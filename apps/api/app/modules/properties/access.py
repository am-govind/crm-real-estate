"""Property-level assignment rules layered on top of tenant RBAC."""

import uuid

from sqlalchemy import ColumnElement, or_, select, true
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.errors import NotFound
from app.core.permissions import P
from app.core.tenancy import get_scoped
from app.modules.properties.models import Property, PropertyAssignment


def visible_clause(ctx: RequestContext) -> ColumnElement[bool]:
    if ctx.has(P.PROPERTY_READ_ALL):
        return true()
    from app.modules.deals.models import Deal, DealAssignment

    return or_(
        Property.created_by_id == ctx.user_id,
        Property.id.in_(select(PropertyAssignment.property_id).where(PropertyAssignment.user_id == ctx.user_id)),
        Property.id.in_(
            select(Deal.property_id)
            .join(DealAssignment, DealAssignment.deal_id == Deal.id)
            .where(DealAssignment.user_id == ctx.user_id)
        ),
    )


def get_visible_property(session: Session, property_id: uuid.UUID, ctx: RequestContext) -> Property:
    prop = get_scoped(session, Property, property_id, ctx, label="Property")
    if ctx.has(P.PROPERTY_READ_ALL):
        return prop
    visible = session.scalar(select(Property.id).where(Property.id == prop.id, visible_clause(ctx)))
    if visible is None:
        raise NotFound("Property not found")
    return prop
