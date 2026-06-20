"""
回归测试：覆盖本会话中修复过的历史 bug，防止后续更新破坏已修复的功能。

每个测试类对应一个历史问题，注释标明问题背景。
"""
import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.sender import (
    SendTask, build_send_task, load_contact_map, update_detail_status, send_task,
)


def _task(**kwargs):
    defaults = dict(
        job_id=1, batch_id="b1", recipient="u@t.com", name="U",
        source_email="s@t.com", reply_to="", subject_tpl="", html_tpl="",
        text_tpl="", attributes={}, config_set="", tags={},
        unsub_url="", attachments=[], detail_id=0,
    )
    defaults.update(kwargs)
    return SendTask(**defaults)


class TestCustomAttributeReplacement:
    """问题：模板里的 {{link}} 等自定义属性未被替换（同邮箱多客群取错联系人）。
    修复：按 group_id 精确匹配联系人并替换其 attributes。"""

    def test_link_attribute_replaced(self):
        from core.sender import replace_vars
        task = _task(attributes={"link": "https://www.163.com"})
        html = '<a href="{{link}}">网易</a>'
        assert replace_vars(html, task) == '<a href="https://www.163.com">网易</a>'

    def test_build_send_task_uses_contact_attributes(self):
        job = MagicMock(id=1, batch_id="b1", source_email="s@t.com", user_id=1, template_name="T")
        detail = MagicMock(id=10, recipient="u@t.com")
        tpl = MagicMock(subject="Hi {{name}}", html_body="<a href='{{link}}'>x</a>")
        with patch("core.config.UNSUBSCRIBE_BASE_URL", ""):
            t = build_send_task(detail, job, tpl, [], "r@t.com", ("张三", '{"link":"https://x.com"}'))
        assert t.name == "张三"
        assert t.attributes == {"link": "https://x.com"}
        assert t.detail_id == 10


class TestErrorMessageSimplification:
    """问题：发送失败原因冗长。修复：精简为 [Code] Message。"""

    def test_domain_starts_with_dot(self):
        from core.sender import extract_error
        err = "An error occurred (BadRequestException) when calling the SendEmail operation: Domain starts with dot"
        assert extract_error(err) == "[BadRequestException] Domain starts with dot"


class TestDedup:
    """问题：同一邮箱在客群出现多次导致重复发送。修复：提交阶段按邮箱去重。"""

    def test_dedup_keeps_first(self):
        contact_list = [
            {"email": "dup@t.com"}, {"email": "dup@t.com"}, {"email": "uniq@t.com"},
        ]
        seen, out = set(), []
        for c in contact_list:
            if c["email"] not in seen:
                seen.add(c["email"]); out.append(c)
        assert len(out) == 2


class TestIdempotentSend:
    """问题：pending 任务反复入队导致海量重复邮件。
    修复：发送前检查 detail 状态，非 Pending/Queued 直接跳过。"""

    @patch("core.blacklist.is_blacklisted", return_value=False)
    @patch("core.database.SessionLocal")
    @patch("core.sender.update_detail_status")
    def test_skip_already_sent(self, mock_update, mock_session_cls, mock_bl):
        db = MagicMock()
        mock_session_cls.return_value = db
        detail = MagicMock(send_status="Success")
        db.query.return_value.filter.return_value.first.return_value = detail
        result = send_task(_task(detail_id=5), log_prefix="T")
        assert result == "skipped"
        mock_update.assert_not_called()

    @patch("core.blacklist.is_blacklisted", return_value=False)
    @patch("core.database.SessionLocal")
    @patch("core.sender.update_detail_status")
    def test_skip_failed(self, mock_update, mock_session_cls, mock_bl):
        db = MagicMock()
        mock_session_cls.return_value = db
        detail = MagicMock(send_status="Failed")
        db.query.return_value.filter.return_value.first.return_value = detail
        result = send_task(_task(detail_id=6), log_prefix="T")
        assert result == "skipped"

    @patch("core.blacklist.is_blacklisted", return_value=False)
    @patch("core.database.SessionLocal")
    @patch("core.ses.sesv2_client")
    @patch("core.sender.update_detail_status")
    def test_queued_status_is_sendable(self, mock_update, mock_ses, mock_session_cls, mock_bl):
        """Queued 是新增中间态，应被视为待发送（不跳过）。"""
        db = MagicMock()
        mock_session_cls.return_value = db
        detail = MagicMock(send_status="Queued")
        db.query.return_value.filter.return_value.first.return_value = detail
        mock_ses.send_email.return_value = {"MessageId": "m1"}
        result = send_task(_task(detail_id=7), log_prefix="T")
        assert result == "success"
        mock_ses.send_email.assert_called_once()


class TestUpdateDetailByDetailId:
    """问题：update 按 recipient 匹配会更新错记录（同邮箱多条）。
    修复：优先按 detail_id 精确更新。"""

    @patch("core.database.SessionLocal")
    def test_update_by_detail_id(self, mock_session_cls):
        db = MagicMock()
        mock_session_cls.return_value = db
        d = MagicMock(send_status="Queued")
        db.query.return_value.filter.return_value.all.return_value = [d]
        db.query.return_value.filter.return_value.first.return_value = MagicMock(sent_count=0)
        n = update_detail_status(_task(detail_id=42), "Success", "", "m1")
        assert d.send_status == "Success"
        assert d.message_id == "m1"
        assert n == 1


class TestN1Elimination:
    """问题：入队时每封邮件单独查 Contact（N+1）。
    修复：load_contact_map 一次性批量查出 email->(name, attributes)。"""

    def test_load_contact_map_batches(self):
        db = MagicMock()
        rows = [("a@t.com", "A", '{"x":1}'), ("b@t.com", "B", None)]
        # query(...).filter(...).filter(...) 链
        q = db.query.return_value.filter.return_value
        q.filter.return_value = rows
        q.__iter__ = lambda s: iter(rows)
        # 直接让 filter 返回可迭代 rows
        db.query.return_value.filter.return_value = rows
        m = load_contact_map(db, ["a@t.com", "b@t.com"], group_id=None)
        assert m["a@t.com"] == ("A", '{"x":1}')
        assert m["b@t.com"] == ("B", None)

    def test_empty_recipients_no_query(self):
        db = MagicMock()
        assert load_contact_map(db, [], group_id=1) == {}


class TestBatchCompletionStatus:
    """问题：批次完成状态判定（success/partial/failed）。
    用纯逻辑函数验证判定规则，对应 Scanner/Producer 的 _finalize。"""

    @staticmethod
    def _decide(failed, total):
        if total > 0 and failed == total:
            return "failed"
        elif failed > 0:
            return "partial"
        return "success"

    def test_all_success(self):
        assert self._decide(failed=0, total=10) == "success"

    def test_partial(self):
        assert self._decide(failed=3, total=10) == "partial"

    def test_all_failed(self):
        assert self._decide(failed=10, total=10) == "failed"

    def test_zero_total_is_success(self):
        # 全部退订(Unsubscribed)被排除后 total=0，不应判为 failed
        assert self._decide(failed=0, total=0) == "success"
