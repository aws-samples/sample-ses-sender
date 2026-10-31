from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Index
from sqlalchemy.orm import relationship
from core.database import Base


class ContactGroup(Base):
    __tablename__ = "contact_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True)
    description = Column(String(500))
    user_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="groups")
    contacts = relationship("Contact", back_populates="group", cascade="all, delete-orphan")
    selections = relationship("ContactSelection", cascade="all, delete-orphan", passive_deletes=True)


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (Index("ix_contacts_group_id_id", "group_id", "id"),)

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), index=True)
    name = Column(String(255))
    attributes = Column(Text, nullable=True)                     # JSON string: {"company":"Acme","city":"Shanghai"}
    group_id = Column(Integer, ForeignKey("contact_groups.id"))

    group = relationship("ContactGroup", back_populates="contacts")


class ContactSelection(Base):
    """Short-lived, immutable selection; its ID is not an authorization token."""
    __tablename__ = "contact_selections"

    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    group_id = Column(Integer, ForeignKey("contact_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)


class ContactSelectionItem(Base):
    __tablename__ = "contact_selection_items"

    selection_id = Column(String(36), ForeignKey("contact_selections.id", ondelete="CASCADE"), primary_key=True)
    # No contact FK: a deleted or moved contact must never widen this selection.
    contact_id = Column(Integer, primary_key=True)
