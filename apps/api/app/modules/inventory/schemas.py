import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.core.schemas import DecimalStr, Measurement, ORMModel

InventoryStatus = Literal["available", "reserved", "blocked", "sold", "under_acquisition", "not_for_sale"]


class Edge(BaseModel):
    """A named edge or boundary segment of an irregular plot (e.g. frontage, north edge, south cut)."""

    name: str = Field(min_length=1, max_length=100)
    length: Measurement
    direction: str | None = None
    notes: str | None = None


class SourceRef(BaseModel):
    document_id: uuid.UUID | None = None
    map_upload_id: uuid.UUID | None = None
    page_number: int | None = Field(default=None, ge=1)
    map_label: str | None = None
    region_reference: str | None = None
    layout_reference: str | None = None


class Location(BaseModel):
    property_id: uuid.UUID | None = None
    project_name: str | None = None
    state_id: uuid.UUID | None = None
    district_id: uuid.UUID | None = None
    tehsil_id: uuid.UUID | None = None
    village_id: uuid.UUID | None = None
    address: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    description: str | None = None


class RoadAccess(BaseModel):
    road_type: str | None = None
    road_width: Measurement | None = None
    access_notes: str | None = None


class _Common(BaseModel):
    status: InventoryStatus = "available"
    source: SourceRef = Field(default_factory=SourceRef)
    location: Location = Field(default_factory=Location)
    notes: str | None = None


class LandPlotData(_Common):
    property_type: Literal["land_plot"]
    plot_label: str | None = None
    area: Measurement | None = None
    length: Measurement | None = None
    width: Measurement | None = None
    frontage: Measurement | None = None
    cut_dimensions: list[Edge] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    road_access: RoadAccess | None = None


class ResidentialUnitData(_Common):
    property_type: Literal["apartment", "studio_flat"]
    unit_number: str | None = None
    floor: str | None = None
    total_area: Measurement | None = None
    carpet_area: Measurement | None = None
    built_up_area: Measurement | None = None
    super_built_up_area: Measurement | None = None
    rooms: int | None = Field(default=None, ge=0)
    bathrooms: int | None = Field(default=None, ge=0)


class CommercialUnitData(_Common):
    property_type: Literal["commercial_unit"]
    unit_number: str | None = None
    floor: str | None = None
    total_area: Measurement | None = None
    carpet_area: Measurement | None = None
    built_up_area: Measurement | None = None
    frontage: Measurement | None = None
    access: str | None = None
    usage_type: str | None = None


SiteData = Annotated[LandPlotData | ResidentialUnitData | CommercialUnitData, Field(discriminator="property_type")]


class MatchQuery(BaseModel):
    data: SiteData
    exclude_site_id: uuid.UUID | None = None


class MatchCandidate(BaseModel):
    site_id: uuid.UUID
    site_code: str
    score: float
    reasons: list[str]
    approval_state: str


class SiteCreate(BaseModel):
    confirmed_site_code: str = Field(pattern=r"^SITE-\d{6}$")
    confirmed_new: Literal[True]
    considered_candidates: list[uuid.UUID] = Field(default_factory=list)
    data: SiteData
    change_note: str | None = None


class RevisionCreate(BaseModel):
    data: SiteData
    change_note: str = Field(min_length=3)
    considered_candidates: list[uuid.UUID] = Field(default_factory=list)


class ReviewIn(BaseModel):
    note: str | None = None


class RejectIn(BaseModel):
    note: str = Field(min_length=3)


class RevisionOut(ORMModel):
    id: uuid.UUID
    site_record_id: uuid.UUID
    revision_no: int
    change_type: str
    data: dict
    derived: dict
    match_decision: dict
    change_note: str | None
    status: str
    submitted_by_id: uuid.UUID
    submitted_at: datetime
    reviewed_by_id: uuid.UUID | None
    reviewed_at: datetime | None
    review_note: str | None


class SiteOut(ORMModel):
    id: uuid.UUID
    site_code: str
    property_type: str
    approval_state: str
    active_revision_id: uuid.UUID | None
    pending_revision_id: uuid.UUID | None
    status: str | None
    property_id: uuid.UUID | None
    source_document_id: uuid.UUID | None
    source_map_upload_id: uuid.UUID | None
    plot_label: str | None
    unit_number: str | None
    project_name: str | None
    location_text: str | None
    latitude: float | None
    longitude: float | None
    area_value: DecimalStr | None
    area_unit: str | None
    area_sqm_derived: DecimalStr | None
    rooms: int | None
    bathrooms: int | None
    floor: str | None
    usage_type: str | None
    created_at: datetime
    updated_at: datetime


class SiteDetail(SiteOut):
    active_revision: RevisionOut | None = None
    pending_revision: RevisionOut | None = None
    history: list[RevisionOut] = Field(default_factory=list)
