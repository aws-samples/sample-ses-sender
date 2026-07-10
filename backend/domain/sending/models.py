from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from core.database import Base


class SendingJob(Base):
    __tablename__ = "sending_jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    batch_id = Column(String(64), unique=True, index=True)     # 唯一批次标识（用于 VDM Tag）
    template_name = Column(String(255))                         # 模版名称
    template_id = Column(Integer, nullable=True)                  # 模版 ID
    group_name = Column(String(255))                            # 客群名称
    group_id = Column(Integer, nullable=True)                     # 客群 ID
    source_email = Column(String(255))                          # 发送邮箱
    sender_name = Column(String(255), nullable=True)            # 发件人显示名（Friendly From）
    reply_to = Column(String(255), nullable=True)               # 收件邮箱（回复地址）
    total_contacts = Column(Integer, default=0)                 # 联系人总数
    sent_count = Column(Integer, default=0)                     # 已发送数量（实时更新）
    total_batches = Column(Integer, default=0)                  # SES 批次数
    status = Column(String(50), default="queued")               # queued / sending / success / partial / failed
    error_message = Column(Text, nullable=True)
    configuration_set = Column(String(255), nullable=True)      # SES Configuration Set 名称
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)               # 完成时间


class SendingJobDetail(Base):
    """每封邮件的发送明细 + 事件追踪"""
    __tablename__ = "sending_job_details"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, index=True)                        # 关联 sending_jobs.id
    batch_id = Column(String(64), index=True)                   # 批次 ID
    message_id = Column(String(128), index=True, nullable=True) # SES MessageId
    recipient = Column(String(256), index=True)                 # 收件人邮箱
    send_status = Column(String(32), default="Pending")         # Success / MessageRejected / Failed
    send_error = Column(Text, nullable=True)                    # 发送失败原因

    # SES 事件追踪（通过 SNS Webhook 更新）
    delivery_status = Column(String(32), nullable=True)         # Delivery / Bounce / Reject
    delivery_time = Column(DateTime, nullable=True)
    bounce_type = Column(String(64), nullable=True)             # Permanent / Transient
    bounce_subtype = Column(String(64), nullable=True)          # General / NoEmail / Suppressed ...
    bounce_message = Column(Text, nullable=True)
    open_count = Column(Integer, default=0)                     # 打开次数
    first_open_time = Column(DateTime, nullable=True)
    click_count = Column(Integer, default=0)                    # 点击次数
    first_click_time = Column(DateTime, nullable=True)
    complaint_time = Column(DateTime, nullable=True)            # 投诉时间
    created_at = Column(DateTime, default=datetime.utcnow)


class UnsubscribeRecord(Base):
    """全局退订记录"""
    __tablename__ = "unsubscribe_list"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), index=True)                      # 收件人邮箱
    source_email = Column(String(255), index=True)               # 发送者邮箱
    reason = Column(String(32), default="one-click")             # one-click / manual / complaint
    unsubscribed_at = Column(DateTime, default=datetime.utcnow)


class EmailBlacklist(Base):
    """全局邮箱黑名单"""
    __tablename__ = "email_blacklist"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True)
    reason = Column(String(500), default="")
    created_by = Column(String(100), default="admin")
    created_at = Column(DateTime, default=datetime.utcnow)


class ScheduledJob(Base):
    """定时/周期发送任务"""
    __tablename__ = "scheduled_jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    template_id = Column(Integer)
    group_id = Column(Integer)
    template_name = Column(String(255))
    group_name = Column(String(255))

    schedule_type = Column(String(16))          # once / daily / weekly / monthly
    scheduled_time = Column(DateTime)           # once: 精确执行时间; recurring: 首次执行时间
    cron_hour = Column(Integer, default=9)      # 周期执行的小时 (0-23 UTC)
    cron_minute = Column(Integer, default=0)    # 周期执行的分钟 (0-59)
    day_of_week = Column(Integer, nullable=True)  # weekly: 0=周一 ... 6=周日
    day_of_month = Column(Integer, nullable=True) # monthly: 1-31

    status = Column(String(16), default="active")  # active / paused / completed / cancelled
    next_run_at = Column(DateTime, index=True)
    last_run_at = Column(DateTime, nullable=True)
    run_count = Column(Integer, default=0)
    last_batch_id = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
