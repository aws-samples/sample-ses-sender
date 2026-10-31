"""Contact status integration tests with a real, isolated SQLAlchemy database."""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from core.database import Base
from core.config import AWS_REGION
from domain.auth.models import User
from domain.audience.models import Contact, ContactGroup
from domain.audience.service import list_contacts
from domain.sending.models import EmailBlacklist, UnsubscribeRecord, SesSuppressedDestination, SesSuppressionSyncState


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            User(id=1, username="owner", email="sender@example.com"),
            User(id=2, username="other", email="other@example.com"),
            ContactGroup(id=1, name="Audience", user_id=1),
            ContactGroup(id=2, name="Private", user_id=2),
            SesSuppressionSyncState(region=AWS_REGION, last_success_at=datetime.utcnow()),
        ])
        session.commit()
        with patch("core.config.ENABLE_SES_SUPPRESSION_SYNC", True):
            yield session
    engine.dispose()


def suppress(email, region=AWS_REGION, reason="BOUNCE"):
    return SesSuppressedDestination(region=region, email=email, reason=reason, last_update_time=datetime.utcnow())


def test_all_sources_can_coexist_and_blacklist_normalizes_recipient(db):
    db.add_all([
        Contact(id=1, group_id=1, email="clean@example.com"),
        Contact(id=2, group_id=1, email="blocked@example.com"),
        Contact(id=3, group_id=1, email=" Upper@Example.COM "),
        EmailBlacklist(email="blocked@example.com"),
        EmailBlacklist(email="upper@example.com"),
        suppress("blocked@example.com", reason="COMPLAINT"),
        suppress("upper@example.com"),
        UnsubscribeRecord(email="blocked@example.com", source_email="sender@example.com"),
    ])
    db.commit()
    result = list_contacts(db, 1, 1)
    by_id = {item["id"]: item for item in result.items}
    assert result.suppression_sync.status == "ready"
    assert result.suppression_sync.last_synced_at.endswith("+00:00")
    assert by_id[1]["blacklist_sources"] == []
    assert by_id[1]["is_blacklisted"] is False
    assert by_id[1]["is_ses_suppressed"] is False
    assert by_id[1]["is_unsubscribed"] is False
    assert by_id[2]["blacklist_sources"] == ["manual", "ses"]
    assert by_id[2]["ses_suppression_reason"] == "COMPLAINT"
    assert by_id[2]["is_unsubscribed"] is True
    assert by_id[3]["blacklist_sources"] == ["manual", "ses"]


def test_sender_and_region_isolation(db):
    db.add_all([
        Contact(group_id=1, email="recipient@example.com"),
        UnsubscribeRecord(email="recipient@example.com", source_email="other@example.com"),
        suppress("recipient@example.com", region="different-region"),
    ])
    db.commit()
    item = list_contacts(db, 1, 1).items[0]
    assert item["is_unsubscribed"] is False
    assert item["is_ses_suppressed"] is False
    with pytest.raises(HTTPException) as exc:
        list_contacts(db, 2, 1)
    assert exc.value.status_code == 404


def test_unsubscribe_matches_sending_case_insensitive_recipient_semantics(db):
    db.add_all([
        Contact(group_id=1, email="User@example.com"),
        UnsubscribeRecord(email="user@example.com", source_email="sender@example.com"),
    ])
    db.commit()
    assert list_contacts(db, 1, 1).items[0]["is_unsubscribed"] is True
    assert list_contacts(db, 1, 1, flags="unsubscribed").total == 1
    assert list_contacts(db, 1, 1, flags="unmatched").total == 0


def test_shared_sender_shares_unsubscribe_scope(db):
    db.get(User, 2).email = "sender@example.com"
    db.add_all([
        Contact(group_id=2, email="recipient@example.com"),
        UnsubscribeRecord(email="recipient@example.com", source_email="sender@example.com"),
    ])
    db.commit()
    assert list_contacts(db, 2, 2).items[0]["is_unsubscribed"] is True


def test_missing_sender_and_first_sync_are_unknown(db):
    db.get(User, 1).email = None
    db.delete(db.get(SesSuppressionSyncState, AWS_REGION))
    db.add(Contact(group_id=1, email="recipient@example.com"))
    db.commit()
    result = list_contacts(db, 1, 1)
    assert result.suppression_sync.status == "pending"
    assert result.items[0]["is_ses_suppressed"] is None
    assert result.items[0]["is_unsubscribed"] is None


def test_stale_and_failed_sync_expose_old_snapshot_without_raw_errors(db):
    state = db.get(SesSuppressionSyncState, AWS_REGION)
    state.last_success_at = datetime.utcnow() - timedelta(days=1)
    db.add_all([Contact(group_id=1, email="old@example.com"), suppress("old@example.com")])
    db.commit()
    assert list_contacts(db, 1, 1).suppression_sync.status == "stale"
    state.last_error = "AccessDenied: internal AWS details"
    db.commit()
    result = list_contacts(db, 1, 1)
    assert result.suppression_sync.status == "error"
    assert result.items[0]["is_ses_suppressed"] is True
    assert "AccessDenied" not in result.model_dump_json()


def test_disabled_sync_is_not_reported_ready(db):
    with patch("core.config.ENABLE_SES_SUPPRESSION_SYNC", False):
        assert list_contacts(db, 1, 1).suppression_sync.status == "disabled"


def test_removal_reflected_on_next_list_request(db):
    entry = suppress("blocked@example.com")
    unsub = UnsubscribeRecord(email=entry.email, source_email="sender@example.com")
    db.add_all([Contact(group_id=1, email=entry.email), entry, unsub])
    db.commit()
    assert list_contacts(db, 1, 1).items[0]["is_blacklisted"] is True
    db.delete(entry)
    db.delete(unsub)
    db.commit()
    item = list_contacts(db, 1, 1).items[0]
    assert item["is_blacklisted"] is False
    assert item["is_unsubscribed"] is False


def test_pagination_search_and_query_count_do_not_scale_per_contact(db):
    db.add_all([Contact(id=i, group_id=1, email=f"user{i}@example.com", name=f"User {i}") for i in range(1, 101)])
    db.commit()
    counts = []
    for page_size in (1, 100):
        db.expire_all()
        statements = []
        def record_query(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        event.listen(db.bind, "before_cursor_execute", record_query)
        try:
            response = list_contacts(db, 1, 1, page_size=page_size)
        finally:
            event.remove(db.bind, "before_cursor_execute", record_query)
        assert response.total == 100
        assert len(response.items) == page_size
        counts.append(len(statements))
    assert counts[0] == counts[1]
    result = list_contacts(db, 1, 1, search="user10@", page_size=10)
    assert result.total == 1
    assert result.items[0]["email"] == "user10@example.com"


@pytest.fixture
def blacklist_cache(db, monkeypatch):
    from core import blacklist, redis_cache
    monkeypatch.setattr(blacklist, "_blacklist", set())
    monkeypatch.setattr(blacklist, "_ses_suppressions", set())
    monkeypatch.setattr(blacklist, "_ses_version", -1)
    monkeypatch.setattr(redis_cache, "_get_client", lambda: None)
    monkeypatch.setattr("core.database.SessionLocal", sessionmaker(bind=db.bind))
    return blacklist


def test_cache_removing_manual_entry_does_not_lift_ses_block(db, blacklist_cache):
    manual = EmailBlacklist(email="blocked@example.com")
    db.add_all([manual, suppress(manual.email)])
    db.commit()
    blacklist_cache.reload()
    db.delete(manual)
    db.commit()
    blacklist_cache.remove("blocked@example.com")
    assert blacklist_cache.count() == 0  # Admin count remains the manual list.
    assert blacklist_cache.is_blacklisted(" BLOCKED@EXAMPLE.COM ") is True


def test_cache_removing_ses_entry_preserves_manual_block(db, blacklist_cache):
    suppression = suppress("blocked@example.com")
    db.add_all([EmailBlacklist(email=suppression.email), suppression,
                suppress("elsewhere@example.com", region="different-region")])
    db.commit()
    blacklist_cache.reload()
    assert blacklist_cache.is_blacklisted("elsewhere@example.com") is False
    db.delete(suppression)
    db.commit()
    blacklist_cache.reload()
    assert blacklist_cache.is_blacklisted("blocked@example.com") is True


def test_authoritative_empty_redis_snapshot_overrides_other_instance_old_memory(db, blacklist_cache, monkeypatch):
    from core import redis_cache
    redis_sets = {}
    monkeypatch.setattr(redis_cache, "replace_set", lambda key, members: redis_sets.update({key: set(members)}))
    monkeypatch.setattr(
        redis_cache, "replace_versioned_set",
        lambda key, members, version: redis_sets.update({key: set(members)}) or True,
    )
    monkeypatch.setattr(redis_cache, "key_exists", lambda key: key in redis_sets)
    monkeypatch.setattr(redis_cache, "sismember", lambda key, email: email in redis_sets.get(key, set()))
    blacklist_cache.reload()
    # Simulate an instance that hasn't refreshed its previous nonempty snapshot.
    blacklist_cache._ses_suppressions.add("removed@example.com")
    assert blacklist_cache.is_blacklisted("removed@example.com") is False
    # Eviction should use the local fallback, while an explicit empty snapshot shouldn't.
    del redis_sets[blacklist_cache._SES_REDIS_KEY]
    assert blacklist_cache.is_blacklisted("removed@example.com") is True


def test_ses_snapshot_blocks_actual_send_before_ses_api(db, blacklist_cache, sample_task, mock_ses):
    from core.sender import send_task
    db.add(suppress(sample_task.recipient))
    db.commit()
    blacklist_cache.reload()
    with patch("core.sender.update_detail_status") as update:
        assert send_task(sample_task) == "failed"
    mock_ses.send_email.assert_not_called()
    update.assert_called_once_with(sample_task, "Failed", "[Blacklisted] 邮箱在黑名单中")
