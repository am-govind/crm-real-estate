import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import ActorMixin, Base, IdMixin, TenantScopedMixin, TimestampMixin, utcnow


class ScoringModel(IdMixin, TimestampMixin, TenantScopedMixin, ActorMixin, Base):
    __tablename__ = "scoring_models"

    name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    factors: Mapped[list] = mapped_column(default=list)


class DealScore(IdMixin, TenantScopedMixin, Base):
    __tablename__ = "deal_scores"

    deal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("deals.id"), index=True)
    model_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("scoring_models.id"))
    total: Mapped[float] = mapped_column(Float)
    coverage: Mapped[float] = mapped_column(Float)
    breakdown: Mapped[list] = mapped_column(default=list)
    computed_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
