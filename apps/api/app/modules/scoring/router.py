import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.deps import DB, requires
from app.core.permissions import P
from app.core.schemas import ORMModel
from app.modules.audit import service as audit
from app.modules.deals.access import get_visible_deal
from app.modules.scoring import service

router = APIRouter(tags=["scoring"])


class FactorIn(BaseModel):
    key: str
    weight: float = Field(ge=0)
    params: dict = Field(default_factory=dict)


class ModelIn(BaseModel):
    name: str
    factors: list[FactorIn]


class ModelOut(ORMModel):
    id: uuid.UUID
    name: str
    is_active: bool
    factors: list


class ScoreOut(ORMModel):
    id: uuid.UUID | None = None
    deal_id: uuid.UUID
    model_id: uuid.UUID
    total: float
    coverage: float
    breakdown: list
    computed_at: datetime | None = None


@router.get("/scoring/factors")
def list_factors(ctx=requires(P.REPORT_READ)):
    return [{"key": k, "label": v[0]} for k, v in service.FACTORS.items()]


@router.get("/scoring/model", response_model=ModelOut)
def get_model(db: DB, ctx=requires(P.REPORT_READ)):
    return service.active_model(db, ctx)


@router.put("/scoring/model", response_model=ModelOut)
def update_model(body: ModelIn, db: DB, ctx=requires(P.SCORING_CONFIGURE)):
    factors = [f.model_dump() for f in body.factors]
    service.validate_factors(factors)
    m = service.active_model(db, ctx)
    before = {"name": m.name, "factors": m.factors}
    m.name, m.factors = body.name, factors
    audit.record(db, ctx, "scoring_model.updated", "scoring_model", m.id, changes={"from": before, "to": {"name": body.name, "factors": factors}})
    return m


@router.post("/deals/{deal_id}/score", response_model=ScoreOut)
def compute_score(deal_id: uuid.UUID, db: DB, ctx=requires(P.DEAL_READ)):
    return service.score_deal(db, ctx, get_visible_deal(db, deal_id, ctx))


@router.get("/deals/{deal_id}/score", response_model=ScoreOut | None)
def get_score(deal_id: uuid.UUID, db: DB, ctx=requires(P.DEAL_READ)):
    return service.latest_score(db, get_visible_deal(db, deal_id, ctx))
