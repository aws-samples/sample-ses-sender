"""Tests for core/redis_cache.py — 降级行为 + 基于 fakeredis 风格的 Mock 行为。"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import redis_cache


class _FakeRedis:
    """极简内存 Redis 替身，覆盖被 redis_cache 用到的命令。"""

    def __init__(self):
        self.kv = {}
        self.sets = {}

    # 字符串
    def get(self, k):
        return self.kv.get(k)

    def set(self, k, v, ex=None, exat=None):
        self.kv[k] = str(v)

    def delete(self, *keys):
        for k in keys:
            self.kv.pop(k, None)
            self.sets.pop(k, None)

    def exists(self, k):
        return 1 if (k in self.kv or k in self.sets) else 0

    def getdel(self, k):
        return self.kv.pop(k, None)

    def incrby(self, k, amount):
        cur = int(self.kv.get(k, 0)) + amount
        self.kv[k] = str(cur)
        return cur

    def expireat(self, k, ts):
        return True

    def expire(self, k, ttl):
        return True

    # 集合
    def sadd(self, k, *members):
        self.sets.setdefault(k, set()).update(members)

    def srem(self, k, *members):
        self.sets.setdefault(k, set()).difference_update(members)

    def sismember(self, k, m):
        return m in self.sets.get(k, set())

    def smembers(self, k):
        return set(self.sets.get(k, set()))

    # pipeline（同步执行收集结果）
    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, r):
        self.r = r
        self.ops = []

    def __getattr__(self, name):
        def collector(*args, **kwargs):
            self.ops.append((name, args, kwargs))
            return self
        return collector

    def execute(self):
        results = []
        for name, args, kwargs in self.ops:
            results.append(getattr(self.r, name)(*args, **kwargs))
        return results


def _use_fake(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(redis_cache, "_get_client", lambda: fake)
    return fake


class TestRedisCacheFallback:
    """Redis 不可用时全部降级（_get_client 返回 None）。"""

    def setup_method(self):
        # 强制视为不可用
        redis_cache._client = None
        redis_cache._init_done = True

    def teardown_method(self):
        redis_cache._init_done = False

    def test_get_json_none_when_unavailable(self):
        assert redis_cache.get_json("k") is None

    def test_set_json_noop_when_unavailable(self):
        redis_cache.set_json("k", {"a": 1})  # 不应抛异常

    def test_sismember_none_when_unavailable(self):
        assert redis_cache.sismember("s", "m") is None

    def test_incrby_none_when_unavailable(self):
        assert redis_cache.incrby("c", 5) is None

    def test_getdel_none_when_unavailable(self):
        assert redis_cache.getdel("k") is None

    def test_available_false(self):
        assert redis_cache.available() is False


class TestRedisCacheWithFake:
    def test_json_roundtrip(self, monkeypatch):
        _use_fake(monkeypatch)
        redis_cache.set_json("k", {"a": 1, "b": [1, 2]})
        assert redis_cache.get_json("k") == {"a": 1, "b": [1, 2]}

    def test_delete(self, monkeypatch):
        _use_fake(monkeypatch)
        redis_cache.set_json("k", 1)
        redis_cache.delete("k")
        assert redis_cache.get_json("k") is None

    def test_set_ops(self, monkeypatch):
        _use_fake(monkeypatch)
        redis_cache.sadd("s", "a@t.com", "b@t.com")
        assert redis_cache.sismember("s", "a@t.com") is True
        assert redis_cache.sismember("s", "z@t.com") is False
        redis_cache.srem("s", "a@t.com")
        assert redis_cache.sismember("s", "a@t.com") is False

    def test_replace_set_and_smembers(self, monkeypatch):
        _use_fake(monkeypatch)
        redis_cache.replace_set("s", {"x", "y"})
        assert redis_cache.smembers("s") == {"x", "y"}
        redis_cache.replace_set("s", {"z"})
        assert redis_cache.smembers("s") == {"z"}

    def test_counter(self, monkeypatch):
        _use_fake(monkeypatch)
        assert redis_cache.incrby("c", 10, 0) == 10
        assert redis_cache.incrby("c", 5, 0) == 15
        assert redis_cache.get_int("c") == 15
        assert redis_cache.incrby("c", -3) == 12

    def test_getdel_consumes(self, monkeypatch):
        _use_fake(monkeypatch)
        redis_cache.setex("k", "val", 60)
        assert redis_cache.getdel("k") == "val"
        assert redis_cache.getdel("k") is None
