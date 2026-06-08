from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class BulkSendRequest(BaseModel):
    TemplateId: int
    GroupId: int


class TestEmailRequest(BaseModel):
    source: str
    to: str
    subject: str
    html_body: str


class SendingJobOut(BaseModel):
    id: int
    batch_id: str
    template_name: str
    group_name: str
    source_email: str
    reply_to: Optional[str] = None
    total_contacts: int
    sent_count: int = 0
    total_batches: int
    status: str
    error_message: Optional[str] = None
    configuration_set: Optional[str] = None
    created_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SendingJobDetailOut(BaseModel):
    id: int
    batch_id: Optional[str] = None
    message_id: Optional[str] = None
    recipient: str
    send_status: str
    send_error: Optional[str] = None
    delivery_status: Optional[str] = None
    delivery_time: Optional[datetime] = None
    bounce_type: Optional[str] = None
    bounce_subtype: Optional[str] = None
    bounce_message: Optional[str] = None
    open_count: int = 0
    first_open_time: Optional[datetime] = None
    click_count: int = 0
    first_click_time: Optional[datetime] = None
    complaint_time: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ScheduledJobCreate(BaseModel):
    template_id: int
    group_id: int
    schedule_type: str          # once / daily / weekly / monthly
    scheduled_time: str         # ISO 格式日期时间字符串
    cron_hour: int = 9
    cron_minute: int = 0
    day_of_week: Optional[int] = None   # 0-6 (周一-周日)
    day_of_month: Optional[int] = None  # 1-31


class ScheduledJobUpdate(BaseModel):
    schedule_type: Optional[str] = None
    scheduled_time: Optional[str] = None
    cron_hour: Optional[int] = None
    cron_minute: Optional[int] = None
    day_of_week: Optional[int] = None
    day_of_month: Optional[int] = None
    status: Optional[str] = None


class ScheduledJobOut(BaseModel):
    id: int
    user_id: int
    template_id: int
    group_id: int
    template_name: str
    group_name: str
    schedule_type: str
    scheduled_time: Optional[datetime] = None
    cron_hour: int = 9
    cron_minute: int = 0
    day_of_week: Optional[int] = None
    day_of_month: Optional[int] = None
    status: str
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    run_count: int = 0
    last_batch_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
