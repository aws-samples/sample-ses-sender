"""
统一 Redis 缓存层。

复用 core.config.REDIS_URL 配置，提供单例客户端 + JSON/Set/计数器封装。
所有方法在 Redis 不可用（未配置 / 连接失败 / 运行时异常）时静默降级：
读返回 None、写静默忽略，由调用方回退到 DB / 内存逻辑，确保功能永不被缓存层阻断。

设计原则：
- 客户端单例，惰性初始化，连接失败后不再反复尝试连接（短路）。
- 所有操作包裹 try/except，异常只记日志不抛出。
- decode_responses=True，统一处理字符串。
"""

import json
import logging
import threading
import time

logger = logging.getLogger("ses-sender.cache")

_client = None
_init_done = False
_lock = threading.Lock()
_last_fail_log = 0.0


def _get_client():
    """惰性初始化 Redis 客户端单例。未配置或连接失败返回 None。"""
    global _client, _init_done
    if _init_done:
        return _client
    with _lock:
        if _init_done:
            return _client
        _init_done = True
        try:
            from core.config import REDIS_URL
            if not REDIS_URL:
                logger.info("[Cache] 未配置 REDIS_URL，缓存层禁用（降级到 DB）")
                _client = None
                return None
            import redis
            c = redis.Redis.from_url(
                REDIS_URL,
                socket_timeout=2,
                socket_connect_timeout=2,
                decode_responses=True,
            )
            c.ping()
            _client = c
            logger.info("[Cache] Redis 缓存层已启用")
        except Exception as e:
            logger.warning(f"[Cache] Redis 不可用，缓存层降级: {e}")
            _client = None
    return _client


def available() -> bool:
    return _get_client() is not None


def _warn(msg: str, e: Exception):
    """对运行时偶发错误做节流日志，避免刷屏。"""
    global _last_fail_log
    now = time.time()
    if now - _last_fail_log > 30:
        _last_fail_log = now
        logger.warning(f"[Cache] {msg}: {e}")


# ========== JSON 键值缓存 ==========

def get_json(key: str):
    """读 JSON 缓存。未命中 / 不可用返回 None。"""
    c = _get_client()
    if c is None:
        return None
    try:
        raw = c.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        _warn(f"get_json({key}) 失败", e)
        return None


def set_json(key: str, value, ttl: int = 300):
    """写 JSON 缓存，带 TTL（秒）。不可用时静默忽略。"""
    c = _get_client()
    if c is None:
        return
    try:
        c.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
    except Exception as e:
        _warn(f"set_json({key}) 失败", e)


def delete(*keys: str):
    """删除一个或多个键（缓存失效）。"""
    c = _get_client()
    if c is None or not keys:
        return
    try:
        c.delete(*keys)
    except Exception as e:
        _warn(f"delete({keys}) 失败", e)


# ========== Set 操作（黑名单 / 退订列表） ==========

def sismember(key: str, member: str):
    """判断成员是否在 Set 中。不可用返回 None（由调用方决定回退）。"""
    c = _get_client()
    if c is None:
        return None
    try:
        return bool(c.sismember(key, member))
    except Exception as e:
        _warn(f"sismember({key}) 失败", e)
        return None


def sadd(key: str, *members: str):
    c = _get_client()
    if c is None or not members:
        return
    try:
        c.sadd(key, *members)
    except Exception as e:
        _warn(f"sadd({key}) 失败", e)


def srem(key: str, *members: str):
    c = _get_client()
    if c is None or not members:
        return
    try:
        c.srem(key, *members)
    except Exception as e:
        _warn(f"srem({key}) 失败", e)


def replace_set(key: str, members, ttl: int = 0):
    """用给定成员全量替换一个 Set（原子：DEL + SADD via pipeline）。"""
    c = _get_client()
    if c is None:
        return
    try:
        pipe = c.pipeline()
        pipe.delete(key)
        if members:
            pipe.sadd(key, *members)
            if ttl > 0:
                pipe.expire(key, ttl)
        pipe.execute()
    except Exception as e:
        _warn(f"replace_set({key}) 失败", e)


def smembers(key: str):
    """返回 Set 全部成员（set）。key 不存在返回空 set，Redis 不可用返回 None。"""
    c = _get_client()
    if c is None:
        return None
    try:
        return set(c.smembers(key))
    except Exception as e:
        _warn(f"smembers({key}) 失败", e)
        return None


def key_exists(key: str):
    """判断 key 是否存在。不可用返回 None。"""
    c = _get_client()
    if c is None:
        return None
    try:
        return c.exists(key) > 0
    except Exception as e:
        _warn(f"key_exists({key}) 失败", e)
        return None


# ========== 计数器（每日配额） ==========

def incrby(key: str, amount: int, expire_at_ts: int = 0):
    """
    原子自增计数器，返回自增后的值；不可用返回 None。
    expire_at_ts > 0 时设置绝对过期时间（仅在 key 新建时近似生效，重复设置幂等）。
    """
    c = _get_client()
    if c is None:
        return None
    try:
        pipe = c.pipeline()
        pipe.incrby(key, amount)
        if expire_at_ts > 0:
            pipe.expireat(key, expire_at_ts)
        res = pipe.execute()
        return int(res[0])
    except Exception as e:
        _warn(f"incrby({key}) 失败", e)
        return None


def get_int(key: str):
    """读整数计数器。未命中 / 不可用返回 None。"""
    c = _get_client()
    if c is None:
        return None
    try:
        raw = c.get(key)
        return int(raw) if raw is not None else None
    except Exception as e:
        _warn(f"get_int({key}) 失败", e)
        return None


def set_int(key: str, value: int, expire_at_ts: int = 0):
    """设置整数计数器初值（用于从 DB 回填）。"""
    c = _get_client()
    if c is None:
        return
    try:
        if expire_at_ts > 0:
            c.set(key, value, exat=expire_at_ts)
        else:
            c.set(key, value)
    except Exception as e:
        _warn(f"set_int({key}) 失败", e)


def setex(key: str, value: str, ttl: int):
    """写字符串带 TTL（验证码用）。"""
    c = _get_client()
    if c is None:
        return
    try:
        c.set(key, value, ex=ttl)
    except Exception as e:
        _warn(f"setex({key}) 失败", e)


def getdel(key: str):
    """读取并删除（验证码一次性校验，防重放）。不可用返回 None。"""
    c = _get_client()
    if c is None:
        return None
    try:
        if hasattr(c, "getdel"):
            return c.getdel(key)
        pipe = c.pipeline()
        pipe.get(key)
        pipe.delete(key)
        return pipe.execute()[0]
    except Exception as e:
        _warn(f"getdel({key}) 失败", e)
        return None
