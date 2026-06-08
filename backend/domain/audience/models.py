from sqlalchemy import Column, Integer, String, Text, ForeignKey
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


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), index=True)
    name = Column(String(255))
    attributes = Column(Text, nullable=True)                     # JSON string: {"company":"Acme","city":"Shanghai"}
    group_id = Column(Integer, ForeignKey("contact_groups.id"))

    group = relationship("ContactGroup", back_populates="contacts")
