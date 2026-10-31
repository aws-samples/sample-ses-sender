"""Shared database predicates for display, whole-group checks and selection.

The regional SES mirror is the persistent cache. Queries never call AWS and use
indexed EXISTS lookups, so filtering is authoritative before pagination. Sharing
these predicates avoids display/filter disagreements and stale Redis decisions.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import and_, cast, func, literal, not_, or_, select
from sqlalchemy.dialects.mysql import BINARY

from domain.audience.models import Contact
from domain.sending.models import (EmailBlacklist, SendingJob, SendingJobDetail,
                                  SesSuppressedDestination, SesSuppressionSyncState,
                                  UnsubscribeRecord)

FLAGS = ("bounced", "manual", "ses", "unsubscribed", "unmatched", "unknown")


def parse_flags(flags):
    values = flags.split(",") if isinstance(flags, str) else (flags or [])
    values = {value.strip() for value in values if value.strip()}
    if values - set(FLAGS):
        raise HTTPException(status_code=400, detail="不支持的联系人状态筛选")
    return values


def exact_equal(db, column, value):
    # MySQL's default collation is case insensitive. Keep the ordinary indexed
    # comparison and add byte equality to match the producer's Python sets,
    # including trailing spaces (MySQL's older binary collations ignore them).
    if db.bind.dialect.name in ("mysql", "mariadb"):
        # Preserve a string bind type before CAST; otherwise PyMySQL expects a
        # Python bytes object when SQLAlchemy infers BINARY for a raw string.
        compared = literal(value) if isinstance(value, str) else value
        return and_(column == value, cast(column, BINARY) == cast(compared, BINARY))
    return column == value


def normalized_equal(db, column, normalized):
    stored = func.lower(func.trim(column))
    if db.bind.dialect.name in ("mysql", "mariadb"):
        # Keep indexable candidate equality, then match cache normalization
        # exactly. The guard also supports mixed-case legacy stored addresses.
        return and_(column == normalized, cast(stored, BINARY) == cast(normalized, BINARY))
    return stored == normalized


def case_insensitive_equal(db, column, value):
    stored = func.lower(column)
    normalized = func.lower(value)
    if db.bind.dialect.name in ("mysql", "mariadb"):
        # The ordinary equality keeps the existing email index usable; the
        # binary lowercase check avoids the collation's accent/space folding.
        return and_(column == value, cast(stored, BINARY) == cast(normalized, BINARY))
    return stored == normalized


class ContactStatusQuery:
    def __init__(self, db, user_id, source_email):
        from core.config import AWS_REGION, ENABLE_SES_SUPPRESSION_SYNC, SES_SUPPRESSION_SYNC_INTERVAL_SECONDS
        self.source_email = source_email
        state = db.query(SesSuppressionSyncState).filter_by(region=AWS_REGION).first()
        self.last_success = state.last_success_at if state else None
        if not ENABLE_SES_SUPPRESSION_SYNC:
            status = "disabled"
        elif state and state.last_error:
            status = "error"
        elif not self.last_success:
            status = "pending"
        elif (datetime.utcnow() - self.last_success).total_seconds() > max(60, SES_SUPPRESSION_SYNC_INTERVAL_SECONDS) * 2 + 60:
            status = "stale"
        else:
            status = "ready"
        self.sync_info = {
            "status": status,
            "last_synced_at": self.last_success.replace(tzinfo=timezone.utc).isoformat() if self.last_success else None,
            "region": AWS_REGION,
        }
        normalized = func.lower(func.trim(Contact.email))
        # Cache normalization lowercases and trims, but does not remove accents.
        manual = select(1).where(normalized_equal(db, EmailBlacklist.email, normalized)).correlate(Contact).exists()
        ses_where = (SesSuppressedDestination.region == AWS_REGION,
                     normalized_equal(db, SesSuppressedDestination.email, normalized))
        ses = select(1).where(*ses_where).correlate(Contact).exists()
        self.ses_reason = select(SesSuppressedDestination.reason).where(*ses_where).correlate(Contact).limit(1).scalar_subquery()
        # Sending loads records using the database's sender collation, then
        # compares case-folded recipients without trimming them.
        unsubscribed = (
            select(1).where(UnsubscribeRecord.source_email == source_email,
                            case_insensitive_equal(db, UnsubscribeRecord.email, Contact.email)).correlate(Contact).exists()
            if source_email else literal(False)
        )
        # Probe the recipient index before joining to its owner's job. MySQL can
        # otherwise choose the owner first and rescan all of their history for
        # every contact during aggregate validation; fix only that join order.
        bounced = select(1).select_from(SendingJobDetail).join(
            SendingJob, SendingJob.id == SendingJobDetail.job_id
        ).where(
            SendingJob.user_id == user_id,
            exact_equal(db, SendingJobDetail.recipient, Contact.email),
            or_(SendingJobDetail.delivery_status == "Bounce", SendingJobDetail.bounce_type.is_not(None)),
        ).prefix_with("STRAIGHT_JOIN", dialect="mysql").correlate(Contact).exists()
        unknown = literal(status != "ready" or not source_email)
        self.predicates = {
            "bounced": bounced, "manual": manual, "ses": ses, "unsubscribed": unsubscribed,
            "unmatched": not_(or_(bounced, manual, ses, unsubscribed, unknown)), "unknown": unknown,
        }

    def filter_query(self, query, search="", flags=None):
        if search:
            query = query.filter(or_(Contact.name.ilike(f"%{search}%"), Contact.email.ilike(f"%{search}%")))
        selected = parse_flags(flags)
        if selected:
            query = query.filter(or_(*(self.predicates[flag] for flag in FLAGS if flag in selected)))
        return query

    def columns(self):
        return [self.predicates[flag].label(flag) for flag in FLAGS if flag != "unmatched"] + [self.ses_reason.label("ses_reason")]

    def status_dict(self, row):
        sources = (["manual"] if row.manual else []) + (["ses"] if row.ses else [])
        return {
            "is_blacklisted": bool(sources), "blacklist_sources": sources,
            "is_ses_suppressed": bool(row.ses) if self.last_success or row.ses else None,
            "ses_suppression_reason": row.ses_reason,
            "is_unsubscribed": bool(row.unsubscribed) if self.source_email else None,
            "has_bounced": bool(row.bounced), "status_unknown": bool(row.unknown),
        }
