from pydantic import BaseModel
from typing import Optional


class LoginRequest(BaseModel):
    username: str
    password: str
    captcha_id: Optional[str] = None
    captcha_code: Optional[str] = None


class UserCreate(BaseModel):
    username: str
    display_name: str
    password: str
    email: str
    contact_email: Optional[str] = None
    sender_name: Optional[str] = None
    is_admin: bool = False
    daily_send_limit: int = 1000


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    contact_email: Optional[str] = None
    sender_name: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    daily_send_limit: Optional[int] = None


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    email: str
    contact_email: Optional[str] = None
    sender_name: Optional[str] = None
    is_admin: bool
    is_active: bool
    daily_send_limit: int = 1000

    class Config:
        from_attributes = True
