import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Timestamps(ORMModel):
    created_at: datetime
    updated_at: datetime


DecimalStr = Annotated[Decimal, PlainSerializer(lambda v: format(v, "f"), return_type=str, when_used="json")]


class Measurement(BaseModel):
    """A value exactly as entered, with its unit. Never silently converted."""

    value: DecimalStr
    unit: str = Field(min_length=1, max_length=20)

    @field_validator("value", mode="before")
    @classmethod
    def _no_float(cls, v):
        if isinstance(v, float):
            return Decimal(str(v))
        return v


class DerivedValue(BaseModel):
    """A calculated value, explicitly marked derived with its sources and formula."""

    value: DecimalStr
    unit: str
    derived: Literal[True] = True
    formula: str
    sources: dict


class IdOut(ORMModel):
    id: uuid.UUID


class Reason(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)
