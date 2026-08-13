from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True)
    display_name = Column(String(255))
    hashed_password = Column(String(255))
    email = Column(String(255))  # 发件邮箱
    sender_name = Column(String(255), nullable=True)  # 发件人显示名（Friendly From）
    contact_email = Column(String(255), nullable=True)  # 收件邮箱（默认同发件邮箱）
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    daily_send_limit = Column(Integer, default=1000)
    unsub_config = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    groups = relationship("ContactGroup", back_populates="owner")
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    key_prefix = Column(String(24), nullable=False, index=True)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    scopes = Column(Text, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="api_keys")


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(128), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
