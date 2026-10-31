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


class TestUploadContactsExcel:
    def test_deduplicates_file_and_existing_group_case_insensitively(self):
        import io
        import openpyxl
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from core.database import Base
        from domain.auth.models import User
        from domain.audience.models import ContactGroup, Contact
        from domain.audience.service import upload_contacts_excel

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()

        user = User(username="import-user", hashed_password="x", email="sender@example.com")
        db.add(user)
        db.flush()
        group = ContactGroup(name="Import group", user_id=user.id)
        db.add(group)
        db.flush()
        db.add(Contact(name="Existing", email="Existing@Example.com", group_id=group.id))
        db.commit()

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append(["姓名", "邮箱", "company"])
        sheet.append(["Existing duplicate", "existing@example.com", "Old"])
        sheet.append(["New one", "new@example.com", "Acme"])
        sheet.append(["New duplicate", "NEW@example.com", "Acme"])
        sheet.append(["Empty", "", "Acme"])
        sheet.append(["New two", "second@example.com", "Tech"])
        content = io.BytesIO()
        workbook.save(content)
        content.seek(0)
        upload = MagicMock()
        upload.file = content

        result = upload_contacts_excel(db, group.id, user.id, upload)

        assert result["imported_count"] == 2
        assert result["duplicate_count"] == 2
        assert result["empty_count"] == 1
        assert db.query(Contact).filter(Contact.group_id == group.id).count() == 3
        assert {
            contact.email for contact in db.query(Contact).filter(Contact.group_id == group.id).all()
        } == {"Existing@Example.com", "new@example.com", "second@example.com"}

        db.close()
        engine.dispose()
