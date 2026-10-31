"""SES suppression sync tests use isolated SQLite databases and mocked AWS calls."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call
import threading
import asyncio

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from core import ses_suppression
from domain.sending.models import EmailBlacklist, SesSuppressedDestination, SesSuppressionSyncState

REGION = "us-east-1"
UPDATED_AT = datetime(2026, 10, 27, 8, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize("fail_during_lifespan", [False, True])
def test_fastapi_lifespan_starts_and_stops_worker(monkeypatch, fail_during_lifespan):
    from fastapi import FastAPI
    start = MagicMock()
    stop = MagicMock()
    monkeypatch.setattr(ses_suppression, "start", start)
    monkeypatch.setattr(ses_suppression, "stop", stop)
    app = FastAPI(lifespan=ses_suppression.lifespan)

    async def exercise():
        async with app.router.lifespan_context(app):
            start.assert_called_once_with()
            stop.assert_not_called()
            if fail_during_lifespan:
                raise RuntimeError("simulated app failure")

    if fail_during_lifespan:
        with pytest.raises(RuntimeError, match="simulated app failure"):
            asyncio.run(exercise())
    else:
        asyncio.run(exercise())
    stop.assert_called_once_with()


@pytest.fixture
def sync_db(monkeypatch):
    engine = create_engine("sqlite://")
    for model in (EmailBlacklist, SesSuppressedDestination, SesSuppressionSyncState):
        model.__table__.create(engine)
    reload_cache = MagicMock()
    monkeypatch.setattr("core.blacklist.reload", reload_cache)
    yield engine, reload_cache
    engine.dispose()


def destination(email, reason="BOUNCE", updated_at=UPDATED_AT):
    return {"EmailAddress": email, "Reason": reason, "LastUpdateTime": updated_at}


def client_with_pages(*pages):
    client = MagicMock()
    client.list_suppressed_destinations.side_effect = pages
    return client


def run_sync(engine, client, **kwargs):
    return ses_suppression.sync_once(client=client, region=REGION, db_engine=engine, **kwargs)


def seed(engine, *rows):
    with Session(engine) as db:
        db.add_all(rows)
        db.commit()


def suppressed(email, region=REGION, reason="BOUNCE"):
    return SesSuppressedDestination(region=region, email=email, reason=reason,
                                    last_update_time=UPDATED_AT.replace(tzinfo=None))


def test_pagination_adds_updates_and_deletes_only_current_region(sync_db):
    engine, reload_cache = sync_db
    seed(engine, suppressed("removed@example.com"), suppressed("updated@example.com"),
         suppressed("other-region@example.com", region="us-west-2"),
         EmailBlacklist(email="removed@example.com", reason="manual"))
    client = client_with_pages(
        {"SuppressedDestinationSummaries": [destination(" New@Example.COM ")], "NextToken": "page-two"},
        {"SuppressedDestinationSummaries": [destination("updated@example.com", reason="COMPLAINT")]},
    )

    assert run_sync(engine, client)

    assert client.list_suppressed_destinations.call_args_list == [
        call(PageSize=1000), call(PageSize=1000, NextToken="page-two"),
    ]
    with Session(engine) as db:
        rows = {(row.region, row.email): row for row in db.query(SesSuppressedDestination).all()}
        assert set(rows) == {
            (REGION, "new@example.com"), (REGION, "updated@example.com"),
            ("us-west-2", "other-region@example.com"),
        }
        assert rows[(REGION, "updated@example.com")].reason == "COMPLAINT"
        assert db.query(EmailBlacklist).one().email == "removed@example.com"
        state = db.get(SesSuppressionSyncState, REGION)
        assert state.last_success_at >= state.last_attempt_at
        assert state.last_error is None
    reload_cache.assert_called_once_with()


def test_later_page_failure_keeps_snapshot_and_last_success(sync_db):
    engine, reload_cache = sync_db
    last_success = datetime.utcnow() - timedelta(hours=1)
    seed(engine, suppressed("kept@example.com"),
         SesSuppressionSyncState(region=REGION, last_success_at=last_success))
    failure = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
                          "ListSuppressedDestinations")
    client = client_with_pages(
        {"SuppressedDestinationSummaries": [destination("partial@example.com")], "NextToken": "next"},
        failure,
    )

    assert not run_sync(engine, client)

    with Session(engine) as db:
        assert db.query(SesSuppressedDestination).one().email == "kept@example.com"
        state = db.get(SesSuppressionSyncState, REGION)
        assert state.last_success_at == last_success
        assert state.last_attempt_at > last_success
        assert "AccessDeniedException" in state.last_error
    reload_cache.assert_not_called()


def test_first_sync_failure_is_recorded_and_recovers(sync_db):
    engine, _ = sync_db
    assert not run_sync(engine, client_with_pages(RuntimeError("service unavailable")))
    with Session(engine) as db:
        state = db.get(SesSuppressionSyncState, REGION)
        assert state.last_success_at is None
        assert state.last_attempt_at is not None
        assert state.last_error == "service unavailable"

    assert run_sync(engine, client_with_pages({"SuppressedDestinationSummaries": []}), force=True)
    with Session(engine) as db:
        state = db.get(SesSuppressionSyncState, REGION)
        assert state.last_success_at is not None
        assert state.last_error is None


def test_empty_snapshot_preserves_manual_blacklist_and_other_region(sync_db):
    engine, _ = sync_db
    seed(engine, suppressed("same@example.com"), suppressed("same@example.com", region="us-west-2"),
         EmailBlacklist(email="same@example.com", reason="manual complaint"))

    assert run_sync(engine, client_with_pages({"SuppressedDestinationSummaries": []}))

    with Session(engine) as db:
        assert db.query(SesSuppressedDestination).one().region == "us-west-2"
        assert db.query(EmailBlacklist).one().reason == "manual complaint"


def test_timezone_and_duplicate_email_are_normalized(sync_db):
    engine, _ = sync_db
    shanghai = timezone(timedelta(hours=8))
    newer = datetime(2026, 10, 27, 17, 30, tzinfo=shanghai)
    client = client_with_pages({"SuppressedDestinationSummaries": [
        destination(" DUPLICATE@example.com ", "COMPLAINT", newer),
        destination("duplicate@EXAMPLE.COM", "BOUNCE", UPDATED_AT),
        destination("naive@example.com", updated_at=UPDATED_AT.replace(tzinfo=None)),
    ]})

    assert run_sync(engine, client)

    with Session(engine) as db:
        row = db.query(SesSuppressedDestination).filter_by(email="duplicate@example.com").one()
        assert row.reason == "COMPLAINT"
        assert row.last_update_time == datetime(2026, 10, 27, 9, 30)
        assert row.last_update_time.tzinfo is None
        assert db.query(SesSuppressedDestination).count() == 2


def test_recent_success_skips_repeated_requests_from_another_worker(sync_db):
    engine, reload_cache = sync_db
    seed(engine, SesSuppressionSyncState(region=REGION, last_success_at=datetime.utcnow()))
    client = client_with_pages({"SuppressedDestinationSummaries": []})

    assert not run_sync(engine, client)

    client.list_suppressed_destinations.assert_not_called()
    reload_cache.assert_not_called()
    assert run_sync(engine, client, force=True)


def test_recent_failure_limits_retries_from_another_worker(sync_db):
    engine, _ = sync_db
    assert not run_sync(engine, client_with_pages(RuntimeError("access denied")))
    client = MagicMock()

    assert not run_sync(engine, client)

    client.list_suppressed_destinations.assert_not_called()


def test_failure_lock_check_runs_inside_session_owned_transaction(sync_db, monkeypatch):
    engine, _ = sync_db
    transactions = []

    def check_lock(connection, region):
        transactions.append(connection.in_transaction())
        # Simulate the SQL issued by the MySQL lock check. This must not create
        # an external transaction that Session.commit would leave uncommitted.
        connection.exec_driver_sql("SELECT 1")

    monkeypatch.setattr(ses_suppression, "_check_lock", check_lock)
    assert not run_sync(engine, client_with_pages(RuntimeError("access denied")))

    assert transactions == [True]
    with Session(engine) as db:
        assert db.get(SesSuppressionSyncState, REGION).last_error == "access denied"


def test_snapshot_commit_failure_rolls_back_all_changes(sync_db):
    engine, reload_cache = sync_db
    seed(engine, suppressed("kept@example.com"))

    def fail_destination_insert(mapper, connection, target):
        raise RuntimeError("simulated insert failure")

    event.listen(SesSuppressedDestination, "before_insert", fail_destination_insert)
    try:
        assert not run_sync(engine, client_with_pages({
            "SuppressedDestinationSummaries": [destination("new@example.com")],
        }))
    finally:
        event.remove(SesSuppressedDestination, "before_insert", fail_destination_insert)

    with Session(engine) as db:
        assert db.query(SesSuppressedDestination).one().email == "kept@example.com"
        assert db.get(SesSuppressionSyncState, REGION).last_error == "simulated insert failure"
    reload_cache.assert_not_called()


def test_repeated_pagination_token_does_not_replace_snapshot(sync_db):
    engine, _ = sync_db
    seed(engine, suppressed("kept@example.com"))
    page = {"SuppressedDestinationSummaries": [], "NextToken": "repeated"}

    assert not run_sync(engine, client_with_pages(page, page))

    with Session(engine) as db:
        assert db.query(SesSuppressedDestination).one().email == "kept@example.com"


def test_stop_requested_during_fetch_preserves_snapshot(sync_db):
    engine, reload_cache = sync_db
    seed(engine, suppressed("kept@example.com"))
    stop_event = threading.Event()
    client = MagicMock()

    def fetch(**kwargs):
        stop_event.set()
        return {"SuppressedDestinationSummaries": []}

    client.list_suppressed_destinations.side_effect = fetch
    assert not run_sync(engine, client, stop_event=stop_event)
    with Session(engine) as db:
        assert db.query(SesSuppressedDestination).one().email == "kept@example.com"
    reload_cache.assert_not_called()


def test_local_lock_prevents_concurrent_sync(sync_db):
    engine, _ = sync_db
    client = MagicMock()
    with engine.connect() as connection:
        with ses_suppression._sync_lock(connection, REGION) as acquired:
            assert acquired
            assert not run_sync(engine, client, force=True)
    client.list_suppressed_destinations.assert_not_called()


def test_mysql_advisory_lock_is_released_after_exception():
    connection = MagicMock()
    connection.dialect.name = "mysql"
    connection.engine.url.database = "ses_sender"
    connection.execute.return_value.scalar.return_value = 1

    with pytest.raises(RuntimeError, match="fetch failed"):
        with ses_suppression._sync_lock(connection, REGION) as acquired:
            assert acquired
            ses_suppression._check_lock(connection, REGION)
            raise RuntimeError("fetch failed")

    statements = [str(args.args[0]) for args in connection.execute.call_args_list]
    assert statements == [
        "SELECT GET_LOCK(:name, 0)",
        "SELECT IS_USED_LOCK(:name) = CONNECTION_ID()",
        "SELECT RELEASE_LOCK(:name)",
    ]
    assert connection.commit.call_count == 2


def test_lost_mysql_lock_aborts_before_writing():
    connection = MagicMock()
    connection.dialect.name = "mysql"
    connection.engine.url.database = "ses_sender"
    connection.execute.return_value.scalar.return_value = 0
    with pytest.raises(RuntimeError, match="lock was lost"):
        ses_suppression._check_lock(connection, REGION)
