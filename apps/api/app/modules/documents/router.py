import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.db import utcnow
from app.core.deps import DB, TenantCtx, requires
from app.core.errors import NotFound, ValidationFailed
from app.core.pagination import Page, PageParams
from app.core.permissions import P
from app.core.schemas import ORMModel
from app.core.storage import get_storage, safe_filename
from app.core.tenancy import get_scoped
from app.modules.audit import service as audit
from app.modules.documents import service
from app.modules.documents.models import (
    DOC_CATEGORIES,
    Document,
    DocumentAccessGrant,
    DocumentClass,
    DocumentReview,
    DocumentVersion,
    RequiredDocumentRule,
)
from app.modules.identity.models import TenantMembership

router = APIRouter(tags=["documents"])

AccessPolicy = Literal["standard", "restricted", "confidential"]


class DocumentClassOut(ORMModel):
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    key: str
    name: str
    category: str
    is_sensitive: bool
    default_access_policy: str
    requires_expiry: bool
    applies_to: list[str]
    description: str | None


class DocumentClassIn(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    name: str
    category: str
    is_sensitive: bool = False
    default_access_policy: AccessPolicy = "standard"
    requires_expiry: bool = False
    applies_to: list[str] = Field(default_factory=lambda: ["property", "deal"])
    description: str | None = None


class VersionOut(ORMModel):
    id: uuid.UUID
    version_no: int
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    note: str | None
    uploaded_by_id: uuid.UUID | None
    uploaded_at: datetime


class DocumentOut(BaseModel):
    id: uuid.UUID
    class_id: uuid.UUID
    class_key: str
    class_name: str
    category: str
    is_sensitive: bool
    is_redacted: bool = False
    title: str | None
    description: str | None = None
    property_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    site_visit_id: uuid.UUID | None
    access_policy: str
    review_status: str
    reviewer_id: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    current_version_no: int
    expiry_date: date | None
    renewal_due_date: date | None = None
    reference_number: str | None = None
    issued_on: date | None = None
    created_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    versions: list[VersionOut] = Field(default_factory=list)


class ReviewIn(BaseModel):
    decision: Literal["approved", "rejected", "needs_changes"]
    note: str | None = None


class ReviewOut(ORMModel):
    id: uuid.UUID
    version_id: uuid.UUID
    decision: str
    note: str | None
    reviewer_id: uuid.UUID
    reviewed_at: datetime


class DocumentUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    access_policy: AccessPolicy | None = None
    expiry_date: date | None = None
    renewal_due_date: date | None = None
    reference_number: str | None = None
    issued_on: date | None = None
    is_archived: bool | None = None


class GrantIn(BaseModel):
    user_id: uuid.UUID
    reason: str = Field(min_length=3)
    expires_at: datetime | None = None


class GrantOut(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    granted_by_id: uuid.UUID
    reason: str
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class RuleIn(BaseModel):
    scope: Literal["property", "deal"]
    class_id: uuid.UUID
    land_types: list[str] = Field(default_factory=list)


class RuleOut(ORMModel):
    id: uuid.UUID
    scope: str
    class_id: uuid.UUID
    land_types: list[str]
    is_active: bool
    document_class: DocumentClassOut


def to_out(doc: Document, *, redacted: bool = False) -> DocumentOut:
    cls = doc.document_class
    base = dict(
        id=doc.id, class_id=doc.class_id, class_key=cls.key, class_name=cls.name, category=cls.category,
        is_sensitive=service.is_sensitive(doc), property_id=doc.property_id, deal_id=doc.deal_id, owner_id=doc.owner_id,
        site_visit_id=doc.site_visit_id, access_policy=doc.access_policy, review_status=doc.review_status,
        current_version_no=doc.current_version_no, expiry_date=doc.expiry_date, created_by_id=doc.created_by_id,
        created_at=doc.created_at, updated_at=doc.updated_at,
    )
    if redacted:
        return DocumentOut(**base, is_redacted=True, title=None)
    return DocumentOut(
        **base, title=doc.title, description=doc.description, reviewer_id=doc.reviewer_id, reviewed_at=doc.reviewed_at,
        review_note=doc.review_note, renewal_due_date=doc.renewal_due_date, reference_number=doc.reference_number,
        issued_on=doc.issued_on, versions=[VersionOut.model_validate(v) for v in doc.versions],
    )


# ---- Classes & required rules ----


@router.get("/document-classes", response_model=list[DocumentClassOut])
def list_classes(ctx: TenantCtx, db: DB):
    return service.visible_classes(db, ctx.tenant_id)


@router.post("/document-classes", response_model=DocumentClassOut, status_code=201)
def create_class(body: DocumentClassIn, db: DB, ctx=requires(P.DOCUMENT_CONFIGURE)):
    if body.category not in DOC_CATEGORIES:
        raise ValidationFailed("Unknown category", details={"allowed": list(DOC_CATEGORIES)})
    c = DocumentClass(tenant_id=ctx.tenant_id, **body.model_dump())
    db.add(c)
    db.flush()
    audit.record(db, ctx, "document_class.created", "document_class", c.id, metadata=body.model_dump())
    return c


@router.get("/required-document-rules", response_model=list[RuleOut])
def list_rules(ctx: TenantCtx, db: DB):
    return list(
        db.scalars(
            select(RequiredDocumentRule)
            .where(RequiredDocumentRule.tenant_id == ctx.tenant_id)
            .options(selectinload(RequiredDocumentRule.document_class))
        )
    )


@router.post("/required-document-rules", response_model=RuleOut, status_code=201)
def create_rule(body: RuleIn, db: DB, ctx=requires(P.DOCUMENT_CONFIGURE)):
    cls = service.resolve_class(db, ctx.tenant_id, class_id=body.class_id, class_key=None)
    rule = RequiredDocumentRule(tenant_id=ctx.tenant_id, scope=body.scope, class_id=cls.id, land_types=body.land_types)
    rule.document_class = cls
    db.add(rule)
    db.flush()
    audit.record(db, ctx, "required_document_rule.created", "required_document_rule", rule.id, metadata=body.model_dump(mode="json"))
    return rule


@router.delete("/required-document-rules/{rule_id}", status_code=204)
def deactivate_rule(rule_id: uuid.UUID, db: DB, ctx=requires(P.DOCUMENT_CONFIGURE)):
    rule = get_scoped(db, RequiredDocumentRule, rule_id, ctx, label="Rule")
    rule.is_active = False
    audit.record(db, ctx, "required_document_rule.deactivated", "required_document_rule", rule.id)


# ---- Documents ----


@router.get("/documents", response_model=Page[DocumentOut])
def list_documents(
    db: DB,
    property_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
    site_visit_id: uuid.UUID | None = None,
    class_key: list[str] | None = Query(None),
    review_status: str | None = None,
    expiring_before: date | None = None,
    include_archived: bool = False,
    page: PageParams = Depends(),
    ctx=requires(P.DOCUMENT_READ),
):
    stmt = (
        select(Document)
        .where(Document.tenant_id == ctx.tenant_id)
        .options(selectinload(Document.document_class), selectinload(Document.versions))
    )
    for col, val in ((Document.property_id, property_id), (Document.deal_id, deal_id), (Document.owner_id, owner_id), (Document.site_visit_id, site_visit_id)):
        if val:
            stmt = stmt.where(col == val)
    if class_key:
        stmt = stmt.join(DocumentClass, DocumentClass.id == Document.class_id).where(DocumentClass.key.in_(class_key))
    if review_status:
        stmt = stmt.where(Document.review_status == review_status)
    if expiring_before:
        stmt = stmt.where(Document.expiry_date.is_not(None), Document.expiry_date <= expiring_before)
    if not include_archived:
        stmt = stmt.where(Document.is_archived.is_(False))
    rows = db.scalars(stmt.order_by(Document.created_at.desc())).all()
    visible = []
    for d in rows:
        if not service._scope_visible(db, ctx, d):
            continue
        visible.append(to_out(d, redacted=not service.can_access(db, ctx, d)))
    items = visible[page.offset : page.offset + page.limit]
    return {"items": items, "total": len(visible), "limit": page.limit, "offset": page.offset}


@router.post("/documents", response_model=DocumentOut, status_code=201)
def upload_document(
    ctx: TenantCtx,
    db: DB,
    file: UploadFile = File(...),
    title: str = Form(...),
    class_key: str | None = Form(None),
    class_id: uuid.UUID | None = Form(None),
    property_id: uuid.UUID | None = Form(None),
    deal_id: uuid.UUID | None = Form(None),
    owner_id: uuid.UUID | None = Form(None),
    site_visit_id: uuid.UUID | None = Form(None),
    access_policy: AccessPolicy | None = Form(None),
    expiry_date: date | None = Form(None),
    renewal_due_date: date | None = Form(None),
    reference_number: str | None = Form(None),
    issued_on: date | None = Form(None),
    description: str | None = Form(None),
):
    cls = service.resolve_class(db, ctx.tenant_id, class_id=class_id, class_key=class_key)
    doc, _ = service.create_document(
        db, ctx, cls=cls, title=title, stream=file.file, filename=safe_filename(file.filename or "upload"),
        content_type=file.content_type or "application/octet-stream", property_id=property_id, deal_id=deal_id,
        owner_id=owner_id, site_visit_id=site_visit_id, access_policy=access_policy, expiry_date=expiry_date,
        renewal_due_date=renewal_due_date, reference_number=reference_number, issued_on=issued_on, description=description,
    )
    db.refresh(doc)
    return to_out(doc)


@router.get("/documents/completeness")
def get_completeness(ctx: TenantCtx, db: DB, property_id: uuid.UUID | None = None, deal_id: uuid.UUID | None = None):
    return service.completeness(db, ctx, property_id=property_id, deal_id=deal_id)


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: uuid.UUID, ctx: TenantCtx, db: DB):
    return to_out(service.get_accessible(db, ctx, document_id))


@router.patch("/documents/{document_id}", response_model=DocumentOut)
def update_document(document_id: uuid.UUID, body: DocumentUpdate, db: DB, ctx=requires(P.DOCUMENT_UPLOAD)):
    doc = service.get_accessible(db, ctx, document_id, action="update")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("access_policy") == "standard" and doc.document_class.is_sensitive:
        raise ValidationFailed("Sensitive document classes cannot be made standard access")
    before = audit.snapshot(doc)
    for k, v in changes.items():
        setattr(doc, k, v)
    db.flush()
    audit.record_update(db, ctx, "document", doc, before)
    return to_out(doc)


@router.post("/documents/{document_id}/versions", response_model=DocumentOut, status_code=201)
def upload_version(document_id: uuid.UUID, ctx: TenantCtx, db: DB, file: UploadFile = File(...), note: str | None = Form(None)):
    doc = service.get_accessible(db, ctx, document_id, action="version")
    service.add_version(
        db, ctx, doc, stream=file.file, filename=safe_filename(file.filename or "upload"),
        content_type=file.content_type or "application/octet-stream", note=note,
    )
    db.refresh(doc)
    return to_out(doc)


@router.get("/documents/{document_id}/versions/{version_no}/download")
def download(document_id: uuid.UUID, version_no: int, ctx: TenantCtx, db: DB):
    doc = service.get_accessible(db, ctx, document_id, action="download")
    version = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc.id, DocumentVersion.version_no == version_no))
    if version is None:
        raise NotFound("Version not found")
    audit.record(db, ctx, "document.downloaded", "document", doc.id, metadata={"version": version_no})
    db.commit()
    storage = get_storage()
    url = storage.presigned_get(version.storage_key, filename=version.filename, content_type=version.content_type)
    if url:
        return RedirectResponse(url, status_code=302)
    return StreamingResponse(
        storage.open(version.storage_key),
        media_type=version.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{version.filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/documents/{document_id}/review", response_model=DocumentOut)
def review_document(document_id: uuid.UUID, body: ReviewIn, db: DB, ctx=requires(P.DOCUMENT_REVIEW)):
    doc = service.get_accessible(db, ctx, document_id, action="review")
    service.review(db, ctx, doc, decision=body.decision, note=body.note)
    return to_out(doc)


@router.get("/documents/{document_id}/reviews", response_model=list[ReviewOut])
def list_reviews(document_id: uuid.UUID, ctx: TenantCtx, db: DB):
    doc = service.get_accessible(db, ctx, document_id)
    return list(db.scalars(select(DocumentReview).where(DocumentReview.document_id == doc.id).order_by(DocumentReview.reviewed_at)))


@router.get("/documents/{document_id}/grants", response_model=list[GrantOut])
def list_grants(document_id: uuid.UUID, db: DB, ctx=requires(P.DOCUMENT_GRANT)):
    doc = get_scoped(db, Document, document_id, ctx, label="Document")
    return list(db.scalars(select(DocumentAccessGrant).where(DocumentAccessGrant.document_id == doc.id)))


@router.post("/documents/{document_id}/grants", response_model=GrantOut, status_code=201)
def grant_access(document_id: uuid.UUID, body: GrantIn, db: DB, ctx=requires(P.DOCUMENT_GRANT)):
    doc = get_scoped(db, Document, document_id, ctx, label="Document")
    if db.scalar(select(TenantMembership.id).where(TenantMembership.tenant_id == ctx.tenant_id, TenantMembership.user_id == body.user_id)) is None:
        raise NotFound("User is not a member of this tenant")
    grant = db.scalar(select(DocumentAccessGrant).where(DocumentAccessGrant.document_id == doc.id, DocumentAccessGrant.user_id == body.user_id))
    if grant:
        grant.reason, grant.expires_at, grant.revoked_at, grant.granted_by_id = body.reason, body.expires_at, None, ctx.user_id
    else:
        grant = DocumentAccessGrant(document_id=doc.id, granted_by_id=ctx.user_id, **body.model_dump())
        db.add(grant)
    db.flush()
    audit.record(db, ctx, "document.access_granted", "document", doc.id, metadata=body.model_dump(mode="json"))
    return grant


@router.delete("/documents/{document_id}/grants/{user_id}", status_code=204)
def revoke_access(document_id: uuid.UUID, user_id: uuid.UUID, db: DB, ctx=requires(P.DOCUMENT_GRANT)):
    doc = get_scoped(db, Document, document_id, ctx, label="Document")
    grant = db.scalar(select(DocumentAccessGrant).where(DocumentAccessGrant.document_id == doc.id, DocumentAccessGrant.user_id == user_id))
    if grant is None or grant.revoked_at:
        raise NotFound("Grant not found")
    grant.revoked_at = utcnow()
    audit.record(db, ctx, "document.access_revoked", "document", doc.id, metadata={"user_id": str(user_id)})
