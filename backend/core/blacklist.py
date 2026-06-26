"""
全局邮箱黑名单缓存

优先使用 Redis 共享 Set（多实例强一致，增删立即对全部实例生效）；
Redis 不可用时降级为内存 Set + 后台 60 秒刷新。

发送时直接查缓存，避免每封邮件都查数据库。
"""

import threading
import time
import logging
from typing import Set

from core import redis_cache

logger = logging.getLogger("ses-sender.blacklist")

_REDIS_KEY = "ses:blacklist"

_blacklist: Set[str] = set()
_lock = threading.Lock()
_running = False


def _norm(email: str) -> str:
    return (email or "").lower().strip()


def _load_from_db():
    """从数据库加载黑名单到内存 + Redis（若可用）。"""
    from core.database import SessionLocal
    from domain.sending.models import EmailBlacklist

    db = SessionLocal()
    try:
        rows = db.query(EmailBlacklist.email).all()
        emails = {_norm(r[0]) for r in rows if r[0]}
        with _lock:
            _blacklist.clear()
            _blacklist.update(emails)
        # 同步全量到 Redis（不可用时静默忽略）
        redis_cache.replace_set(_REDIS_KEY, emails)
        logger.info(f"[Blacklist] 已加载 {len(emails)} 个黑名单邮箱")
    except Exception as e:
        logger.error(f"[Blacklist] 加载失败: {e}")
    finally:
        db.close()


def _refresh_loop():
    """后台线程：每 60 秒刷新一次（仅作为兜底，Redis 模式下主要靠实时增删）。"""
    while _running:
        time.sleep(60)  # nosemgrep: arbitrary-sleep
        if _running:
            _load_from_db()


def start():
    """启动黑名单缓存（加载 + 后台刷新线程）"""
    global _running
    _load_from_db()
    _running = True
    t = threading.Thread(target=_refresh_loop, daemon=True)
    t.start()


def is_blacklisted(email: str) -> bool:
    """检查邮箱是否在黑名单中。优先查 Redis，失败回退内存。"""
    e = _norm(email)
    hit = redis_cache.sismember(_REDIS_KEY, e)
    if hit is not None:
        return hit
    with _lock:
        return e in _blacklist


def add(email: str):
    """添加到缓存（DB 操作由调用方负责）。同步写 Redis + 内存。"""
    e = _norm(email)
    redis_cache.sadd(_REDIS_KEY, e)
    with _lock:
        _blacklist.add(e)


def remove(email: str):
    """从缓存移除。同步移除 Redis + 内存。"""
    e = _norm(email)
    redis_cache.srem(_REDIS_KEY, e)
    with _lock:
        _blacklist.discard(e)


def reload():
    """手动触发重新加载"""
    _load_from_db()


def get_all() -> Set[str]:
    """获取当前缓存的全部黑名单（内存副本）"""
    with _lock:
        return _blacklist.copy()


def count() -> int:
    with _lock:
        return len(_blacklist)
