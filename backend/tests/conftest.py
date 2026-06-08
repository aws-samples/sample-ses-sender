"""Shared test fixtures."""
import sys
import os
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import all models to resolve SQLAlchemy relationships
import domain.auth.models  # noqa: F401
import domain.audience.models  # noqa: F401
import domain.template.models  # noqa: F401
import domain.sending.models  # noqa: F401


@pytest.fixture
def mock_db():
    """Mock SQLAlchemy Session."""
    db = MagicMock()
    db.query.return_value = db
    db.filter.return_value = db
    db.first.return_value = None
    db.all.return_value = []
    db.count.return_value = 0
    return db


@pytest.fixture
def mock_ses():
    """Mock SES v2 client."""
    with patch("core.ses.sesv2_client") as m:
        m.send_email.return_value = {"MessageId": "test-msg-id-123"}
        m.create_email_template.return_value = {}
        m.update_email_template.return_value = {}
        yield m


@pytest.fixture
def sample_task():
    """Create a sample SendTask for testing."""
    from core.sender import SendTask
    return SendTask(
        job_id=1,
        batch_id="batch-test123",
        recipient="user@example.com",
        name="Test User",
        source_email="sender@example.com",
        reply_to="reply@example.com",
        subject_tpl="Hello {{name}}",
        html_tpl="<p>Hi {{name}}, your email is {{email}}. Link: {{link}}</p>",
        text_tpl="",
        attributes={"link": "https://example.com"},
        config_set="test-config",
        tags={"batch_id": "batch-test123", "user_id": "1"},
        unsub_url="https://unsub.example.com/token123",
        attachments=[],
        detail_id=42,
    )
