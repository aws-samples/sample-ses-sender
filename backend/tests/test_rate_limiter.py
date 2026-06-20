"""Tests for core/rate_limiter.py — local token bucket fallback."""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.rate_limiter import GlobalRateLimiter, _LocalTokenBucket


class TestLocalTokenBucket:
    def test_initial_capacity_allows_burst(self):
        b = _LocalTokenBucket(rate=10, capacity=10)
        # 初始满桶，应能连续取 10 个
        got = sum(1 for _ in range(10) if b.acquire(1))
        assert got == 10

    def test_exhausted_then_denied(self):
        b = _LocalTokenBucket(rate=1, capacity=2)
        assert b.acquire(1) is True
        assert b.acquire(1) is True
        # 桶空，立即再取应失败
        assert b.acquire(1) is False

    def test_refill_over_time(self):
        b = _LocalTokenBucket(rate=100, capacity=1)
        assert b.acquire(1) is True
        assert b.acquire(1) is False
        time.sleep(0.05)  # 100/s 速率，50ms 应补充 ~5 个令牌
        assert b.acquire(1) is True


class TestGlobalRateLimiterFallback:
    def test_no_redis_uses_local(self):
        # 不传 redis_url → 本地令牌桶
        rl = GlobalRateLimiter(rate=5, redis_url="")
        assert rl._redis is None
        # 初始满桶能拿到
        assert rl.acquire(1, timeout=1) is True

    def test_acquire_timeout_returns_false(self):
        rl = GlobalRateLimiter(rate=1, redis_url="")
        # 耗尽
        rl._local.tokens = 0
        rl._local.rate = 0.0001  # 几乎不补充
        rl._local.ts = time.monotonic()
        assert rl.acquire(1, timeout=0.2) is False
