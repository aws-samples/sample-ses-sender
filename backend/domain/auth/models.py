from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship
from core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True)
    display_name = Column(String(255))
    hashed_password = Column(String(255))
    email = Column(String(255))  # 发件邮箱
    contact_email = Column(String(255), nullable=True)  # 收件邮箱（默认同发件邮箱）
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    daily_send_limit = Column(Integer, default=1000)
    unsub_config = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    groups = relationship("ContactGroup", back_populates="owner")


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(128), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
