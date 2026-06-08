from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from core.database import Base


class EmailTemplate(Base):
    __tablename__ = "email_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True)              # 用户看到的模版名称
    ses_name = Column(String(255), unique=True)          # SES 中的实际模版名称 (u{user_id}_{name})
    subject = Column(String(500))                        # 邮件主题
    html_body = Column(Text)                             # HTML 内容
    text_body = Column(Text)                             # 纯文本内容
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)


class TemplateAttachment(Base):
    __tablename__ = "template_attachments"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, index=True)
    file_name = Column(String(255))
    file_path = Column(String(500))
    content_type = Column(String(128))
    file_size = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
