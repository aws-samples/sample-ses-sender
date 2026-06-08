from pydantic import BaseModel
from typing import Optional, List, Generic, TypeVar
from pydantic.generics import GenericModel


class GroupCreate(BaseModel):
    name: str
    description: Optional[str] = None


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class GroupOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    user_id: int
    contact_count: int = 0

    class Config:
        from_attributes = True


class ContactCreate(BaseModel):
    email: str
    name: Optional[str] = None
    attributes: Optional[str] = None
    group_id: int


class ContactOut(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    attributes: Optional[str] = None
    group_id: int

    class Config:
        from_attributes = True


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    total_pages: int
