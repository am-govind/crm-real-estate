import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import ActorMixin, Base, IdMixin, TenantScopedMixin, TimestampMixin, utcnow, uuid_fk

DOC_CATEGORIES = ("ownership", "property", "transaction", "identity", "financial", "internal")
ACCESS_POLICIES = ("standard", "restricted", "confidential")
REVIEW_STATUSES = ("pending_review", "approved", "rejected", "needs_changes")


class DocumentClass(IdMixin, TimestampMixin, Base):
    """Classification. ``tenant_id`` null means a system-wide class available to every tenant."""

    __tablename__ = "document_classes"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_document_class_key"),)

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(20))
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    default_access_policy: Mapped[str] = mapped_column(String(20), default="standard")
    requires_expiry: Mapped[bool] = mapped_column(Boolean, default=False)
    applies_to: Mapped[list] = mapped_column(default=list)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Document(IdMixin, TimestampMixin, TenantScopedMixin, ActorMixin, Base):
    __tablename__ = "documents"

    class_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("document_classes.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    property_id: Mapped[uuid.UUID | None] = uuid_fk("properties.id")
    deal_id: Mapped[uuid.UUID | None] = uuid_fk("deals.id")
    owner_id: Mapped[uuid.UUID | None] = uuid_fk("owners.id")
    site_visit_id: Mapped[uuid.UUID | None] = uuid_fk("site_visits.id")
    access_policy: Mapped[str] = mapped_column(String(20), default="standard")
    review_status: Mapped[str] = mapped_column(String(20), default="pending_review", index=True)
    reviewer_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)
    reviewed_at: Mapped[datetime | None]
    review_note: Mapped[str | None] = mapped_column(Text)
    current_version_no: Mapped[int] = mapped_column(Integer, default=0)
    expiry_date: Mapped[date | None] = mapped_column(index=True)
    renewal_due_date: Mapped[date | None]
    reference_number: Mapped[str | None] = mapped_column(String(200))
    issued_on: Mapped[date | None]
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    document_class: Mapped[DocumentClass] = relationship()
    versions: Mapped[list["DocumentVersion"]] = relationship(back_populates="document", order_by="DocumentVersion.version_no")


class DocumentVersion(IdMixin, Base):
    """Immutable file version. New uploads always create a new version."""

    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_no", name="uq_document_version"),)

    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("documents.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(600))
    filename: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(150))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    note: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    uploaded_by_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)
    uploaded_at: Mapped[datetime] = mapped_column(default=utcnow)

    document: Mapped[Document] = relationship(back_populates="versions")


class DocumentReview(IdMixin, Base):
    __tablename__ = "document_reviews"

    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("documents.id"), index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("document_versions.id"))
    decision: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    reviewed_at: Mapped[datetime] = mapped_column(default=utcnow)


class DocumentAccessGrant(IdMixin, TimestampMixin, Base):
    __tablename__ = "document_access_grants"
    __table_args__ = (UniqueConstraint("document_id", "user_id", name="uq_document_grant"),)

    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("documents.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    granted_by_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]


class RequiredDocumentRule(IdMixin, TimestampMixin, TenantScopedMixin, Base):
    """Documents expected for completeness. Deal completeness also includes checklist-linked classes."""

    __tablename__ = "required_document_rules"
    __table_args__ = (UniqueConstraint("tenant_id", "scope", "class_id", name="uq_required_doc_rule"),)

    scope: Mapped[str] = mapped_column(String(20))
    class_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("document_classes.id"))
    land_types: Mapped[list] = mapped_column(default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    document_class: Mapped[DocumentClass] = relationship()
