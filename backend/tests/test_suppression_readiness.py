"""Sending gates for the initial SES suppression snapshot."""

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core import blacklist, redis_cache, ses_suppression
from core.config import AWS_REGION
from core.sender import SenderEngine, send_task
from domain.sending.models import (
    EmailBlacklist,
    SesSuppressedDestination,
    SesSuppressionSyncState,
)


@pytest.fixture
def cache_db(monkeypatch):
    engine = create_engine("sqlite://")
    for model in (EmailBlacklist, SesSuppressedDestination, SesSuppressionSyncState):
        model.__table__.create(engine)
    sessions = sessionmaker(bind=engine)

    monkeypatch.setattr("core.database.SessionLocal", sessions)
    monkeypatch.setattr(redis_cache, "_get_client", lambda: None)
    monkeypatch.setattr(blacklist, "_blacklist", set())
    monkeypatch.setattr(blacklist, "_ses_suppressions", set())
    monkeypatch.setattr(blacklist, "_ses_version", -1)
    monkeypatch.setattr(blacklist, "_ses_ready", False, raising=False)
    monkeypatch.setattr(blacklist, "_ses_redis_trusted", False, raising=False)
    monkeypatch.setattr(blacklist, "ENABLE_SES_SUPPRESSION_SYNC", True, raising=False)

    yield sessions
    engine.dispose()


def _seed_success(sessions, *, error=None, suppressed=()):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with sessions() as db:
        db.add(SesSuppressionSyncState(
            region=AWS_REGION,
            version=1,
            last_success_at=now,
            last_attempt_at=now,
            last_error=error,
        ))
        db.add_all([
            SesSuppressedDestination(
                region=AWS_REGION,
                email=email,
                reason="BOUNCE",
                last_update_time=now,
            )
            for email in suppressed
        ])
        db.commit()


def _run_send(task):
    detail = MagicMock(send_status="Queued")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = detail
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = detail
    ses = MagicMock()
    ses.send_email.return_value = {"MessageId": "message-1"}
    with patch("core.database.SessionLocal", return_value=db), \
         patch("core.ses.sesv2_client", ses), \
         patch("core.sender.update_detail_status") as update:
        result = send_task(task)
    return result, ses, update


def test_enabled_without_success_does_not_publish_authoritative_empty_snapshot(cache_db):
    publish = MagicMock()
    with patch.object(redis_cache, "replace_versioned_set", publish):
        blacklist.reload()
    publish.assert_not_called()


def test_sync_commit_during_initial_load_cannot_make_older_empty_rows_authoritative(cache_db):
    state_after_commit = SesSuppressionSyncState(
        region=AWS_REGION,
        version=1,
        last_success_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db = MagicMock()
    manual_query = MagicMock()
    manual_query.all.return_value = []
    suppression_query = MagicMock()
    suppression_query.filter.return_value.all.side_effect = lambda: (
        setattr(db.get, "return_value", state_after_commit) or []
    )
    db.query.side_effect = [manual_query, suppression_query]
    db.get.return_value = None
    publish = MagicMock()

    with patch("core.database.SessionLocal", return_value=db), \
         patch.object(redis_cache, "replace_versioned_set", publish):
        blacklist.reload()

    publish.assert_not_called()


def test_stale_not_ready_reload_cannot_revoke_a_completed_sync(cache_db, monkeypatch):
    monkeypatch.setattr(blacklist, "_ses_ready", True)
    monkeypatch.setattr(blacklist, "_ses_version", 1)
    monkeypatch.setattr(blacklist, "_ses_suppressions", {"kept@example.com"})
    delete = MagicMock()

    with patch.object(redis_cache, "delete", delete):
        blacklist.reload()

    assert blacklist.suppression_ready() is True
    assert blacklist.is_blacklisted("kept@example.com") is True
    delete.assert_not_called()


def test_enabled_without_success_defers_at_final_ses_boundary(cache_db, sample_task):
    blacklist.reload()

    result, ses, update = _run_send(sample_task)

    assert result == "deferred"
    ses.send_email.assert_not_called()
    update.assert_not_called()


def test_successful_snapshot_allows_send(cache_db, sample_task):
    _seed_success(cache_db)
    blacklist.reload()

    result, ses, update = _run_send(sample_task)

    assert result == "success"
    ses.send_email.assert_called_once()
    update.assert_called_once_with(sample_task, "Success", "", "message-1")


def test_initial_readiness_is_published_only_after_shared_snapshot(cache_db, sample_task):
    _seed_success(cache_db)
    readiness_during_publish = []

    with patch.object(
        redis_cache,
        "replace_versioned_set",
        side_effect=lambda *args: (
            readiness_during_publish.append(blacklist.suppression_ready()) or True
        ),
    ):
        blacklist.reload()

    assert readiness_during_publish == [False]
    assert _run_send(sample_task)[0] == "success"


def test_failed_first_redis_publish_uses_local_snapshot_after_redis_recovers(cache_db, sample_task):
    _seed_success(cache_db, suppressed=(sample_task.recipient,))
    with patch.object(redis_cache, "replace_versioned_set", return_value=None):
        blacklist.reload()

    # Redis recovered with the legacy version-0 empty set still present.
    with patch.object(redis_cache, "key_exists", return_value=True), \
         patch.object(redis_cache, "sismember", return_value=False):
        result, ses, update = _run_send(sample_task)

    assert result == "failed"
    ses.send_email.assert_not_called()
    update.assert_called_once_with(sample_task, "Failed", "[Blacklisted] 邮箱在黑名单中")


def test_failure_after_success_keeps_snapshot_and_does_not_block_clean_send(cache_db, sample_task):
    _seed_success(cache_db, suppressed=("blocked@example.com",))
    client = MagicMock()
    client.list_suppressed_destinations.side_effect = RuntimeError("simulated later AWS failure")
    assert not ses_suppression.sync_once(
        client=client,
        region=AWS_REGION,
        db_engine=cache_db.kw["bind"],
        force=True,
    )
    blacklist.reload()

    clean_result, clean_ses, _ = _run_send(sample_task)
    blocked = replace(sample_task, recipient="blocked@example.com")
    blocked_result, blocked_ses, blocked_update = _run_send(blocked)

    assert clean_result == "success"
    clean_ses.send_email.assert_called_once()
    assert blocked_result == "failed"
    blocked_ses.send_email.assert_not_called()
    blocked_update.assert_called_once_with(blocked, "Failed", "[Blacklisted] 邮箱在黑名单中")


def test_disabled_sync_allows_send_and_keeps_manual_blacklist(cache_db, sample_task, monkeypatch):
    monkeypatch.setattr(blacklist, "ENABLE_SES_SUPPRESSION_SYNC", False)
    with cache_db() as db:
        db.add(EmailBlacklist(email="manual@example.com", created_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        db.commit()
    blacklist.reload()

    clean_result, clean_ses, _ = _run_send(sample_task)
    manual = replace(sample_task, recipient="manual@example.com")
    manual_result, manual_ses, _ = _run_send(manual)

    assert clean_result == "success"
    clean_ses.send_email.assert_called_once()
    assert manual_result == "failed"
    manual_ses.send_email.assert_not_called()


def test_memory_scanner_does_not_claim_queued_or_resumed_jobs_before_ready(cache_db):
    blacklist.reload()
    engine = SenderEngine.__new__(SenderEngine)

    with patch("core.database.SessionLocal") as sessions:
        engine._process_queued_jobs()

    sessions.assert_not_called()


def test_sqs_producer_does_not_claim_queued_or_resumed_jobs_before_ready(cache_db):
    from core.sqs_sender import SqsSendEngine

    blacklist.reload()
    engine = SqsSendEngine.__new__(SqsSendEngine)
    engine.sqs = MagicMock()

    with patch("core.sqs_sender.SessionLocal") as sessions:
        engine._produce_once()

    sessions.assert_not_called()
    engine.sqs.send_message_batch.assert_not_called()


def test_sqs_consumer_preserves_message_if_final_boundary_defers(sample_task):
    from core.sqs_sender import SqsSendEngine

    engine = SqsSendEngine.__new__(SqsSendEngine)
    engine.running = True
    engine.rate_limiter = MagicMock()
    engine.sqs = MagicMock()
    message = {"Body": '{"detail_id": 42}', "ReceiptHandle": "receipt-1"}

    def receive_message(**kwargs):
        engine.running = False
        return {"Messages": [message]}

    engine.sqs.receive_message.side_effect = receive_message
    detail = MagicMock(id=42, batch_id="batch-1", recipient=sample_task.recipient, send_status="Queued")
    job = MagicMock(batch_id="batch-1")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [detail, job]

    with patch("core.sqs_sender.SessionLocal", return_value=db), \
         patch.object(blacklist, "suppression_ready", return_value=True, create=True), \
         patch("core.sqs_sender._sender.load_job_send_context", return_value=(None, [], "reply@example.com", 1)), \
         patch("core.sqs_sender._sender.load_contact_map", return_value={}), \
         patch("core.sqs_sender._sender.build_send_task", return_value=sample_task), \
         patch("core.sqs_sender._sender.send_task", return_value="deferred"):
        engine._consumer_loop(0)

    engine.sqs.delete_message.assert_not_called()
