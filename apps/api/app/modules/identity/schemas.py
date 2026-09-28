import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.core.schemas import ORMModel


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,78}$")
    country_code: str = "IN"
    default_currency: str = "INR"
    admin_email: EmailStr | None = None


class TenantOut(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    country_code: str
    default_currency: str
    is_active: bool
    settings: dict


class TenantSettingsUpdate(BaseModel):
    settings: dict


class MembershipSummary(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    role_keys: list[str]


class MeOut(BaseModel):
    id: uuid.UUID
    email: str | None
    display_name: str | None
    is_system_admin: bool
    tenant_id: uuid.UUID | None
    permissions: list[str]
    role_keys: list[str]
    memberships: list[MembershipSummary]
    terminology: dict[str, str]


class UserOut(ORMModel):
    id: uuid.UUID
    email: str | None
    display_name: str | None
    is_active: bool


class MemberOut(BaseModel):
    membership_id: uuid.UUID
    user: UserOut
    is_active: bool
    title: str | None
    role_keys: list[str]


class MemberUpdate(BaseModel):
    role_keys: list[str] | None = None
    is_active: bool | None = None
    title: str | None = None


class InvitationCreate(BaseModel):
    email: EmailStr
    role_keys: list[str] = Field(min_length=1)


class InvitationOut(ORMModel):
    id: uuid.UUID
    email: str
    role_keys: list[str]
    accepted_at: datetime | None
    created_at: datetime


class RoleOut(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    description: str | None
    is_builtin: bool
    permissions: list[str]


class RoleUpsert(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    name: str
    description: str | None = None
    permissions: list[str]
