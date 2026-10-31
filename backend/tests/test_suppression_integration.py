"""Optional service integration checks; use dedicated disposable test services.

SES_TEST_MYSQL_URL=mysql+pymysql://.../test_db
SES_TEST_REDIS_URL=redis://.../0
AWS is always mocked; no emails are sent or suppression lists modified.
"""
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core import ses_suppression, redis_cache
from domain.sending.models import SesSuppressedDestination, SesSuppressionSyncState


@pytest.fixture
def mysql_engine():
    url = os.getenv("SES_TEST_MYSQL_URL")
    if not url:
        pytest.skip("SES_TEST_MYSQL_URL not configured")
    engine = create_engine(url)
    SesSuppressedDestination.__table__.create(engine, checkfirst=True)
    SesSuppressionSyncState.__table__.create(engine, checkfirst=True)
    yield engine
    engine.dispose()


def test_mysql_snapshot_failure_persistence_and_shared_lock(mysql_engine):
    region = "test-" + uuid.uuid4().hex
    client = MagicMock()
    client.list_suppressed_destinations.return_value = {
        "SuppressedDestinationSummaries": [{
            "EmailAddress": "USER@example.com", "Reason": "BOUNCE",
            "LastUpdateTime": datetime.now(timezone.utc),
        }]
    }
    try:
        with patch("core.blacklist.reload"):
            assert ses_suppression.sync_once(client=client, region=region, db_engine=mysql_engine)
            client.list_suppressed_destinations.side_effect = RuntimeError("simulated API failure")
            assert not ses_suppression.sync_once(client=client, region=region, db_engine=mysql_engine, force=True)
            with Session(mysql_engine) as db:
                state = db.get(SesSuppressionSyncState, region)
                assert state.last_success_at is not None
                assert state.last_error == "simulated API failure"
                assert state.version == 1
                assert db.query(SesSuppressedDestination).filter_by(region=region).one().email == "user@example.com"
            client.reset_mock()
            with mysql_engine.connect() as owner:
                with ses_suppression._sync_lock(owner, region) as acquired:
                    assert acquired
                    assert not ses_suppression.sync_once(client=client, region=region, db_engine=mysql_engine, force=True)
                    client.list_suppressed_destinations.assert_not_called()
            client.list_suppressed_destinations.side_effect = None
            client.list_suppressed_destinations.return_value = {"SuppressedDestinationSummaries": []}
            assert ses_suppression.sync_once(client=client, region=region, db_engine=mysql_engine, force=True)
            with Session(mysql_engine) as db:
                state = db.get(SesSuppressionSyncState, region)
                assert state.version == 2
                assert state.last_error is None
                assert db.query(SesSuppressedDestination).filter_by(region=region).count() == 0
    finally:
        with Session(mysql_engine) as db:
            db.query(SesSuppressedDestination).filter_by(region=region).delete()
            db.query(SesSuppressionSyncState).filter_by(region=region).delete()
            db.commit()


def test_redis_versioned_snapshot_rejects_stale_publish_and_clears_removed_addresses(monkeypatch):
    url = os.getenv("SES_TEST_REDIS_URL")
    if not url:
        pytest.skip("SES_TEST_REDIS_URL not configured")
    import redis
    client = redis.Redis.from_url(url, decode_responses=True)
    key = "ses-test:" + uuid.uuid4().hex
    monkeypatch.setattr(redis_cache, "_get_client", lambda: client)
    try:
        emails = {f"user{i}@example.com" for i in range(1200)}
        assert redis_cache.replace_versioned_set(key, emails, 2) is True
        assert redis_cache.replace_versioned_set(key, {"outdated@example.com"}, 1) is False
        assert client.smembers(key) == emails
        assert redis_cache.replace_versioned_set(key, {"__empty__"}, 3) is True
        assert not client.sismember(key, "user1@example.com")
        assert redis_cache.replace_versioned_set(key, emails, 2) is False
        assert client.smembers(key) == {"__empty__"}
    finally:
        client.delete(key, key + ":version")
        client.close()
