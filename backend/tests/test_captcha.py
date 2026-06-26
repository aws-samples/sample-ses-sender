"""Tests for core/captcha.py — 验证码生成 / 校验 / 降级。"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import captcha, redis_cache


class _Store:
    """内存替身存储验证码（带 getdel 一次性语义）。"""

    def __init__(self):
        self.kv = {}

    def get(self, k):
        return self.kv.get(k)

    def set(self, k, v, ex=None, exat=None):
        self.kv[k] = str(v)

    def getdel(self, k):
        return self.kv.pop(k, None)


def _use_store(monkeypatch):
    store = _Store()
    monkeypatch.setattr(redis_cache, "_get_client", lambda: store)
    return store


class TestCaptchaWithRedis:
    def test_generate_returns_id_and_image(self, monkeypatch):
        _use_store(monkeypatch)
        out = captcha.generate()
        assert out["captcha_id"]
        assert out["image"].startswith("data:image/svg+xml;base64,")

    def test_verify_success(self, monkeypatch):
        store = _use_store(monkeypatch)
        out = captcha.generate()
        # 取出 store 中存的答案（小写）
        cid = out["captcha_id"]
        code = store.kv[captcha._KEY_PREFIX + cid]
        assert captcha.verify(cid, code) is True

    def test_verify_case_insensitive(self, monkeypatch):
        store = _use_store(monkeypatch)
        out = captcha.generate()
        cid = out["captcha_id"]
        code = store.kv[captcha._KEY_PREFIX + cid]
        assert captcha.verify(cid, code.upper()) is True

    def test_verify_one_time_only(self, monkeypatch):
        """校验一次后立即失效，防重放。"""
        store = _use_store(monkeypatch)
        out = captcha.generate()
        cid = out["captcha_id"]
        code = store.kv[captcha._KEY_PREFIX + cid]
        assert captcha.verify(cid, code) is True
        assert captcha.verify(cid, code) is False  # 已被消费

    def test_verify_wrong_code(self, monkeypatch):
        _use_store(monkeypatch)
        out = captcha.generate()
        assert captcha.verify(out["captcha_id"], "0000wrong") is False

    def test_verify_empty(self, monkeypatch):
        _use_store(monkeypatch)
        assert captcha.verify("", "abcd") is False
        assert captcha.verify("someid", "") is False

    def test_verify_expired_or_missing(self, monkeypatch):
        _use_store(monkeypatch)
        assert captcha.verify("nonexistent-id", "abcd") is False


class TestCaptchaFallback:
    """Redis 不可用时，verify 跳过校验返回 True（可用性优先）。"""

    def setup_method(self):
        redis_cache._client = None
        redis_cache._init_done = True

    def teardown_method(self):
        redis_cache._init_done = False

    def test_verify_skips_when_unavailable(self):
        assert captcha.verify("anything", "anything") is True

    def test_verify_skips_even_empty(self):
        assert captcha.verify("", "") is True
