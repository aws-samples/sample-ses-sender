"""Tests for domain/settings/service.py — system settings and unsub page config."""
import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestGetUnsubPageConfig:
    def test_defaults(self):
        from domain.settings.service import get_unsub_page_config

        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []

        result = get_unsub_page_config(db)

        assert result["title"] == "退订确认"
        assert result["buttonText"] == "确认退订"
        assert result["color"] == "#667eea"
        assert isinstance(result["reasons"], list)
        assert len(result["reasons"]) > 0

    def test_user_override(self):
        from domain.settings.service import get_unsub_page_config
        import json

        db = MagicMock()

        mock_user = MagicMock()
        mock_user.unsub_config = json.dumps({
            "title": "自定义标题",
            "buttonText": "确定退订",
            "color": "#ff0000",
        })
        db.query.return_value.filter.return_value.all.side_effect = [
            [mock_user],
            [],
        ]

        result = get_unsub_page_config(db, source_email="user@test.com")

        assert result["title"] == "自定义标题"
        assert result["buttonText"] == "确定退订"
        assert result["color"] == "#ff0000"

    def test_button_text_field_present(self):
        from domain.settings.service import get_unsub_page_config

        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []

        result = get_unsub_page_config(db)
        assert "buttonText" in result
