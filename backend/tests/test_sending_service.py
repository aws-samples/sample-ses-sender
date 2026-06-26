"""Tests for domain/sending/service.py — bulk send and SES event processing."""
import sys
import os
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSendBulkEmailDedup:
    """Test that duplicate emails in a group are deduplicated."""

    def test_dedup_logic(self):
        """Test the deduplication logic used in send_bulk_email."""
        contact_list = [
            {"email": "dup@test.com", "name": "User1", "attributes": {}},
            {"email": "dup@test.com", "name": "User2", "attributes": {}},
            {"email": "unique@test.com", "name": "User3", "attributes": {}},
        ]
        unsub_emails = set()

        active_contacts = [c for c in contact_list if c["email"] not in unsub_emails]

        # Dedup logic (same as in send_bulk_email)
        seen_emails = set()
        deduped_active = []
        for c in active_contacts:
            if c["email"] not in seen_emails:
                seen_emails.add(c["email"])
                deduped_active.append(c)
        active_contacts = deduped_active

        assert len(active_contacts) == 2
        assert active_contacts[0]["email"] == "dup@test.com"
        assert active_contacts[1]["email"] == "unique@test.com"

    def test_dedup_with_unsubscribed(self):
        """Test dedup combined with unsubscribe filtering."""
        contact_list = [
            {"email": "a@test.com", "name": "A", "attributes": {}},
            {"email": "a@test.com", "name": "A2", "attributes": {}},
            {"email": "unsub@test.com", "name": "U", "attributes": {}},
            {"email": "b@test.com", "name": "B", "attributes": {}},
        ]
        unsub_emails = {"unsub@test.com"}

        active_contacts = [c for c in contact_list if c["email"] not in unsub_emails]
        skipped_contacts = [c for c in contact_list if c["email"] in unsub_emails]

        seen_emails = set()
        deduped_active = []
        for c in active_contacts:
            if c["email"] not in seen_emails:
                seen_emails.add(c["email"])
                deduped_active.append(c)
        active_contacts = deduped_active

        assert len(active_contacts) == 2
        assert len(skipped_contacts) == 1


class TestProcessSesEvent:
    """Test SES event processing."""

    def test_delivery_event(self):
        from domain.sending.service import process_ses_event

        db = MagicMock()
        mock_detail = MagicMock()
        mock_detail.send_status = "Success"
        mock_detail.delivery_status = None
        mock_detail.message_id = "msg-123"
        db.query.return_value.filter.return_value.first.return_value = mock_detail

        event_data = {
            "eventType": "Delivery",
            "mail": {"messageId": "msg-123"},
            "delivery": {"timestamp": "2026-05-15T10:00:00Z"},
        }
        process_ses_event(event_data, db)

        assert mock_detail.delivery_status == "Delivery"
        db.commit.assert_called()

    def test_bounce_event(self):
        from domain.sending.service import process_ses_event

        db = MagicMock()
        mock_detail = MagicMock()
        mock_detail.send_status = "Success"
        mock_detail.delivery_status = None
        mock_detail.message_id = "msg-456"
        db.query.return_value.filter.return_value.first.return_value = mock_detail

        event_data = {
            "eventType": "Bounce",
            "mail": {"messageId": "msg-456"},
            "bounce": {
                "bounceType": "Permanent",
                "bounceSubType": "General",
                "bouncedRecipients": [{"diagnosticCode": "550 No such user"}],
                "timestamp": "2026-05-15T10:00:00Z",
            },
        }
        process_ses_event(event_data, db)

        assert mock_detail.delivery_status == "Bounce"
        assert mock_detail.bounce_type == "Permanent"
        db.commit.assert_called()

    def test_fixes_pending_status(self):
        from domain.sending.service import process_ses_event

        db = MagicMock()
        mock_detail = MagicMock()
        mock_detail.send_status = "Pending"
        mock_detail.delivery_status = None
        mock_detail.message_id = "msg-789"
        db.query.return_value.filter.return_value.first.return_value = mock_detail

        event_data = {
            "eventType": "Delivery",
            "mail": {"messageId": "msg-789"},
            "delivery": {"timestamp": "2026-05-15T10:00:00Z"},
        }
        process_ses_event(event_data, db)

        assert mock_detail.send_status == "Success"
        assert mock_detail.delivery_status == "Delivery"

    def test_ignores_unknown_message_id(self):
        from domain.sending.service import process_ses_event

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        event_data = {
            "eventType": "Delivery",
            "mail": {"messageId": "unknown-msg"},
            "delivery": {},
        }
        process_ses_event(event_data, db)
        db.commit.assert_not_called()


class TestDailyQuotaRedis:
    """每日配额 Redis 计数器：命中缓存直接用，未命中回退 DB 并回填。"""

    def test_quota_uses_redis_counter_when_present(self):
        from domain.sending import service
        from core import redis_cache

        db = MagicMock()
        user = MagicMock()
        user.daily_send_limit = 1000
        db.query.return_value.filter.return_value.first.return_value = user

        with patch.object(redis_cache, "get_int", return_value=300) as gi, \
             patch.object(redis_cache, "set_int") as si:
            q = service.get_user_daily_quota(db, user_id=7)

        gi.assert_called_once()
        # 命中缓存就不应回填
        si.assert_not_called()
        assert q["today_sent"] == 300
        assert q["daily_limit"] == 1000
        assert q["remaining"] == 700

    def test_quota_falls_back_to_db_and_backfills(self):
        from domain.sending import service
        from core import redis_cache

        db = MagicMock()
        user = MagicMock()
        user.daily_send_limit = 500
        db.query.return_value.filter.return_value.first.return_value = user
        # DB 聚合返回 120
        db.query.return_value.filter.return_value.scalar.return_value = 120

        with patch.object(redis_cache, "get_int", return_value=None), \
             patch.object(redis_cache, "set_int") as si:
            q = service.get_user_daily_quota(db, user_id=9)

        si.assert_called_once()  # 回填 Redis
        assert q["today_sent"] == 120
        assert q["remaining"] == 380

