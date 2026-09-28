"""Deal-level assignment rules layered on top of tenant RBAC."""

import uuid

from sqlalchemy import ColumnElement, or_, select, true
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.errors import NotFound
from app.core.permissions import P
from app.core.tenancy import get_scoped
from app.modules.deals.models import Deal, DealAssignment
from app.modules.properties.models import PropertyAssignment


def visible_clause(ctx: RequestContext) -> ColumnElement[bool]:
    if ctx.has(P.DEAL_READ_ALL):
        return true()
    return or_(
        Deal.created_by_id == ctx.user_id,
        Deal.next_action_assignee_id == ctx.user_id,
        Deal.id.in_(select(DealAssignment.deal_id).where(DealAssignment.user_id == ctx.user_id)),
        Deal.property_id.in_(select(PropertyAssignment.property_id).where(PropertyAssignment.user_id == ctx.user_id)),
    )


def get_visible_deal(session: Session, deal_id: uuid.UUID, ctx: RequestContext) -> Deal:
    deal = get_scoped(session, Deal, deal_id, ctx, label="Deal")
    if ctx.has(P.DEAL_READ_ALL):
        return deal
    if session.scalar(select(Deal.id).where(Deal.id == deal.id, visible_clause(ctx))) is None:
        raise NotFound("Deal not found")
    return deal
