import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.schemas import DecimalStr, ORMModel
from app.modules.owners.schemas import OwnerOut

LandType = Literal["agricultural", "non_agricultural", "residential", "commercial", "industrial", "mixed", "other"]
PropertyStatus = Literal["prospect", "in_pipeline", "acquired", "dropped", "on_hold"]
RoadAccess = Literal["unknown", "none", "kaccha", "pakka", "highway_frontage"]
TitleStatus = Literal["unknown", "under_review", "clear", "encumbered", "disputed"]
OwnershipType = Literal["sole", "joint", "co_owner", "legal_heir", "poa_holder", "lessee", "other"]


def _no_float(v):
    if isinstance(v, float):
        return Decimal(str(v))
    return v


class PropertyBase(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    land_type: LandType = "agricultural"
    state_id: uuid.UUID | None = None
    district_id: uuid.UUID | None = None
    tehsil_id: uuid.UUID | None = None
    village_id: uuid.UUID | None = None
    survey_number: str | None = None
    khasra_number: str | None = None
    khata_number: str | None = None
    address: str | None = None
    pincode: str | None = None
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    area_value: Decimal | None = Field(default=None, ge=0)
    area_unit: str | None = None
    land_use: str | None = None
    road_access: RoadAccess = "unknown"
    road_frontage_value: Decimal | None = Field(default=None, ge=0)
    road_frontage_unit: str | None = None
    title_status: TitleStatus = "unknown"
    notes: str | None = None
    custom_fields: dict = Field(default_factory=dict)

    _floats = field_validator("latitude", "longitude", "area_value", "road_frontage_value", mode="before")(_no_float)


class PropertyCreate(PropertyBase):
    pass


class PropertyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    land_type: LandType | None = None
    status: PropertyStatus | None = None
    state_id: uuid.UUID | None = None
    district_id: uuid.UUID | None = None
    tehsil_id: uuid.UUID | None = None
    village_id: uuid.UUID | None = None
    survey_number: str | None = None
    khasra_number: str | None = None
    khata_number: str | None = None
    address: str | None = None
    pincode: str | None = None
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    area_value: Decimal | None = Field(default=None, ge=0)
    area_unit: str | None = None
    land_use: str | None = None
    road_access: RoadAccess | None = None
    road_frontage_value: Decimal | None = Field(default=None, ge=0)
    road_frontage_unit: str | None = None
    title_status: TitleStatus | None = None
    notes: str | None = None
    custom_fields: dict | None = None

    _floats = field_validator("latitude", "longitude", "area_value", "road_frontage_value", mode="before")(_no_float)


class PropertyOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    land_type: str
    status: str
    state_id: uuid.UUID | None
    district_id: uuid.UUID | None
    tehsil_id: uuid.UUID | None
    village_id: uuid.UUID | None
    survey_number: str | None
    khasra_number: str | None
    khata_number: str | None
    address: str | None
    pincode: str | None
    latitude: DecimalStr | None
    longitude: DecimalStr | None
    active_geometry_id: uuid.UUID | None
    area_value: DecimalStr | None
    area_unit: str | None
    area_sqm_derived: DecimalStr | None
    land_use: str | None
    road_access: str
    road_frontage_value: DecimalStr | None
    road_frontage_unit: str | None
    title_status: str
    notes: str | None
    custom_fields: dict
    created_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class PropertyOwnerCreate(BaseModel):
    owner_id: uuid.UUID
    ownership_type: OwnershipType = "sole"
    share_percent: Decimal | None = Field(default=None, gt=0, le=100)
    record_reference: str | None = None
    source_document_id: uuid.UUID | None = None
    valid_from: date | None = None
    supersedes_id: uuid.UUID | None = None

    _floats = field_validator("share_percent", mode="before")(_no_float)


class PropertyOwnerEnd(BaseModel):
    reason: str = Field(min_length=3)
    valid_to: date | None = None


class PropertyOwnerVerify(BaseModel):
    status: Literal["pending", "verified", "rejected"]
    note: str | None = None


class PropertyOwnerOut(ORMModel):
    id: uuid.UUID
    property_id: uuid.UUID
    owner_id: uuid.UUID
    owner: OwnerOut
    ownership_type: str
    share_percent: DecimalStr | None
    record_reference: str | None
    source_document_id: uuid.UUID | None
    valid_from: date | None
    valid_to: date | None
    is_current: bool
    ended_reason: str | None
    verification_status: str
    verified_by_id: uuid.UUID | None
    verified_at: datetime | None
    supersedes_id: uuid.UUID | None
    created_at: datetime


class OwnershipSummary(BaseModel):
    total_share_percent: DecimalStr
    current_owner_count: int
    verified_owner_count: int
    is_complete: bool
    warnings: list[str]


class AssignmentIn(BaseModel):
    user_id: uuid.UUID
    role: str = "member"


class AssignmentOut(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    role: str
    created_at: datetime


class MapPin(BaseModel):
    property_id: uuid.UUID
    code: str
    name: str
    latitude: DecimalStr
    longitude: DecimalStr
    status: str
    deal_id: uuid.UUID | None
    deal_stage_key: str | None
    deal_stage_name: str | None
    color: str
    has_geometry: bool
