import uuid
from datetime import date
from typing import BinaryIO

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.db import utcnow
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.permissions import P
from app.core.storage import build_key, get_storage
from app.core.tenancy import get_scoped
from app.modules.audit import service as audit
from app.modules.documents.models import (
    Document,
    DocumentAccessGrant,
    DocumentClass,
    DocumentReview,
    DocumentVersion,
    RequiredDocumentRule,
)

BLOCKED_EXTENSIONS = {".exe", ".bat", ".cmd", ".sh", ".js", ".msi", ".html", ".htm", ".php", ".jar", ".ps1", ".dll"}


# ---- Classes ----


def visible_classes(session: Session, tenant_id: uuid.UUID) -> list[DocumentClass]:
    rows = session.scalars(
        select(DocumentClass).where(
            or_(DocumentClass.tenant_id.is_(None), DocumentClass.tenant_id == tenant_id), DocumentClass.is_active.is_(True)
        )
    ).all()
    by_key: dict[str, DocumentClass] = {}
    for c in rows:
        if c.key not in by_key or c.tenant_id is not None:
            by_key[c.key] = c
    return sorted(by_key.values(), key=lambda c: (c.category, c.name))


def resolve_class(session: Session, tenant_id: uuid.UUID, *, class_id: uuid.UUID | None, class_key: str | None) -> DocumentClass:
    if class_id:
        c = session.get(DocumentClass, class_id)
        if c is None or c.tenant_id not in (None, tenant_id):
            raise NotFound("Document class not found")
        return c
    if class_key:
        for c in visible_classes(session, tenant_id):
            if c.key == class_key:
                return c
    raise NotFound("Document class not found")


# ---- Access policy ----


def _has_grant(session: Session, doc: Document, user_id: uuid.UUID) -> bool:
    now = utcnow()
    grant = session.scalar(
        select(DocumentAccessGrant).where(
            DocumentAccessGrant.document_id == doc.id,
            DocumentAccessGrant.user_id == user_id,
            DocumentAccessGrant.revoked_at.is_(None),
        )
    )
    if grant is None:
        return False
    if grant.expires_at is not None:
        exp = grant.expires_at if grant.expires_at.tzinfo else grant.expires_at.replace(tzinfo=now.tzinfo)
        return exp > now
    return True


def is_sensitive(doc: Document) -> bool:
    return doc.document_class.is_sensitive or doc.access_policy in ("restricted", "confidential")


def can_access(session: Session, ctx: RequestContext, doc: Document) -> bool:
    if not ctx.has(P.DOCUMENT_READ):
        return False
    if not _scope_visible(session, ctx, doc):
        return False
    if doc.created_by_id == ctx.user_id:
        return True
    if doc.access_policy == "confidential":
        return _has_grant(session, doc, ctx.user_id)
    if is_sensitive(doc):
        return ctx.has(P.DOCUMENT_SENSITIVE_READ) or _has_grant(session, doc, ctx.user_id)
    return True


def _scope_visible(session: Session, ctx: RequestContext, doc: Document) -> bool:
    from app.modules.deals.access import get_visible_deal
    from app.modules.properties.access import get_visible_property

    try:
        if doc.deal_id:
            get_visible_deal(session, doc.deal_id, ctx)
        elif doc.property_id:
            get_visible_property(session, doc.property_id, ctx)
    except NotFound:
        return False
    return True


def get_accessible(session: Session, ctx: RequestContext, doc_id: uuid.UUID, *, action: str = "view") -> Document:
    doc = get_scoped(session, Document, doc_id, ctx, label="Document")
    if not can_access(session, ctx, doc):
        audit.record(session, ctx, "document.access_denied", "document", doc.id, metadata={"action": action})
        raise Forbidden("You do not have access to this document")
    if is_sensitive(doc):
        audit.record(session, ctx, f"document.sensitive_{action}", "document", doc.id)
    return doc


# ---- Uploads ----


def _check_upload(ctx: RequestContext, cls: DocumentClass, filename: str) -> None:
    ctx.require(P.DOCUMENT_UPLOAD)
    if cls.is_sensitive:
        ctx.require(P.DOCUMENT_SENSITIVE_UPLOAD)
    lower = filename.lower()
    if any(lower.endswith(ext) for ext in BLOCKED_EXTENSIONS):
        raise ValidationFailed("This file type is not allowed")


def _store_version(session: Session, ctx: RequestContext, doc: Document, *, stream: BinaryIO, filename: str, content_type: str, note: str | None) -> DocumentVersion:
    stored = get_storage().put(build_key(doc.tenant_id, "documents", doc.id, filename), stream, content_type)
    doc.current_version_no += 1
    version = DocumentVersion(
        document_id=doc.id, version_no=doc.current_version_no, storage_key=stored.key, filename=filename,
        content_type=content_type, size_bytes=stored.size_bytes, sha256=stored.sha256, note=note,
        uploaded_by_id=ctx.user_id,
    )
    session.add(version)
    doc.review_status = "pending_review"
    doc.reviewer_id = None
    doc.reviewed_at = None
    doc.review_note = None
    session.flush()
    return version


def create_document(
    session: Session,
    ctx: RequestContext,
    *,
    cls: DocumentClass,
    title: str,
    stream: BinaryIO,
    filename: str,
    content_type: str,
    property_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
    site_visit_id: uuid.UUID | None = None,
    access_policy: str | None = None,
    expiry_date: date | None = None,
    renewal_due_date: date | None = None,
    reference_number: str | None = None,
    issued_on: date | None = None,
    description: str | None = None,
) -> tuple[Document, DocumentVersion]:
    from app.modules.deals.access import get_visible_deal
    from app.modules.owners.models import Owner
    from app.modules.properties.access import get_visible_property

    _check_upload(ctx, cls, filename)
    if not any((property_id, deal_id, owner_id, site_visit_id)):
        raise ValidationFailed("A document must be linked to a property, deal, owner or site visit")
    if deal_id:
        deal = get_visible_deal(session, deal_id, ctx)
        property_id = property_id or deal.property_id
    if property_id:
        get_visible_property(session, property_id, ctx)
    if owner_id:
        get_scoped(session, Owner, owner_id, ctx, label="Owner")
    if cls.requires_expiry and expiry_date is None:
        raise ValidationFailed(f"{cls.name} requires an expiry date")

    policy = access_policy or cls.default_access_policy
    if cls.is_sensitive and policy == "standard":
        policy = "restricted"

    doc = Document(
        tenant_id=ctx.tenant_id, class_id=cls.id, title=title, description=description, property_id=property_id,
        deal_id=deal_id, owner_id=owner_id, site_visit_id=site_visit_id, access_policy=policy,
        expiry_date=expiry_date, renewal_due_date=renewal_due_date, reference_number=reference_number,
        issued_on=issued_on, created_by_id=ctx.user_id,
    )
    doc.document_class = cls
    session.add(doc)
    session.flush()
    version = _store_version(session, ctx, doc, stream=stream, filename=filename, content_type=content_type, note=None)
    audit.record(
        session, ctx, "document.uploaded", "document", doc.id,
        metadata={"class": cls.key, "version": version.version_no, "sha256": version.sha256, "size": version.size_bytes,
                  "property_id": property_id, "deal_id": deal_id, "owner_id": owner_id, "access_policy": policy},
    )
    return doc, version


def add_version(session: Session, ctx: RequestContext, doc: Document, *, stream: BinaryIO, filename: str, content_type: str, note: str | None) -> DocumentVersion:
    _check_upload(ctx, doc.document_class, filename)
    version = _store_version(session, ctx, doc, stream=stream, filename=filename, content_type=content_type, note=note)
    audit.record(
        session, ctx, "document.version_added", "document", doc.id,
        metadata={"version": version.version_no, "sha256": version.sha256, "size": version.size_bytes, "note": note},
    )
    return version


def review(session: Session, ctx: RequestContext, doc: Document, *, decision: str, note: str | None) -> Document:
    ctx.require(P.DOCUMENT_REVIEW)
    version = session.scalar(
        select(DocumentVersion).where(DocumentVersion.document_id == doc.id, DocumentVersion.version_no == doc.current_version_no)
    )
    if version is None:
        raise Conflict("Document has no versions to review")
    if version.uploaded_by_id == ctx.user_id and not ctx.is_system_admin:
        raise Forbidden("Reviewers cannot approve their own uploads")
    if decision in ("rejected", "needs_changes") and not note:
        raise ValidationFailed("A note is required when rejecting or requesting changes")
    before = doc.review_status
    doc.review_status = decision
    doc.reviewer_id = ctx.user_id
    doc.reviewed_at = utcnow()
    doc.review_note = note
    session.add(DocumentReview(document_id=doc.id, version_id=version.id, decision=decision, note=note, reviewer_id=ctx.user_id))
    audit.record(
        session, ctx, "document.reviewed", "document", doc.id,
        changes={"review_status": {"from": before, "to": decision}}, metadata={"version": version.version_no, "note": note},
    )
    return doc


# ---- Completeness ----


def _required_classes(session: Session, ctx: RequestContext, *, scope: str, land_type: str | None) -> dict[str, DocumentClass]:
    rules = session.scalars(
        select(RequiredDocumentRule).where(
            RequiredDocumentRule.tenant_id == ctx.tenant_id,
            RequiredDocumentRule.scope == scope,
            RequiredDocumentRule.is_active.is_(True),
        )
    ).all()
    out = {}
    for r in rules:
        if r.land_types and land_type not in r.land_types:
            continue
        out[r.document_class.key] = r.document_class
    return out


def completeness(session: Session, ctx: RequestContext, *, property_id: uuid.UUID | None = None, deal_id: uuid.UUID | None = None) -> dict:
    from app.modules.deals.access import get_visible_deal
    from app.modules.deals.models import DealChecklistItem
    from app.modules.properties.access import get_visible_property
    from app.modules.workflows.models import ChecklistItemDefinition

    classes = {c.key: c for c in visible_classes(session, ctx.require_tenant())}
    bypassed: set[str] = set()

    if deal_id:
        deal = get_visible_deal(session, deal_id, ctx)
        prop = get_visible_property(session, deal.property_id, ctx)
        required = _required_classes(session, ctx, scope="deal", land_type=prop.land_type)
        required.update(_required_classes(session, ctx, scope="property", land_type=prop.land_type))
        for item, definition in session.execute(
            select(DealChecklistItem, ChecklistItemDefinition)
            .join(ChecklistItemDefinition, ChecklistItemDefinition.id == DealChecklistItem.item_definition_id)
            .where(DealChecklistItem.deal_id == deal.id, ChecklistItemDefinition.document_class_key.is_not(None))
        ).all():
            if item.is_hidden or not item.is_required:
                continue
            key = definition.document_class_key
            if key in classes:
                required[key] = classes[key]
                if item.status in ("bypassed", "not_applicable"):
                    bypassed.add(key)
        docs_stmt = select(Document).where(
            Document.tenant_id == ctx.tenant_id,
            Document.is_archived.is_(False),
            or_(Document.deal_id == deal.id, (Document.property_id == prop.id) & Document.deal_id.is_(None)),
        )
    elif property_id:
        prop = get_visible_property(session, property_id, ctx)
        required = _required_classes(session, ctx, scope="property", land_type=prop.land_type)
        docs_stmt = select(Document).where(
            Document.tenant_id == ctx.tenant_id, Document.is_archived.is_(False), Document.property_id == prop.id
        )
    else:
        raise ValidationFailed("property_id or deal_id is required")

    docs = session.scalars(docs_stmt).all()
    by_class: dict[uuid.UUID, list[Document]] = {}
    for d in docs:
        by_class.setdefault(d.class_id, []).append(d)

    items = []
    received = 0
    for key, cls in sorted(required.items(), key=lambda kv: kv[1].name):
        matches = [d for d in by_class.get(cls.id, []) if d.review_status != "rejected"]
        if matches:
            status = "approved" if any(d.review_status == "approved" for d in matches) else "received"
            received += 1
        elif key in bypassed:
            status = "bypassed"
        elif by_class.get(cls.id):
            status = "rejected"
        else:
            status = "missing"
        expired = [d for d in matches if d.expiry_date and d.expiry_date < date.today()]
        items.append(
            {
                "class_key": key, "class_name": cls.name, "category": cls.category, "status": status,
                "document_ids": [str(d.id) for d in matches], "has_expired": bool(expired),
            }
        )
    total = len(required)
    return {
        "received": received,
        "required": total,
        "label": f"{received}/{total} received",
        "percent": round(100 * received / total) if total else 100,
        "missing": [i for i in items if i["status"] in ("missing", "rejected")],
        "items": items,
    }
