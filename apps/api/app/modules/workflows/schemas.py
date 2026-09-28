import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.schemas import ORMModel

KEY_PATTERN = r"^[a-z][a-z0-9_]{1,79}$"


class ChecklistItemIn(BaseModel):
    key: str = Field(pattern=KEY_PATTERN)
    label: str
    description: str | None = None
    is_required: bool = True
    document_class_key: str | None = None


class StageIn(BaseModel):
    key: str = Field(pattern=KEY_PATTERN)
    name: str
    description: str | None = None
    category: str = "lead"
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    is_terminal: bool = False
    is_skippable: bool = True
    sla_days: int | None = Field(default=None, ge=0)
    checklist: list[ChecklistItemIn] = Field(default_factory=list)


class TemplateCreate(BaseModel):
    key: str = Field(pattern=KEY_PATTERN)
    name: str
    description: str | None = None
    land_types: list[str] = Field(default_factory=list)


class VersionDraftIn(BaseModel):
    notes: str | None = None
    stages: list[StageIn] = Field(min_length=2)


class ChecklistItemOut(ORMModel):
    id: uuid.UUID
    key: str
    label: str
    description: str | None
    position: int
    is_required: bool
    document_class_key: str | None


class StageOut(ORMModel):
    id: uuid.UUID
    key: str
    name: str
    description: str | None
    position: int
    category: str
    color: str | None
    is_terminal: bool
    is_skippable: bool
    sla_days: int | None
    checklist: list[ChecklistItemOut]


class VersionOut(ORMModel):
    id: uuid.UUID
    template_id: uuid.UUID
    version: int
    status: str
    notes: str | None
    published_at: datetime | None
    stages: list[StageOut]


class VersionSummary(ORMModel):
    id: uuid.UUID
    version: int
    status: str
    published_at: datetime | None


class TemplateOut(ORMModel):
    id: uuid.UUID
    key: str
    name: str
    description: str | None
    land_types: list[str]
    is_archived: bool
    versions: list[VersionSummary]


class ActivationIn(BaseModel):
    template_version_id: uuid.UUID
    is_default: bool = False
    land_types: list[str] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)


class ActivationUpdate(BaseModel):
    is_active: bool | None = None
    is_default: bool | None = None
    land_types: list[str] | None = None
    config: dict | None = None


class ActivationOut(ORMModel):
    id: uuid.UUID
    template_version_id: uuid.UUID
    is_active: bool
    is_default: bool
    land_types: list[str]
    config: dict
    created_at: datetime
    template_version: VersionOut
