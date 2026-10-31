"""Tests for core/sender.py — SenderEngine core logic."""
import sys
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, mock_open
from dataclasses import dataclass, field

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.sender import SenderEngine, SendTask


class TestFormatFromAddress:
    """Tests for core.sender.format_from_address (Friendly From)."""

    def test_no_name_returns_email(self):
        from core.sender import format_from_address
        assert format_from_address("noreply@x.com", "") == "noreply@x.com"
        assert format_from_address("noreply@x.com", None) == "noreply@x.com"

    def test_ascii_name(self):
        from core.sender import format_from_address
        assert format_from_address("noreply@cooking-madness.com", "Cooking") == "Cooking <noreply@cooking-madness.com>"

    def test_name_stripped(self):
        from core.sender import format_from_address
        assert format_from_address("a@b.com", "  Team  ") == "Team <a@b.com>"

    def test_non_ascii_name_rfc2047(self):
        from core.sender import format_from_address
        out = format_from_address("a@b.com", "厨房")
        # 非 ASCII 名字应被 RFC 2047 编码，且邮箱保留
        assert "<a@b.com>" in out
        assert "=?utf-8?" in out.lower()


class TestResolveJobReplyTo:
    """Tests for preserving the Reply-To snapshot stored on a sending job."""

    def test_job_snapshot_wins_over_changed_user_contact(self):
        from core.sender import resolve_job_reply_to

        job = SimpleNamespace(
            reply_to="snapshot@example.com",
            source_email="sender@example.com",
        )
        user = SimpleNamespace(contact_email="changed@example.com")

        assert resolve_job_reply_to(job, user) == "snapshot@example.com"

    def test_legacy_job_falls_back_to_current_user_contact(self):
        from core.sender import resolve_job_reply_to

        job = SimpleNamespace(reply_to="", source_email="sender@example.com")
        user = SimpleNamespace(contact_email="contact@example.com")

        assert resolve_job_reply_to(job, user) == "contact@example.com"

    def test_missing_user_contact_falls_back_to_source_email(self):
        from core.sender import resolve_job_reply_to

        job = SimpleNamespace(source_email="sender@example.com")

        assert resolve_job_reply_to(job) == "sender@example.com"


class TestReplaceVars:
    """Tests for SenderEngine._replace_vars"""

    def setup_method(self):
        self.engine = SenderEngine.__new__(SenderEngine)

    def _task(self, **kwargs):
        defaults = dict(
            job_id=1, batch_id="b1", recipient="user@test.com", name="Alice",
            source_email="s@t.com", reply_to="", subject_tpl="", html_tpl="",
            text_tpl="", attributes={}, config_set="", tags={},
            unsub_url="", attachments=[], detail_id=0,
        )
        defaults.update(kwargs)
        return SendTask(**defaults)

    def test_replace_vars_basic(self):
        task = self._task(name="Bob", recipient="bob@test.com")
        result = self.engine._replace_vars("Hello {{name}}, email: {{email}}", task)
        assert result == "Hello Bob, email: bob@test.com"

    def test_replace_vars_custom_attrs(self):
        task = self._task(attributes={"link": "https://example.com", "company": "Acme"})
        result = self.engine._replace_vars("Visit {{link}} at {{company}}", task)
        assert result == "Visit https://example.com at Acme"

    def test_replace_vars_unsubscribe_url(self):
        task = self._task(unsub_url="https://unsub.test/abc")
        result = self.engine._replace_vars('<a href="{{unsubscribe_url}}">Unsub</a>', task)
        assert result == '<a href="https://unsub.test/abc">Unsub</a>'

    def test_replace_vars_unsubscribe_url_empty(self):
        task = self._task(unsub_url="")
        result = self.engine._replace_vars('<a href="{{unsubscribe_url}}">Unsub</a>', task)
        assert result == '<a href="#">Unsub</a>'

    def test_replace_vars_empty_template(self):
        task = self._task()
        result = self.engine._replace_vars("", task)
        assert result == ""

    def test_replace_vars_no_placeholders(self):
        task = self._task()
        result = self.engine._replace_vars("Plain text no vars", task)
        assert result == "Plain text no vars"


class TestExtractError:
    """Tests for SenderEngine._extract_error"""

    def test_ses_format(self):
        err = 'An error occurred (BadRequestException) when calling the SendEmail operation: Domain starts with dot'
        result = SenderEngine._extract_error(err)
        assert result == "[BadRequestException] Domain starts with dot"

    def test_ses_message_rejected(self):
        err = 'An error occurred (MessageRejected) when calling the SendEmail operation: Email address is not verified.'
        result = SenderEngine._extract_error(err)
        assert result == "[MessageRejected] Email address is not verified."

    def test_non_ses_format(self):
        err = "Some random error message that is very long " * 5
        result = SenderEngine._extract_error(err)
        assert len(result) <= 200

    def test_short_non_ses(self):
        err = "Connection timeout"
        result = SenderEngine._extract_error(err)
        assert result == "Connection timeout"


class TestSendOneBlacklist:
    """Tests for blacklist check in _send_one"""

    def setup_method(self):
        self.engine = SenderEngine.__new__(SenderEngine)
        self.engine._stats_lock = __import__("threading").Lock()
        self.engine._total_sent = 0
        self.engine._total_errors = 0

    @patch("core.blacklist.is_blacklisted", return_value=True)
    @patch("core.sender.update_detail_status")
    def test_send_one_blacklist_skip(self, mock_update, mock_bl):
        task = SendTask(
            job_id=1, batch_id="b1", recipient="blocked@test.com", name="X",
            source_email="s@t.com", reply_to="", subject_tpl="Hi", html_tpl="<p>Hi</p>",
            text_tpl="", attributes={}, config_set="", tags={},
            unsub_url="", attachments=[], detail_id=1,
        )
        self.engine._send_one(task, 0)
        mock_update.assert_called_once_with(task, "Failed", "[Blacklisted] 邮箱在黑名单中")
        assert self.engine._total_errors == 1

    @patch("core.blacklist.is_blacklisted", return_value=False)
    @patch("core.database.SessionLocal")
    @patch("core.sender.update_detail_status")
    def test_send_one_duplicate_skip(self, mock_update, mock_session_cls, mock_bl):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_detail = MagicMock()
        mock_detail.send_status = "Success"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_detail

        task = SendTask(
            job_id=1, batch_id="b1", recipient="done@test.com", name="X",
            source_email="s@t.com", reply_to="", subject_tpl="Hi", html_tpl="<p>Hi</p>",
            text_tpl="", attributes={}, config_set="", tags={},
            unsub_url="", attachments=[], detail_id=5,
        )
        self.engine._send_one(task, 0)
        mock_update.assert_not_called()

    @patch("core.blacklist.is_blacklisted", return_value=False)
    @patch("core.database.SessionLocal")
    @patch("core.ses.sesv2_client")
    @patch("core.sender.update_detail_status")
    def test_send_one_success(self, mock_update, mock_ses, mock_session_cls, mock_bl):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_detail = MagicMock()
        mock_detail.send_status = "Pending"
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_detail
        mock_db.query.return_value.filter.return_value.first.return_value = mock_detail
        mock_ses.send_email.return_value = {"MessageId": "msg-abc"}

        task = SendTask(
            job_id=1, batch_id="b1", recipient="user@test.com", name="User",
            source_email="s@t.com", reply_to="s@t.com", subject_tpl="Hello {{name}}",
            html_tpl="<p>Hi {{name}}</p>", text_tpl="", attributes={},
            config_set="my-config", tags={"batch_id": "b1"}, unsub_url="",
            attachments=[], detail_id=10,
        )
        self.engine._send_one(task, 0)
        mock_ses.send_email.assert_called_once()
        call_args = mock_ses.send_email.call_args
        assert call_args[1]["Destination"]["ToAddresses"] == ["user@test.com"]
        mock_update.assert_called_once_with(task, "Success", "", "msg-abc")
        assert self.engine._total_sent == 1

    @patch("core.blacklist.is_blacklisted", return_value=False)
    @patch("core.database.SessionLocal")
    @patch("core.ses.sesv2_client")
    @patch("core.sender.update_detail_status")
    def test_send_one_failure(self, mock_update, mock_ses, mock_session_cls, mock_bl):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_detail = MagicMock()
        mock_detail.send_status = "Pending"
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_detail
        mock_db.query.return_value.filter.return_value.first.return_value = mock_detail
        mock_ses.send_email.side_effect = Exception(
            "An error occurred (BadRequestException) when calling the SendEmail operation: Invalid email"
        )

        task = SendTask(
            job_id=1, batch_id="b1", recipient="bad@test.com", name="X",
            source_email="s@t.com", reply_to="", subject_tpl="Hi", html_tpl="<p>Hi</p>",
            text_tpl="", attributes={}, config_set="", tags={},
            unsub_url="", attachments=[], detail_id=11,
        )
        self.engine._send_one(task, 0)
        mock_update.assert_called_once_with(task, "Failed", "[BadRequestException] Invalid email")
        assert self.engine._total_errors == 1

    @patch("core.blacklist.is_blacklisted", return_value=False)
    @patch("core.database.SessionLocal")
    @patch("core.ses.sesv2_client")
    @patch("core.sender.update_detail_status")
    def test_send_one_with_attachments(self, mock_update, mock_ses, mock_session_cls, mock_bl):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_detail = MagicMock()
        mock_detail.send_status = "Pending"
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_detail
        mock_db.query.return_value.filter.return_value.first.return_value = mock_detail
        mock_ses.send_email.return_value = {"MessageId": "msg-att"}

        import tempfile
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        tmp.write(b"fake pdf content")
        tmp.close()

        task = SendTask(
            job_id=1, batch_id="b1", recipient="u@t.com", name="U",
            source_email="s@t.com", reply_to="", subject_tpl="Hi", html_tpl="<p>Hi</p>",
            text_tpl="", attributes={}, config_set="cfg", tags={},
            unsub_url="", detail_id=20,
            attachments=[{"file_name": "doc.pdf", "file_path": tmp.name, "content_type": "application/pdf"}],
        )
        self.engine._send_one(task, 0)

        call_kwargs = mock_ses.send_email.call_args[1]
        atts = call_kwargs["Content"]["Simple"]["Attachments"]
        assert len(atts) == 1
        assert atts[0]["FileName"] == "doc.pdf"
        assert atts[0]["RawContent"] == b"fake pdf content"
        assert atts[0]["ContentType"] == "application/pdf"

        os.unlink(tmp.name)


class TestUpdateDetailStatus:
    """Tests for _update_detail_status updating all same-email records"""

    @patch("core.database.SessionLocal")
    def test_updates_all_same_email(self, mock_session_cls):
        engine = SenderEngine.__new__(SenderEngine)
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        detail1 = MagicMock(send_status="Pending")
        detail2 = MagicMock(send_status="Pending")
        mock_db.query.return_value.filter.return_value.all.return_value = [detail1, detail2]

        mock_job = MagicMock(sent_count=0)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_job

        task = SendTask(
            job_id=1, batch_id="b1", recipient="dup@test.com", name="D",
            source_email="s@t.com", reply_to="", subject_tpl="", html_tpl="",
            text_tpl="", attributes={}, config_set="", tags={},
            unsub_url="", attachments=[], detail_id=0,
        )
        engine._update_detail_status(task, "Success", "", "msg-123")

        assert detail1.send_status == "Success"
        assert detail1.message_id == "msg-123"
        assert detail2.send_status == "Success"
        assert detail2.message_id == "msg-123"
        mock_db.commit.assert_called_once()
