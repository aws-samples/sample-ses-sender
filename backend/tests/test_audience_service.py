"""Tests for domain/audience/service.py — group and contact management."""
import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestCreateGroup:
    def test_create_group_success(self):
        from domain.audience.service import create_group
        from domain.audience.schemas import GroupCreate

        db = MagicMock()
        db.refresh = MagicMock()

        data = GroupCreate(name="My Group", description="Test group")
        result = create_group(db, data, user_id=1)

        db.add.assert_called_once()
        db.commit.assert_called_once()


class TestCreateContact:
    def test_create_contact_success(self):
        from domain.audience.service import create_contact
        from domain.audience.schemas import ContactCreate
        from domain.audience.models import ContactGroup

        db = MagicMock()
        mock_group = MagicMock()
        mock_group.id = 1
        mock_group.user_id = 1
        db.query.return_value.filter.return_value.first.return_value = mock_group
        db.refresh = MagicMock()

        data = ContactCreate(group_id=1, name="John", email="john@test.com")
        result = create_contact(db, data, user_id=1)

        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_create_contact_group_not_found(self):
        from domain.audience.service import create_contact
        from domain.audience.schemas import ContactCreate
        from fastapi import HTTPException

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        data = ContactCreate(group_id=999, name="John", email="john@test.com")
        with pytest.raises(HTTPException) as exc_info:
            create_contact(db, data, user_id=1)
        assert exc_info.value.status_code == 404
