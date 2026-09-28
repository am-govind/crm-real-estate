"""Factual deal scoring. Each factor reports the underlying fact, its normalized score, and why."""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.errors import ValidationFailed
from app.modules.deals import service as deal_service
from app.modules.deals.models import Deal
from app.modules.documents import service as document_service
from app.modules.maps.models import NearbyFeature
from app.modules.owners.models import Owner
from app.modules.properties.models import Property, PropertyOwner
from app.modules.scoring.models import DealScore, ScoringModel


@dataclass
class FactorResult:
    key: str
    label: str
    weight: float
    score: float | None
    fact: str | None
    explanation: str

    def as_dict(self) -> dict:
        return {
            "key": self.key, "label": self.label, "weight": self.weight,
            "score": None if self.score is None else round(self.score, 3),
            "fact": self.fact, "explanation": self.explanation, "missing": self.score is None,
        }


@dataclass
class ScoringInputs:
    session: Session
    ctx: RequestContext
    deal: Deal
    prop: Property


def _linear(value: float, best: float, worst: float) -> float:
    if best == worst:
        return 1.0 if value <= best else 0.0
    t = (value - best) / (worst - best)
    return max(0.0, min(1.0, 1 - t))


def _nearest(inp: ScoringInputs, kinds: tuple[str, ...]) -> NearbyFeature | None:
    return inp.session.scalar(
        select(NearbyFeature)
        .where(NearbyFeature.property_id == inp.prop.id, NearbyFeature.kind.in_(kinds))
        .order_by(NearbyFeature.distance_m)
        .limit(1)
    )


def f_highway(inp: ScoringInputs, p: dict) -> tuple[float | None, str | None, str]:
    f = _nearest(inp, ("highway",))
    if f is None:
        return None, None, "No highway data; refresh nearby features for this property"
    best, worst = p.get("best_m", 1000), p.get("worst_m", 20000)
    return _linear(f.distance_m, best, worst), f"{f.distance_m / 1000:.1f} km to {f.name or 'highway'}", \
        f"Linear from {best} m (best) to {worst} m (worst); source {f.source}, confidence {f.confidence}"


def f_city(inp: ScoringInputs, p: dict) -> tuple[float | None, str | None, str]:
    f = _nearest(inp, ("city", "town"))
    if f is None:
        return None, None, "No city/town data; refresh nearby features for this property"
    best, worst = p.get("best_m", 5000), p.get("worst_m", 50000)
    return _linear(f.distance_m, best, worst), f"{f.distance_m / 1000:.1f} km to {f.name or f.kind}", \
        f"Linear from {best} m to {worst} m; source {f.source}"


def f_area(inp: ScoringInputs, p: dict) -> tuple[float | None, str | None, str]:
    if inp.prop.area_sqm_derived is None:
        return None, None, "Area is missing or in a unit that is not converted automatically"
    area = float(inp.prop.area_sqm_derived)
    minimum, target = p.get("min_sqm", 4046.86), p.get("target_sqm", 40468.6)
    score = 0.0 if area < minimum else min(1.0, area / target)
    return score, f"{inp.prop.area_value} {inp.prop.area_unit} (≈{area:,.0f} m², derived)", \
        f"0 below {minimum:,.0f} m²; scales to 1 at {target:,.0f} m²"


def f_price(inp: ScoringInputs, p: dict) -> tuple[float | None, str | None, str]:
    asking, target = inp.deal.asking_price, inp.deal.expected_price
    if asking is None or target is None:
        return None, None, "Asking and expected (target) prices are both required"
    tolerance = Decimal(str(p.get("tolerance", 0.25)))
    if asking <= target:
        score = 1.0
    else:
        over = (asking - target) / target
        score = float(max(Decimal("0"), 1 - over / tolerance))
    return score, f"Asking {asking} vs target {target} {inp.deal.currency}", \
        f"1 when asking ≤ target; 0 when asking exceeds target by {tolerance * 100:.0f}% or more"


TITLE_SCORES = {"clear": 1.0, "under_review": 0.5, "unknown": 0.3, "encumbered": 0.1, "disputed": 0.0}


def f_title(inp: ScoringInputs, p: dict) -> tuple[float | None, str | None, str]:
    legal = next((s for s in deal_service.due_diligence_summary(inp.session, inp.deal) if s.category == "legal"), None)
    if legal and legal.status == "issue_found":
        return 0.0, f"Legal due diligence: {legal.issues} issue(s) found", "Open legal issues score 0"
    status = inp.prop.title_status
    return TITLE_SCORES.get(status, 0.3), f"Title status: {status}", "clear 1 · under review 0.5 · unknown 0.3 · encumbered 0.1 · disputed 0"


ROAD_SCORES = {"highway_frontage": 1.0, "pakka": 0.8, "kaccha": 0.4, "none": 0.0}


def f_road(inp: ScoringInputs, p: dict) -> tuple[float | None, str | None, str]:
    if inp.prop.road_access == "unknown":
        return None, None, "Road access not recorded"
    return ROAD_SCORES.get(inp.prop.road_access, 0.0), f"Road access: {inp.prop.road_access}", \
        "highway frontage 1 · pakka 0.8 · kaccha 0.4 · none 0"


def f_land_use(inp: ScoringInputs, p: dict) -> tuple[float | None, str | None, str]:
    if not inp.prop.land_use:
        return None, None, "Land use not recorded"
    preferred = [x.lower() for x in p.get("preferred", [])]
    if not preferred:
        return None, f"Land use: {inp.prop.land_use}", "No preferred land uses configured for this model"
    ok = inp.prop.land_use.lower() in preferred
    return (1.0 if ok else 0.2), f"Land use: {inp.prop.land_use}", f"1 if in {preferred}, otherwise 0.2"


def f_docs(inp: ScoringInputs, p: dict) -> tuple[float | None, str | None, str]:
    c = document_service.completeness(inp.session, inp.ctx, deal_id=inp.deal.id)
    if not c["required"]:
        return None, None, "No required documents configured"
    return c["received"] / c["required"], c["label"], "Share of required documents received (not rejected)"


READINESS_SCORES = {"ready_to_sell": 1.0, "considering": 0.5, "unknown": 0.2, "not_interested": 0.0}


def f_owner_readiness(inp: ScoringInputs, p: dict) -> tuple[float | None, str | None, str]:
    rows = inp.session.execute(
        select(PropertyOwner, Owner)
        .join(Owner, Owner.id == PropertyOwner.owner_id)
        .where(PropertyOwner.property_id == inp.prop.id, PropertyOwner.is_current.is_(True))
    ).all()
    if not rows:
        return None, None, "No current owners recorded"
    readiness = sum(READINESS_SCORES.get(o.readiness, 0.2) for _, o in rows) / len(rows)
    verified = sum(1 for po, o in rows if po.verification_status == "verified" and o.verification_status == "verified") / len(rows)
    ready_count = sum(1 for _, o in rows if o.readiness == "ready_to_sell")
    return 0.7 * readiness + 0.3 * verified, f"{ready_count}/{len(rows)} owners ready; {verified:.0%} verified", \
        "70% owner readiness, 30% ownership verification"


FACTORS: dict[str, tuple[str, Callable[[ScoringInputs, dict], tuple]]] = {
    "highway_proximity": ("Highway proximity", f_highway),
    "city_proximity": ("City proximity", f_city),
    "land_area": ("Land area", f_area),
    "price_vs_target": ("Asking vs target price", f_price),
    "title_status": ("Title status", f_title),
    "road_access": ("Road access", f_road),
    "land_use": ("Land use", f_land_use),
    "documentation_completeness": ("Documentation completeness", f_docs),
    "owner_readiness": ("Owner readiness", f_owner_readiness),
}

DEFAULT_FACTORS = [
    {"key": "highway_proximity", "weight": 15, "params": {}},
    {"key": "land_area", "weight": 10, "params": {}},
    {"key": "price_vs_target", "weight": 15, "params": {}},
    {"key": "title_status", "weight": 20, "params": {}},
    {"key": "road_access", "weight": 10, "params": {}},
    {"key": "land_use", "weight": 5, "params": {"preferred": []}},
    {"key": "documentation_completeness", "weight": 15, "params": {}},
    {"key": "owner_readiness", "weight": 10, "params": {}},
]


def validate_factors(factors: list[dict]) -> None:
    for f in factors:
        if f.get("key") not in FACTORS:
            raise ValidationFailed(f"Unknown factor {f.get('key')!r}", details={"allowed": sorted(FACTORS)})
        if not isinstance(f.get("weight"), (int, float)) or f["weight"] < 0:
            raise ValidationFailed(f"Invalid weight for {f['key']}")


def active_model(session: Session, ctx: RequestContext) -> ScoringModel:
    m = session.scalar(select(ScoringModel).where(ScoringModel.tenant_id == ctx.tenant_id, ScoringModel.is_active.is_(True)))
    if m is None:
        m = ScoringModel(tenant_id=ctx.tenant_id, name="Default", factors=DEFAULT_FACTORS, created_by_id=ctx.user_id)
        session.add(m)
        session.flush()
    return m


def score_deal(session: Session, ctx: RequestContext, deal: Deal, *, persist: bool = True) -> DealScore:
    model = active_model(session, ctx)
    inp = ScoringInputs(session=session, ctx=ctx, deal=deal, prop=session.get(Property, deal.property_id))
    results: list[FactorResult] = []
    for f in model.factors:
        label, fn = FACTORS[f["key"]]
        score, fact, explanation = fn(inp, f.get("params") or {})
        results.append(FactorResult(f["key"], label, float(f["weight"]), score, fact, explanation))
    total_weight = sum(r.weight for r in results) or 1.0
    known_weight = sum(r.weight for r in results if r.score is not None)
    total = sum(r.weight * (r.score or 0.0) for r in results) / total_weight * 100
    ds = DealScore(
        tenant_id=ctx.tenant_id, deal_id=deal.id, model_id=model.id, total=round(total, 1),
        coverage=round(known_weight / total_weight, 3), breakdown=[r.as_dict() for r in results],
    )
    if persist:
        session.add(ds)
        session.flush()
    return ds


def latest_score(session: Session, deal: Deal) -> DealScore | None:
    return session.scalar(select(DealScore).where(DealScore.deal_id == deal.id).order_by(DealScore.computed_at.desc()).limit(1))
