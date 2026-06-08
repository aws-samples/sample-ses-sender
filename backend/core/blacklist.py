"""
全局邮箱黑名单缓存

启动时从 DB 加载到内存 Set，后台线程每 60 秒刷新一次。
发送时直接查内存，避免每封邮件都查数据库。
"""

import threading
import time
import logging
from typing import Set

logger = logging.getLogger("ses-sender.blacklist")

_blacklist: Set[str] = set()
_lock = threading.Lock()
_running = False


def _load_from_db():
    """从数据库加载黑名单到内存"""
    from core.database import SessionLocal
    from domain.sending.models import EmailBlacklist

    db = SessionLocal()
    try:
        rows = db.query(EmailBlacklist.email).all()
        emails = {r[0].lower().strip() for r in rows}
        with _lock:
            _blacklist.clear()
            _blacklist.update(emails)
        logger.info(f"[Blacklist] 已加载 {len(emails)} 个黑名单邮箱")
    except Exception as e:
        logger.error(f"[Blacklist] 加载失败: {e}")
    finally:
        db.close()


def _refresh_loop():
    """后台线程：每 60 秒刷新一次"""
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
    """检查邮箱是否在黑名单中"""
    with _lock:
        return email.lower().strip() in _blacklist


def add(email: str):
    """添加到内存缓存（DB 操作由调用方负责）"""
    with _lock:
        _blacklist.add(email.lower().strip())


def remove(email: str):
    """从内存缓存移除"""
    with _lock:
        _blacklist.discard(email.lower().strip())


def reload():
    """手动触发重新加载"""
    _load_from_db()


def get_all() -> Set[str]:
    """获取当前缓存的全部黑名单"""
    with _lock:
        return _blacklist.copy()


def count() -> int:
    with _lock:
        return len(_blacklist)
