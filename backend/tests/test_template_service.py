"""Tests for domain/template/service.py — template CRUD."""
import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestCreateTemplate:
    @patch("domain.template.service.sesv2_client")
    def test_create_template_success(self, mock_ses):
        from domain.template.service import create_template
        from domain.template.schemas import TemplateCreate

        mock_ses.create_email_template.return_value = {}
        db = MagicMock()

        data = TemplateCreate(name="My Template", subject="Hello", html_body="<p>Hi</p>")
        result = create_template(db, data, user_id=1)

        assert "创建成功" in result["message"]
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @patch("domain.template.service.sesv2_client")
    def test_create_template_empty_name(self, mock_ses):
        from domain.template.service import create_template
        from domain.template.schemas import TemplateCreate
        from fastapi import HTTPException

        db = MagicMock()
        data = TemplateCreate(name="", subject="Hi", html_body="<p>x</p>")

        with pytest.raises(HTTPException) as exc_info:
            create_template(db, data, user_id=1)
        assert exc_info.value.status_code == 400
        assert "不能为空" in exc_info.value.detail


class TestUpdateTemplate:
    @patch("domain.template.service.sesv2_client")
    def test_update_template_not_found(self, mock_ses):
        from domain.template.service import update_template
        from domain.template.schemas import TemplateUpdate
        from fastapi import HTTPException

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        data = TemplateUpdate(subject="New Subject")
        with pytest.raises(HTTPException) as exc_info:
            update_template(db, template_id=999, data=data, user_id=1)
        assert exc_info.value.status_code == 404

    @patch("domain.template.service.sesv2_client")
    def test_update_template_success(self, mock_ses):
        from domain.template.service import update_template
        from domain.template.schemas import TemplateUpdate

        mock_ses.update_email_template.return_value = {}
        db = MagicMock()
        mock_tpl = MagicMock()
        mock_tpl.ses_name = "u1_abc"
        mock_tpl.subject = "Old"
        mock_tpl.html_body = "<p>Old</p>"
        mock_tpl.text_body = "Old"
        db.query.return_value.filter.return_value.first.return_value = mock_tpl

        data = TemplateUpdate(subject="New Subject", html_body="<p>New</p>")
        result = update_template(db, template_id=1, data=data, user_id=1)

        assert "已更新" in result["message"]
        assert mock_tpl.subject == "New Subject"
        assert mock_tpl.html_body == "<p>New</p>"
        db.commit.assert_called_once()
