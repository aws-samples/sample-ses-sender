"""Tests for core/blacklist.py — in-memory blacklist cache."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import blacklist


class TestBlacklist:
    def setup_method(self):
        blacklist._blacklist.clear()

    def test_is_blacklisted_empty(self):
        assert blacklist.is_blacklisted("any@test.com") is False

    def test_add_and_check(self):
        blacklist.add("blocked@test.com")
        assert blacklist.is_blacklisted("blocked@test.com") is True

    def test_remove(self):
        blacklist.add("temp@test.com")
        assert blacklist.is_blacklisted("temp@test.com") is True
        blacklist.remove("temp@test.com")
        assert blacklist.is_blacklisted("temp@test.com") is False

    def test_case_insensitive(self):
        blacklist.add("User@Test.COM")
        assert blacklist.is_blacklisted("user@test.com") is True
        assert blacklist.is_blacklisted("USER@TEST.COM") is True

    def test_whitespace_stripped(self):
        blacklist.add("  spaces@test.com  ")
        assert blacklist.is_blacklisted("spaces@test.com") is True

    def test_count(self):
        assert blacklist.count() == 0
        blacklist.add("a@t.com")
        blacklist.add("b@t.com")
        assert blacklist.count() == 2

    def test_get_all(self):
        blacklist.add("x@t.com")
        blacklist.add("y@t.com")
        result = blacklist.get_all()
        assert result == {"x@t.com", "y@t.com"}

    def test_remove_nonexistent(self):
        blacklist.remove("noexist@t.com")
        assert blacklist.count() == 0

    def test_add_duplicate(self):
        blacklist.add("dup@t.com")
        blacklist.add("dup@t.com")
        assert blacklist.count() == 1
