from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional, List, Generic, TypeVar, Literal, Annotated
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


class SuppressionSyncStatus(BaseModel):
    status: Literal["ready", "pending", "error", "stale", "disabled"]
    last_synced_at: Optional[str] = None
    region: str


class ContactListResponse(PaginatedResponse):
    suppression_sync: SuppressionSyncStatus


ContactFlag = Literal["bounced", "manual", "ses", "unsubscribed", "unmatched", "unknown"]


class ContactSelectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search: str = ""
    flags: list[ContactFlag] = Field(default_factory=list)


class ContactBulkDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contact_ids: Optional[list[Annotated[int, Field(strict=True, gt=0)]]] = Field(default=None, min_length=1, max_length=1000)
    selection_id: Optional[str] = Field(default=None, min_length=1, max_length=36)

    @model_validator(mode="after")
    def exactly_one_selection(self):
        if (self.contact_ids is None) == (self.selection_id is None):
            raise ValueError("Provide exactly one of contact_ids or selection_id")
        return self
