import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.schemas import ORMModel

OwnerType = Literal["individual", "organization", "trust", "huf", "government", "other"]
Readiness = Literal["unknown", "not_interested", "considering", "ready_to_sell"]
ContactKind = Literal["phone", "email", "whatsapp", "address", "other"]


class ContactIn(BaseModel):
    kind: ContactKind
    value: str = Field(min_length=1, max_length=500)
    label: str | None = None
    is_primary: bool = False


class ContactOut(ORMModel):
    id: uuid.UUID
    kind: str
    value: str
    label: str | None
    is_primary: bool


class OwnerCreate(BaseModel):
    owner_type: OwnerType = "individual"
    full_name: str = Field(min_length=1, max_length=300)
    local_name: str | None = None
    relation_name: str | None = None
    date_of_birth: date | None = None
    readiness: Readiness = "unknown"
    notes: str | None = None
    custom_fields: dict = Field(default_factory=dict)
    contacts: list[ContactIn] = Field(default_factory=list)


class OwnerUpdate(BaseModel):
    owner_type: OwnerType | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=300)
    local_name: str | None = None
    relation_name: str | None = None
    date_of_birth: date | None = None
    readiness: Readiness | None = None
    notes: str | None = None
    custom_fields: dict | None = None


class OwnerVerify(BaseModel):
    status: Literal["pending", "verified", "rejected"]
    note: str | None = None


class OwnerOut(ORMModel):
    id: uuid.UUID
    code: str
    owner_type: str
    full_name: str
    local_name: str | None
    relation_name: str | None
    date_of_birth: date | None
    verification_status: str
    verified_by_id: uuid.UUID | None
    verified_at: datetime | None
    verification_note: str | None
    readiness: str
    notes: str | None
    custom_fields: dict
    contacts: list[ContactOut]
    created_at: datetime
    updated_at: datetime
