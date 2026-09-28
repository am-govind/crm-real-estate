import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.core.db import utcnow
from app.core.deps import DB, requires
from app.core.errors import NotFound
from app.core.pagination import Page, PageParams, paginate
from app.core.permissions import P
from app.core.sequences import take
from app.core.tenancy import get_scoped, scoped
from app.modules.audit import service as audit
from app.modules.owners.models import Owner, OwnerContact
from app.modules.owners.schemas import ContactIn, ContactOut, OwnerCreate, OwnerOut, OwnerUpdate, OwnerVerify

router = APIRouter(prefix="/owners", tags=["owners"])


@router.get("", response_model=Page[OwnerOut])
def list_owners(
    db: DB,
    q: str | None = None,
    verification_status: str | None = None,
    readiness: str | None = None,
    page: PageParams = Depends(),
    ctx=requires(P.OWNER_READ),
):
    stmt = scoped(Owner, ctx).options(selectinload(Owner.contacts))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Owner.full_name.ilike(like),
                Owner.local_name.ilike(like),
                Owner.code.ilike(like),
                Owner.id.in_(select(OwnerContact.owner_id).where(OwnerContact.value.ilike(like))),
            )
        )
    if verification_status:
        stmt = stmt.where(Owner.verification_status == verification_status)
    if readiness:
        stmt = stmt.where(Owner.readiness == readiness)
    items, total = paginate(db, stmt.order_by(Owner.full_name), page)
    return {"items": items, "total": total, "limit": page.limit, "offset": page.offset}


@router.post("", response_model=OwnerOut, status_code=201)
def create_owner(body: OwnerCreate, db: DB, ctx=requires(P.OWNER_WRITE)):
    data = body.model_dump(exclude={"contacts"})
    owner = Owner(tenant_id=ctx.tenant_id, code=take(db, ctx.tenant_id, "owner"), created_by_id=ctx.user_id, **data)
    owner.contacts = [OwnerContact(**c.model_dump()) for c in body.contacts]
    db.add(owner)
    db.flush()
    audit.record(db, ctx, "owner.created", "owner", owner.id, changes=audit.snapshot(owner))
    return owner


@router.get("/{owner_id}", response_model=OwnerOut)
def get_owner(owner_id: uuid.UUID, db: DB, ctx=requires(P.OWNER_READ)):
    return get_scoped(db, Owner, owner_id, ctx)


@router.patch("/{owner_id}", response_model=OwnerOut)
def update_owner(owner_id: uuid.UUID, body: OwnerUpdate, db: DB, ctx=requires(P.OWNER_WRITE)):
    owner = get_scoped(db, Owner, owner_id, ctx)
    before = audit.snapshot(owner)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(owner, k, v)
    db.flush()
    audit.record_update(db, ctx, "owner", owner, before)
    return owner


@router.post("/{owner_id}/verification", response_model=OwnerOut)
def verify_owner(owner_id: uuid.UUID, body: OwnerVerify, db: DB, ctx=requires(P.OWNER_VERIFY)):
    owner = get_scoped(db, Owner, owner_id, ctx)
    before = owner.verification_status
    owner.verification_status = body.status
    owner.verification_note = body.note
    owner.verified_by_id = ctx.user_id if body.status in ("verified", "rejected") else None
    owner.verified_at = utcnow() if body.status in ("verified", "rejected") else None
    audit.record(
        db, ctx, "owner.verification_changed", "owner", owner.id,
        changes={"verification_status": {"from": before, "to": body.status}}, metadata={"note": body.note},
    )
    return owner


@router.post("/{owner_id}/contacts", response_model=ContactOut, status_code=201)
def add_contact(owner_id: uuid.UUID, body: ContactIn, db: DB, ctx=requires(P.OWNER_WRITE)):
    owner = get_scoped(db, Owner, owner_id, ctx)
    if body.is_primary:
        for c in owner.contacts:
            if c.kind == body.kind:
                c.is_primary = False
    contact = OwnerContact(owner_id=owner.id, **body.model_dump())
    db.add(contact)
    db.flush()
    audit.record(db, ctx, "owner.contact_added", "owner", owner.id, metadata=body.model_dump())
    return contact


@router.delete("/{owner_id}/contacts/{contact_id}", status_code=204)
def remove_contact(owner_id: uuid.UUID, contact_id: uuid.UUID, db: DB, ctx=requires(P.OWNER_WRITE)):
    owner = get_scoped(db, Owner, owner_id, ctx)
    contact = next((c for c in owner.contacts if c.id == contact_id), None)
    if contact is None:
        raise NotFound("Contact not found")
    audit.record(db, ctx, "owner.contact_removed", "owner", owner.id, metadata={"kind": contact.kind, "value": contact.value})
    db.delete(contact)
