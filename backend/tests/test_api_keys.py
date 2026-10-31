"""User API Key authentication and scope regression tests."""

import hashlib
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from core.deps import _authenticate_api_key, _required_scope
from domain.auth.api_keys import create_api_key
from domain.auth.models import ApiKey
from domain.auth.schemas import ApiKeyCreate


def _request(method: str, path: str) -> Request:
    return Request({"type": "http", "method": method, "path": path, "headers": [], "query_string": b""})


@pytest.mark.parametrize(
    ("method", "path", "scope"),
    [
        ("GET", "/groups", "audience:read"),
        ("POST", "/contacts", "audience:write"),
        ("GET", "/user/templates", "templates:read"),
        ("POST", "/send-bulk", "sending:write"),
        ("GET", "/sending-jobs", "sending:read"),
        ("DELETE", "/scheduled-jobs/1", "scheduled:write"),
        ("GET", "/admin/users", "admin:read"),
        ("POST", "/admin/users", "admin:write"),
    ],
)
def test_scope_mapping(method, path, scope):
    assert _required_scope(_request(method, path)) == scope


def test_api_key_authenticates_and_updates_last_used():
    user = SimpleNamespace(is_active=True)
    item = SimpleNamespace(
        user=user,
        scopes=json.dumps(["audience:read"]),
        revoked_at=None,
        expires_at=datetime.utcnow() + timedelta(days=1),
        last_used_at=None,
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = item

    result = _authenticate_api_key("ses_live_test", _request("GET", "/groups"), db)

    assert result is user
    assert item.last_used_at is not None
    db.commit.assert_called_once()
    expected_hash = hashlib.sha256(b"ses_live_test").hexdigest()
    assert str(db.query.return_value.filter.call_args.args[0].right.value) == expected_hash


def test_api_key_rejects_missing_scope():
    item = SimpleNamespace(
        user=SimpleNamespace(is_active=True),
        scopes=json.dumps(["audience:read"]),
        revoked_at=None,
        expires_at=None,
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = item

    with pytest.raises(HTTPException) as exc:
        _authenticate_api_key("ses_live_test", _request("POST", "/contacts"), db)

    assert exc.value.status_code == 403
    assert "audience:write" in exc.value.detail
    db.commit.assert_not_called()


def test_create_api_key_hashes_secret_and_returns_plaintext_once():
    db = MagicMock()
    db.refresh.side_effect = lambda item: (
        setattr(item, "id", 7),
        setattr(item, "created_at", datetime.utcnow()),
    )
    user = SimpleNamespace(id=3, is_admin=False)

    result = create_api_key(
        ApiKeyCreate(name="Claude MCP", scopes=["sending:read", "sending:read"]),
        current_user=user,
        db=db,
    )

    item = db.add.call_args.args[0]
    assert isinstance(item, ApiKey)
    assert result["api_key"].startswith("ses_live_")
    assert item.key_hash == hashlib.sha256(result["api_key"].encode()).hexdigest()
    assert json.loads(item.scopes) == ["sending:read"]
    assert result["key_prefix"] != result["api_key"]


def test_non_admin_cannot_create_admin_scope():
    with pytest.raises(HTTPException) as exc:
        create_api_key(
            ApiKeyCreate(name="invalid", scopes=["admin:read"]),
            current_user=SimpleNamespace(id=3, is_admin=False),
            db=MagicMock(),
        )
    assert exc.value.status_code == 403
