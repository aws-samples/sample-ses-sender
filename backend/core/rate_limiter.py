"""
全局发送速率限流器。

优先使用 Redis 令牌桶（多实例间全局精确限流），Redis 不可用时降级为本地令牌桶。
所有 Consumer 在调用 SES 发送前先 acquire 一个令牌，确保全局总速率不超过 SES 上限。
"""

import time
import threading
import logging

logger = logging.getLogger("ses-sender.ratelimit")

# Redis 令牌桶 Lua 脚本（原子）：
#   KEYS[1] = 桶 key
#   ARGV[1] = 每秒补充速率(rate)
#   ARGV[2] = 桶容量(capacity)
#   ARGV[3] = 当前时间戳(秒, 浮点)
#   ARGV[4] = 本次请求令牌数(通常 1)
# 返回 1=获得令牌, 0=无令牌
_LUA_TOKEN_BUCKET = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])

local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  ts = now
end

local delta = math.max(0, now - ts)
tokens = math.min(capacity, tokens + delta * rate)

local allowed = 0
if tokens >= requested then
  tokens = tokens - requested
  allowed = 1
end

redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, 60)
return allowed
"""


class _LocalTokenBucket:
    """本地令牌桶（单进程降级用）。"""

    def __init__(self, rate: float, capacity: float):
        self.rate = max(rate, 0.1)
        self.capacity = max(capacity, 1.0)
        self.tokens = self.capacity
        self.ts = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self, n: int = 1) -> bool:
        with self.lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.ts) * self.rate)
            self.ts = now
            if self.tokens >= n:
                self.tokens -= n
                return True
            return False


class GlobalRateLimiter:
    """全局发送限流器。Redis 优先，失败降级本地。"""

    def __init__(self, rate: int, redis_url: str = "", key: str = "ses-sender:send-bucket"):
        self.rate = max(rate, 1)
        self.capacity = max(rate, 1)
        self.key = key
        self._redis = None
        self._sha = None
        self._local = _LocalTokenBucket(self.rate, self.capacity)

        if redis_url:
            try:
                import redis
                self._redis = redis.Redis.from_url(redis_url, socket_timeout=2, socket_connect_timeout=2)
                self._sha = self._redis.script_load(_LUA_TOKEN_BUCKET)
                self._redis.ping()
                logger.info(f"[RateLimit] Redis 全局令牌桶启用: rate={self.rate}/s")
            except Exception as e:
                logger.warning(f"[RateLimit] Redis 不可用，降级本地令牌桶: {e}")
                self._redis = None
        else:
            logger.info(f"[RateLimit] 未配置 Redis，使用本地令牌桶: rate={self.rate}/s")

    def _try_redis(self, n: int) -> bool:
        try:
            allowed = self._redis.evalsha(
                self._sha, 1, self.key,
                self.rate, self.capacity, time.time(), n,
            )
            return int(allowed) == 1
        except Exception as e:
            logger.warning(f"[RateLimit] Redis 取令牌失败，本次降级本地: {e}")
            return self._local.acquire(n)

    def acquire(self, n: int = 1, timeout: float = 30.0) -> bool:
        """阻塞获取令牌，最多等 timeout 秒。拿到返回 True，超时返回 False。"""
        deadline = time.monotonic() + timeout
        while True:
            ok = self._try_redis(n) if self._redis is not None else self._local.acquire(n)
            if ok:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)  # nosemgrep: arbitrary-sleep
