"""
全局邮箱黑名单及当前区域 SES 抑制名单缓存

优先使用 Redis 共享 Set（多实例强一致，增删立即对全部实例生效）；
Redis 不可用时降级为内存 Set + 后台 60 秒刷新。

发送时直接查缓存，避免每封邮件都查数据库。
"""

import threading
import time
import logging
from typing import Set

from core import redis_cache
from core.config import AWS_REGION, ENABLE_SES_SUPPRESSION_SYNC

logger = logging.getLogger("ses-sender.blacklist")

_REDIS_KEY = "ses:blacklist"
_SES_REDIS_KEY = f"ses:suppression:{AWS_REGION}"
_EMPTY_MEMBER = "__empty__"  # Keep an authoritative empty SES snapshot in Redis.

_blacklist: Set[str] = set()
_ses_suppressions: Set[str] = set()
_ses_version = -1
_ses_ready = False
_ses_redis_trusted = False
_lock = threading.Lock()
_running = False


def _norm(email: str) -> str:
    return (email or "").lower().strip()


def _load_from_db():
    """从数据库加载黑名单到内存 + Redis（若可用）。"""
    global _ses_version, _ses_ready, _ses_redis_trusted
    from core.database import SessionLocal
    from domain.sending.models import EmailBlacklist, SesSuppressedDestination, SesSuppressionSyncState

    db = SessionLocal()
    try:
        rows = db.query(EmailBlacklist.email).all()
        emails = {_norm(r[0]) for r in rows if r[0]}
        with _lock:
            _blacklist.clear()
            _blacklist.update(emails)
        redis_cache.replace_set(_REDIS_KEY, emails)
        # Read authority before rows. Under READ COMMITTED this prevents an
        # initial sync committed between the two reads from blessing older rows.
        state = db.get(SesSuppressionSyncState, AWS_REGION)
        suppressed = {
            _norm(email) for (email,) in db.query(SesSuppressedDestination.email).filter(
                SesSuppressedDestination.region == AWS_REGION
            ).all() if email
        }
        version = state.version if state else 0
        snapshot_is_authoritative = bool(state and state.last_success_at) or not ENABLE_SES_SUPPRESSION_SYNC
        # A missing state after an upgrade is not evidence that the AWS list is
        # empty. Leaving the local state unchanged also makes readiness monotonic
        # if this read began before another thread published the first success.
        if snapshot_is_authoritative:
            becomes_ready = bool(state and state.last_success_at)
            with _lock:
                if version >= _ses_version:
                    _ses_suppressions.clear()
                    _ses_suppressions.update(suppressed)
                    _ses_version = version
            # Empty snapshots still need a key so other instances don't fall back to
            # their old, nonempty memory snapshot after AWS removes the last address.
            publish_result = redis_cache.replace_versioned_set(
                _SES_REDIS_KEY, suppressed or {_EMPTY_MEMBER}, version,
            )
            with _lock:
                # False means Redis already has a newer authoritative version;
                # None means the publish failed and stale Redis must be ignored.
                _ses_redis_trusted = publish_result is not None
                _ses_ready = becomes_ready
        logger.info(
            "[Blacklist] 已加载 %s 个人工黑名单、%s 个 SES 抑制邮箱（同步%s）",
            len(emails), len(suppressed), "就绪" if suppression_ready() else "未就绪",
        )
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


def suppression_ready() -> bool:
    """Whether sending may rely on the current regional suppression snapshot."""
    if not ENABLE_SES_SUPPRESSION_SYNC:
        return True
    with _lock:
        return _ses_ready


def is_blacklisted(email: str) -> bool:
    """两种来源任一命中即拦截；人工增删只操作人工名单。"""
    e = _norm(email)
    hit = redis_cache.sismember(_REDIS_KEY, e)
    if hit is None:
        with _lock:
            hit = e in _blacklist
    if hit:
        return True
    # A missing SES key may mean eviction or a rolling upgrade before the first
    # cache publish, not an empty authoritative list.
    with _lock:
        use_redis_snapshot = _ses_redis_trusted
    ses_hit = (
        redis_cache.sismember(_SES_REDIS_KEY, e)
        if use_redis_snapshot and redis_cache.key_exists(_SES_REDIS_KEY)
        else None
    )
    if ses_hit is None:
        with _lock:
            ses_hit = e in _ses_suppressions
    return ses_hit


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
