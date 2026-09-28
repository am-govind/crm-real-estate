import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.schemas import ORMModel

VisitStatus = Literal["scheduled", "in_progress", "completed", "cancelled", "missed"]


class AttendeeIn(BaseModel):
    user_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    name: str | None = None
    contact: str | None = None
    role: str = "attendee"
    is_assigned: bool = False

    @model_validator(mode="after")
    def _who(self):
        if not (self.user_id or self.owner_id or self.name):
            raise ValueError("An attendee needs a user, an owner or a name")
        return self


class VisitCreate(BaseModel):
    property_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=300)
    purpose: str | None = None
    scheduled_start: datetime
    scheduled_end: datetime | None = None
    meeting_point: str | None = None
    attendees: list[AttendeeIn] = Field(default_factory=list)
    client_ref: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _check(self):
        if not (self.property_id or self.deal_id):
            raise ValueError("A site visit must be linked to a property and/or deal")
        if self.scheduled_end and self.scheduled_end <= self.scheduled_start:
            raise ValueError("scheduled_end must be after scheduled_start")
        return self


class VisitUpdate(BaseModel):
    title: str | None = None
    purpose: str | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    status: VisitStatus | None = None
    outcome: str | None = None
    meeting_point: str | None = None


class GeoPoint(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0)
    recorded_at: datetime | None = None


class CheckOutIn(GeoPoint):
    outcome: str | None = None
    track: list[GeoPoint] = Field(default_factory=list)


class NoteIn(BaseModel):
    body: str = Field(min_length=1)
    latitude: float | None = None
    longitude: float | None = None
    recorded_at: datetime | None = None
    client_ref: str | None = Field(default=None, max_length=64)


class AttendeeOut(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    name: str | None
    contact: str | None
    role: str
    is_assigned: bool
    attended: bool | None


class NoteOut(ORMModel):
    id: uuid.UUID
    body: str
    author_id: uuid.UUID | None
    latitude: float | None
    longitude: float | None
    client_ref: str | None
    recorded_at: datetime
    created_at: datetime


class MediaOut(ORMModel):
    id: uuid.UUID
    kind: str
    filename: str
    content_type: str
    size_bytes: int
    caption: str | None
    latitude: float | None
    longitude: float | None
    captured_at: datetime | None
    uploaded_by_id: uuid.UUID | None
    uploaded_at: datetime
    client_ref: str | None


class VisitOut(ORMModel):
    id: uuid.UUID
    property_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    title: str
    purpose: str | None
    scheduled_start: datetime
    scheduled_end: datetime | None
    status: str
    outcome: str | None
    meeting_point: str | None
    check_in_at: datetime | None
    check_in_lat: float | None
    check_in_lng: float | None
    check_in_accuracy_m: float | None
    check_out_at: datetime | None
    check_out_lat: float | None
    check_out_lng: float | None
    client_ref: str | None
    created_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    attendees: list[AttendeeOut]


class VisitDetail(VisitOut):
    notes: list[NoteOut]
    media: list[MediaOut] = Field(default_factory=list)
    conflicts: list[dict] = Field(default_factory=list)
