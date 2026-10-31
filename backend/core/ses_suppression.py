"""Read-only, periodic snapshots of the current account's regional SES suppression list."""

from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timezone, timedelta
import hashlib
import logging
import threading

import boto3
from botocore.config import Config
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.config import (
    AWS_REGION,
    ENABLE_SES_SUPPRESSION_SYNC,
    SES_SUPPRESSION_SYNC_INTERVAL_SECONDS,
)
from core.database import engine
from domain.sending.models import SesSuppressedDestination, SesSuppressionSyncState

logger = logging.getLogger("ses-sender.ses-suppression")
_local_locks = {}
_thread_lock = threading.Lock()
_thread = None
_stop_event = threading.Event()


class _SyncCancelled(Exception):
    pass


def _utc_naive(value):
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _lock_name(connection, region):
    scope = f"{connection.engine.url.database}:{region}"
    return "ses-suppression:" + hashlib.sha256(scope.encode()).hexdigest()[:48]


def _is_mysql(connection):
    return connection.dialect.name in ("mysql", "mariadb")


def _check_lock(connection, region):
    # A dropped connection can be reconnected by SQLAlchemy, losing its advisory lock.
    if _is_mysql(connection):
        owns_lock = connection.execute(
            text("SELECT IS_USED_LOCK(:name) = CONNECTION_ID()"),
            {"name": _lock_name(connection, region)},
        ).scalar()
        if owns_lock != 1:
            raise RuntimeError("SES suppression sync database lock was lost")


@contextmanager
def _sync_lock(connection, region):
    """Hold the same MySQL connection throughout fetch, commit and cache refresh."""
    if _is_mysql(connection):
        name = _lock_name(connection, region)
        acquired = connection.execute(
            text("SELECT GET_LOCK(:name, 0)"), {"name": name},
        ).scalar() == 1
        connection.commit()
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    connection.rollback()
                    connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": name})
                    connection.commit()
                except Exception:
                    # Never return a connection with an unreleased lock to the pool.
                    connection.invalidate()
                    logger.exception("Could not release SES suppression sync lock")
    else:
        with _thread_lock:
            lock = _local_locks.setdefault((id(connection.engine), region), threading.Lock())
        acquired = lock.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                lock.release()


def _check_stopped(stop_event):
    if stop_event is not None and stop_event.is_set():
        raise _SyncCancelled()


def _fetch_snapshot(client, stop_event):
    destinations = {}
    next_token = None
    seen_tokens = set()
    wait_event = stop_event if stop_event is not None else threading.Event()
    while True:
        _check_stopped(stop_event)
        kwargs = {"PageSize": 1000}
        if next_token:
            kwargs["NextToken"] = next_token
        response = client.list_suppressed_destinations(**kwargs)
        for item in response.get("SuppressedDestinationSummaries", []):
            email = item["EmailAddress"].lower().strip()
            if not email:
                raise ValueError("SES returned an empty suppressed email address")
            record = (item["Reason"], _utc_naive(item["LastUpdateTime"]))
            # Pages may overlap while SES changes; retain the newest occurrence.
            if email not in destinations or record[1] >= destinations[email][1]:
                destinations[email] = record
        next_token = response.get("NextToken")
        if not next_token:
            return destinations
        if next_token in seen_tokens:
            raise ValueError("SES returned a repeated suppression pagination token")
        seen_tokens.add(next_token)
        # SES non-sending APIs are limited to one request per second.
        if wait_event.wait(1):
            raise _SyncCancelled()


def sync_once(*, client=None, region=AWS_REGION, db_engine=None, force=False, stop_event=None):
    """Return True after a complete snapshot commit; False when skipped or failed.

    `force` bypasses the attempt interval check, but never bypasses the shared lock.
    Optional client/engine injection supports offline tests without AWS access.
    """
    try:
        with (db_engine if db_engine is not None else engine).connect() as connection:
            with _sync_lock(connection, region) as acquired:
                if not acquired:
                    return False
                with Session(bind=connection, expire_on_commit=False) as db:
                    attempted_at = _now()
                    state = db.get(SesSuppressionSyncState, region)
                    previous_attempts = [value for value in (
                        state.last_attempt_at if state else None,
                        state.last_success_at if state else None,
                    ) if value is not None]
                    if (not force and previous_attempts and attempted_at - max(previous_attempts) <
                            timedelta(seconds=SES_SUPPRESSION_SYNC_INTERVAL_SECONDS)):
                        return False
                    try:
                        _check_stopped(stop_event)
                        owned_client = client is None
                        ses_client = client if client is not None else boto3.client(
                            "sesv2", region_name=region,
                            config=Config(connect_timeout=3, read_timeout=10,
                                          retries={"mode": "standard", "total_max_attempts": 2}),
                        )
                        try:
                            snapshot = _fetch_snapshot(ses_client, stop_event)
                        finally:
                            if owned_client:
                                ses_client.close()
                        _check_stopped(stop_event)
                        _check_lock(db.connection(), region)
                        existing = {row.email: row for row in db.query(SesSuppressedDestination).filter(
                            SesSuppressedDestination.region == region,
                        ).all()}
                        for email, (reason, updated_at) in snapshot.items():
                            row = existing.pop(email, None)
                            if row is None:
                                row = SesSuppressedDestination(region=region, email=email)
                                db.add(row)
                            row.reason = reason
                            row.last_update_time = updated_at
                        for row in existing.values():
                            db.delete(row)
                        if state is None:
                            state = SesSuppressionSyncState(region=region)
                            db.add(state)
                        state.last_attempt_at = attempted_at
                        state.last_success_at = _now()
                        state.last_error = None
                        state.version = (state.version or 0) + 1
                        db.commit()
                    except _SyncCancelled:
                        db.rollback()
                        return False
                    except Exception as exc:
                        db.rollback()
                        logger.exception("SES suppression sync failed for %s; keeping previous snapshot", region)
                        # Let Session own this transaction after rollback; a bare
                        # connection.execute here would prevent Session.commit below.
                        _check_lock(db.connection(), region)
                        state = db.get(SesSuppressionSyncState, region)
                        if state is None:
                            state = SesSuppressionSyncState(region=region)
                            db.add(state)
                        state.last_attempt_at = attempted_at
                        state.last_error = str(exc)[:2000]
                        db.commit()
                        return False
                # Refresh only after the committed snapshot is visible to other sessions.
                from core import blacklist
                try:
                    blacklist.reload()
                except Exception:
                    logger.exception("SES suppression snapshot committed, but cache refresh failed")
                logger.info("Synced %s SES suppressed destinations for %s", len(snapshot), region)
                return True
    except Exception:
        logger.exception("Could not run SES suppression sync for %s", region)
        return False


def _worker(stop_event):
    while not stop_event.is_set():
        sync_once(stop_event=stop_event)
        stop_event.wait(SES_SUPPRESSION_SYNC_INTERVAL_SECONDS)


def start():
    """Start immediately in the background; AWS failures never block app startup."""
    global _thread, _stop_event
    if not ENABLE_SES_SUPPRESSION_SYNC:
        return
    with _thread_lock:
        if _thread is not None and _thread.is_alive():
            return
        _stop_event = threading.Event()
        _thread = threading.Thread(target=_worker, args=(_stop_event,),
                                   name="ses-suppression-sync", daemon=True)
        _thread.start()


def stop():
    """Interrupt interval waits and pagination; in-flight requests have bounded timeouts."""
    with _thread_lock:
        _stop_event.set()
        thread = _thread
    if thread is not None:
        thread.join(timeout=30)
        if thread.is_alive():
            logger.warning("SES suppression sync is still finishing an in-flight request")


@asynccontextmanager
async def lifespan(app):
    """FastAPI lifespan hook, including versions without add_event_handler."""
    start()
    try:
        yield
    finally:
        stop()
