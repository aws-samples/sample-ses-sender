"""Group-wide status validation, filtering and safe batch removal."""
from datetime import datetime, timedelta
from unittest.mock import patch
import os

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from core.config import AWS_REGION
from core.database import Base
from domain.auth.models import User
from domain.audience.models import Contact, ContactGroup
from domain.audience import service
from domain.sending.models import (EmailBlacklist, SendingJob, SendingJobDetail,
                                  UnsubscribeRecord, SesSuppressedDestination,
                                  SesSuppressionSyncState)


@pytest.fixture
def db():
    engine = create_engine(os.environ.get("TEST_GROUP_DATABASE_URL", "sqlite://"))
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(engine)
    connection = engine.connect()
    # SQLite's legacy transaction mode needs an explicit BEGIN before SAVEPOINT.
    if engine.dialect.name == "sqlite":
        connection.exec_driver_sql("BEGIN")
        transaction = connection.get_transaction()
    else:
        transaction = connection.begin()
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        session.add_all([User(id=1, username="owner", email="sender@example.com"),
                         User(id=2, username="other", email="other@example.com")])
        session.flush()
        session.add_all([ContactGroup(id=1, name="Audience", user_id=1),
                         ContactGroup(id=2, name="Other owner", user_id=2),
                         ContactGroup(id=3, name="Other group", user_id=1),
                         SesSuppressionSyncState(region=AWS_REGION, last_success_at=datetime.utcnow()),
                         SendingJob(id=1, user_id=1, batch_id="mine"),
                         SendingJob(id=2, user_id=2, batch_id="theirs")])
        session.flush()
        session.add_all([
            Contact(id=1, group_id=1, email="normal@example.com", name="Normal"),
            Contact(id=2, group_id=1, email="bounced@example.com", name="Bounce"),
            Contact(id=3, group_id=1, email="manual@example.com", name="Manual"),
            Contact(id=4, group_id=1, email="ses@example.com", name="SES"),
            Contact(id=5, group_id=1, email="unsub@example.com", name="Unsubscribed"),
            Contact(id=6, group_id=1, email="both@example.com", name="Both"),
            Contact(id=7, group_id=1, email="other-history@example.com", name="Private"),
            Contact(id=8, group_id=3, email="both@example.com", name="Same email, other group"),
            Contact(id=9, group_id=2, email="private@example.com"),
            EmailBlacklist(email="manual@example.com"), EmailBlacklist(email="both@example.com"),
            UnsubscribeRecord(email="unsub@example.com", source_email="sender@example.com"),
            UnsubscribeRecord(email="both@example.com", source_email="sender@example.com"),
            SendingJobDetail(job_id=1, recipient="bounced@example.com", delivery_status="Delivery", bounce_type="Transient"),
            SendingJobDetail(job_id=2, recipient="other-history@example.com", delivery_status="Bounce"),
            SesSuppressedDestination(region=AWS_REGION, email="ses@example.com", reason="BOUNCE", last_update_time=datetime.utcnow()),
        ])
        session.commit()
        with patch("core.config.ENABLE_SES_SUPPRESSION_SYNC", True):
            yield session
    transaction.rollback()
    connection.close()
    engine.dispose()


def test_validation_counts_entire_group_and_history_is_private(db):
    result = service.validate_group(db, 1, 1)
    assert result["total"] == 7
    assert result["counts"] == {"bounced": 1, "manual": 2, "ses": 1, "unsubscribed": 2,
                                 "unmatched": 2, "unknown": 0}
    assert result["checked_at"].endswith("+00:00")
    items = {row["id"]: row for row in service.list_contacts(db, 1, 1).items}
    assert items[2]["has_bounced"] is True  # Later delivery must not erase bounce history.
    assert items[7]["has_bounced"] is False


def test_or_filter_is_applied_before_pagination_and_search(db):
    result = service.list_contacts(db, 1, 1, page=2, page_size=1, flags="manual,unsubscribed")
    assert result.total == 3
    assert result.total_pages == 3
    assert [row["id"] for row in result.items] == [5]
    result = service.list_contacts(db, 1, 1, search="Both", flags="manual,unsubscribed")
    assert result.total == 1
    assert result.items[0]["id"] == 6
    with pytest.raises(HTTPException) as exc:
        service.list_contacts(db, 1, 1, flags="typo")
    assert exc.value.status_code == 400


@pytest.mark.parametrize("state", ["stale", "error", "pending", "disabled", "missing_sender"])
def test_unknown_is_never_unmatched_but_known_positives_remain(db, state):
    sync = db.get(SesSuppressionSyncState, AWS_REGION)
    if state == "stale":
        sync.last_success_at = datetime.utcnow() - timedelta(days=1)
    elif state == "error":
        sync.last_error = "Internal secret error"
    elif state == "pending":
        sync.last_success_at = None
    elif state == "missing_sender":
        db.get(User, 1).email = None
    db.commit()
    with patch("core.config.ENABLE_SES_SUPPRESSION_SYNC", state != "disabled"):
        assert service.list_contacts(db, 1, 1, flags="unmatched").total == 0
        assert service.list_contacts(db, 1, 1, flags="unknown").total == 7
        positive = service.list_contacts(db, 1, 1, flags="ses").items[0]
        assert positive["is_ses_suppressed"] is True
        assert positive["status_unknown"] is True
        assert "secret" not in str(service.validate_group(db, 1, 1))


def test_filter_and_display_have_identical_matching_semantics(db):
    db.add_all([
        Contact(id=10, group_id=1, email=" Manual@Example.COM "),
        Contact(id=11, group_id=1, email="Unsub@example.com"),
        Contact(id=12, group_id=1, email="BOUNCED@example.com"),
    ])
    db.commit()
    all_items = service.list_contacts(db, 1, 1, page_size=100).items
    expected = {
        "manual": {i["id"] for i in all_items if "manual" in i["blacklist_sources"]},
        "ses": {i["id"] for i in all_items if i["is_ses_suppressed"]},
        "unsubscribed": {i["id"] for i in all_items if i["is_unsubscribed"]},
        "bounced": {i["id"] for i in all_items if i["has_bounced"]},
    }
    assert 10 in expected["manual"]
    assert 11 not in expected["unsubscribed"]
    assert 12 not in expected["bounced"]
    for flag, ids in expected.items():
        assert {i["id"] for i in service.list_contacts(db, 1, 1, flags=flag).items} == ids


def test_snapshot_freezes_all_filtered_ids_and_preserves_source_records(db):
    selection = service.create_contact_selection(db, 1, 1, search="", flags=["manual", "unsubscribed"])
    assert selection["selected_count"] == 3
    db.add(Contact(id=10, group_id=1, email="manual@example.com"))
    # Changed flags do not alter the fixed selection.
    db.query(EmailBlacklist).filter_by(email="manual@example.com").delete()
    db.commit()
    assert service.bulk_delete_contacts(db, 1, 1, selection_id=selection["selection_id"]) == {"deleted_count": 3}
    assert db.get(Contact, 10) is not None
    assert db.get(Contact, 8) is not None
    assert db.query(UnsubscribeRecord).count() == 2
    assert db.query(EmailBlacklist).count() == 1
    assert db.query(SesSuppressedDestination).count() == 1
    assert db.query(SendingJobDetail).count() == 2
    with pytest.raises(HTTPException) as exc:
        service.bulk_delete_contacts(db, 1, 1, selection_id=selection["selection_id"])
    assert exc.value.status_code in (404, 409, 410)


def test_new_snapshot_replaces_only_same_user_group_snapshot(db):
    from domain.audience.models import ContactSelection, ContactSelectionItem

    old = service.create_contact_selection(db, 1, 1, flags=["manual"])
    same_user_other_group = service.create_contact_selection(db, 3, 1)
    other_user = service.create_contact_selection(db, 2, 2)
    assert db.query(ContactSelection).count() == 3
    assert db.query(ContactSelectionItem).count() == 4

    replacement = service.create_contact_selection(db, 1, 1, flags=["ses"])

    assert db.get(ContactSelection, old["selection_id"]) is None
    assert db.query(ContactSelectionItem).filter_by(selection_id=old["selection_id"]).count() == 0
    assert db.get(ContactSelection, replacement["selection_id"]) is not None
    assert db.get(ContactSelection, same_user_other_group["selection_id"]) is not None
    assert db.get(ContactSelection, other_user["selection_id"]) is not None
    assert db.query(ContactSelection).count() == 3
    assert db.query(ContactSelectionItem).count() == 3

    with pytest.raises(HTTPException) as exc:
        service.bulk_delete_contacts(db, 1, 1, selection_id=old["selection_id"])
    assert exc.value.status_code == 404


def test_explicit_ids_are_atomic_and_cannot_escape_group(db):
    for ids in ([1, 8], [1, 9], [1, 999]):
        with pytest.raises(HTTPException):
            service.bulk_delete_contacts(db, 1, 1, contact_ids=ids)
        assert db.get(Contact, 1) is not None
    assert service.bulk_delete_contacts(db, 1, 1, contact_ids=[1, 1, 2]) == {"deleted_count": 2}
    assert db.get(Contact, 8) is not None


def test_endpoints_enforce_ownership_and_snapshot_scope(db):
    selection = service.create_contact_selection(db, 1, 1, flags=["manual"])
    for call in (
        lambda: service.validate_group(db, 1, 2),
        lambda: service.create_contact_selection(db, 1, 2),
        lambda: service.bulk_delete_contacts(db, 1, 2, contact_ids=[1]),
        lambda: service.bulk_delete_contacts(db, 2, 2, selection_id=selection["selection_id"]),
        lambda: service.bulk_delete_contacts(db, 3, 1, selection_id=selection["selection_id"]),
    ):
        with pytest.raises(HTTPException) as exc:
            call()
        assert exc.value.status_code == 404
    assert db.query(Contact).count() == 9


def test_expired_selection_is_not_deleted(db):
    from domain.audience.models import ContactSelection
    selection = service.create_contact_selection(db, 1, 1)
    db.get(ContactSelection, selection["selection_id"]).expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        service.bulk_delete_contacts(db, 1, 1, selection_id=selection["selection_id"])
    assert exc.value.status_code == 410
    assert db.query(Contact).count() == 9


def test_empty_and_mixed_delete_requests_rejected(db):
    for kwargs in ({}, {"contact_ids": []}, {"contact_ids": [1], "selection_id": "x"}, {"contact_ids": [True]}):
        with pytest.raises(HTTPException) as exc:
            service.bulk_delete_contacts(db, 1, 1, **kwargs)
        assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        service.create_contact_selection(db, 1, 1, search="no matches")
    assert exc.value.status_code == 400


def test_queries_are_bounded_independent_of_contact_count(db):
    counts = []
    for size in (1, 100):
        db.expire_all()
        statements = []
        def capture(*args):
            if args[2].lstrip().upper().startswith("SELECT"):
                statements.append(args[2])
        event.listen(db.bind, "before_cursor_execute", capture)
        try:
            service.list_contacts(db, 1, 1, page_size=size, flags="manual,unsubscribed")
        finally:
            event.remove(db.bind, "before_cursor_execute", capture)
        counts.append(len(statements))
    assert counts[0] == counts[1]
    assert counts[0] <= 6


def test_exact_recipient_comparison_preserves_trailing_spaces(db):
    db.add_all([
        Contact(id=10, group_id=1, email="unsub@example.com "),
        Contact(id=11, group_id=1, email="bounced@example.com "),
    ])
    db.commit()
    items = {row["id"]: row for row in service.list_contacts(db, 1, 1).items}
    assert items[10]["is_unsubscribed"] is False
    assert items[11]["has_bounced"] is False
    assert service.list_contacts(db, 1, 1, flags="unmatched").total == 4


def test_empty_group_validation_and_expired_selection_cleanup(db):
    from domain.audience.models import ContactSelection, ContactSelectionItem
    snapshot = service.create_contact_selection(db, 1, 1, flags=["manual"])
    db.get(ContactSelection, snapshot["selection_id"]).expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    service.create_contact_selection(db, 1, 1, flags=["ses"])
    assert db.get(ContactSelection, snapshot["selection_id"]) is None
    assert db.query(ContactSelectionItem).filter_by(selection_id=snapshot["selection_id"]).count() == 0
    service.bulk_delete_contacts(db, 3, 1, contact_ids=[8])
    result = service.validate_group(db, 3, 1)
    assert result["total"] == 0
    assert set(result["counts"].values()) == {0}


def test_snapshot_tolerates_prior_deletion_without_selecting_new_contacts(db):
    snapshot = service.create_contact_selection(db, 1, 1, flags=["manual"])
    service.delete_contact(db, 3, 1)
    db.add(Contact(id=10, group_id=1, email="manual@example.com"))
    db.commit()
    assert service.bulk_delete_contacts(db, 1, 1, selection_id=snapshot["selection_id"])["deleted_count"] == 1
    assert db.get(Contact, 10) is not None


def test_request_schemas_reject_ambiguous_or_invalid_selection(db):
    from pydantic import ValidationError
    from domain.audience.schemas import ContactBulkDelete, ContactSelectionCreate
    for payload in ({}, {"contact_ids": []}, {"contact_ids": [True]},
                    {"contact_ids": [1], "selection_id": "x"}, {"contact_ids": [1], "all": True}):
        with pytest.raises(ValidationError):
            ContactBulkDelete.model_validate(payload)
    with pytest.raises(ValidationError):
        ContactSelectionCreate.model_validate({"flags": ["invalid"]})
    assert ContactBulkDelete.model_validate({"contact_ids": [1]}).contact_ids == [1]
    assert db.query(Contact).count() == 9


@pytest.mark.parametrize("sender", ["SENDER@EXAMPLE.COM", "sénder@example.com"])
def test_unsubscribe_sender_scope_matches_sending_database_collation(db, sender):
    db.get(User, 1).email = sender
    db.commit()
    # Sending loads the sender's records with ordinary SQL equality, then uses
    # exact recipient strings in a Python set. Preserve both halves of that rule.
    producer_recipients = {row[0] for row in db.query(UnsubscribeRecord.email).filter(
        UnsubscribeRecord.source_email == sender
    ).all()}
    if db.bind.dialect.name in ("mysql", "mariadb"):
        assert producer_recipients == {"unsub@example.com", "both@example.com"}
    result = service.list_contacts(db, 1, 1)
    expected_ids = {row["id"] for row in result.items if row["email"] in producer_recipients}
    assert {row["id"] for row in result.items if row["is_unsubscribed"]} == expected_ids
    assert {row["id"] for row in service.list_contacts(db, 1, 1, flags="unsubscribed").items} == expected_ids
    assert not expected_ids.intersection(row["id"] for row in service.list_contacts(db, 1, 1, flags="unmatched").items)
    assert service.validate_group(db, 1, 1)["counts"]["unsubscribed"] == len(expected_ids)


def test_normalized_blacklists_preserve_accents_like_sending_cache(db):
    db.add_all([
        Contact(id=10, group_id=1, email="mánual@example.com"),
        Contact(id=11, group_id=1, email="sés@example.com"),
    ])
    db.commit()
    items = {row["id"]: row for row in service.list_contacts(db, 1, 1).items}
    assert items[10]["is_blacklisted"] is False
    assert items[11]["is_ses_suppressed"] is False
    assert service.list_contacts(db, 1, 1, flags="manual").total == 2
    assert service.list_contacts(db, 1, 1, flags="ses").total == 1
    assert {10, 11}.issubset(row["id"] for row in service.list_contacts(db, 1, 1, flags="unmatched").items)


def test_mixed_case_stored_blacklist_matches_cache_normalization(db):
    db.query(EmailBlacklist).filter_by(email="manual@example.com").one().email = "MANUAL@EXAMPLE.COM"
    db.query(SesSuppressedDestination).filter_by(email="ses@example.com").one().email = "SES@EXAMPLE.COM"
    db.commit()
    items = {row["id"]: row for row in service.list_contacts(db, 1, 1).items}
    assert items[3]["blacklist_sources"] == ["manual"]
    assert items[4]["blacklist_sources"] == ["ses"]
    assert service.list_contacts(db, 1, 1, flags="manual").total == 2
    assert service.list_contacts(db, 1, 1, flags="ses").total == 1
