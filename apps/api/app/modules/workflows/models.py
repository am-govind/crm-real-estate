import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, IdMixin, TimestampMixin, uuid_fk

STAGE_CATEGORIES = ("lead", "screening", "diligence", "valuation", "negotiation", "agreement", "payment", "closing", "closed")


class WorkflowTemplate(IdMixin, TimestampMixin, Base):
    """Centrally published by system administrators. Not tenant-owned."""

    __tablename__ = "workflow_templates"

    key: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    land_types: Mapped[list] = mapped_column(default=list)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    versions: Mapped[list["WorkflowTemplateVersion"]] = relationship(
        back_populates="template", order_by="WorkflowTemplateVersion.version"
    )


class WorkflowTemplateVersion(IdMixin, TimestampMixin, Base):
    """Once published, a version (and its stages/checklists) is immutable."""

    __tablename__ = "workflow_template_versions"
    __table_args__ = (UniqueConstraint("template_id", "version", name="uq_template_version"),)

    template_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("workflow_templates.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    notes: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None]
    published_by_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)

    template: Mapped[WorkflowTemplate] = relationship(back_populates="versions")
    stages: Mapped[list["StageDefinition"]] = relationship(
        back_populates="version", order_by="StageDefinition.position", cascade="all, delete-orphan"
    )


class StageDefinition(IdMixin, Base):
    __tablename__ = "stage_definitions"
    __table_args__ = (UniqueConstraint("version_id", "key", name="uq_stage_key"),)

    version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("workflow_template_versions.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(20), default="lead")
    color: Mapped[str | None] = mapped_column(String(9))
    is_terminal: Mapped[bool] = mapped_column(Boolean, default=False)
    is_skippable: Mapped[bool] = mapped_column(Boolean, default=True)
    sla_days: Mapped[int | None] = mapped_column(Integer)

    version: Mapped[WorkflowTemplateVersion] = relationship(back_populates="stages")
    checklist: Mapped[list["ChecklistItemDefinition"]] = relationship(
        back_populates="stage", order_by="ChecklistItemDefinition.position", cascade="all, delete-orphan"
    )


class ChecklistItemDefinition(IdMixin, Base):
    __tablename__ = "checklist_item_definitions"
    __table_args__ = (UniqueConstraint("stage_id", "key", name="uq_checklist_key"),)

    stage_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("stage_definitions.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    document_class_key: Mapped[str | None] = mapped_column(String(80))

    stage: Mapped[StageDefinition] = relationship(back_populates="checklist")


class TenantWorkflowActivation(IdMixin, TimestampMixin, Base):
    """A tenant's activation of a permitted published template version.

    ``config`` may only tailor permitted aspects: stage label overrides, SLA days, and which
    optional (non-required) checklist items are hidden. Stage structure is never changed.
    """

    __tablename__ = "tenant_workflow_activations"
    __table_args__ = (UniqueConstraint("tenant_id", "template_version_id", name="uq_tenant_activation"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    template_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("workflow_template_versions.id"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    land_types: Mapped[list] = mapped_column(default=list)
    config: Mapped[dict] = mapped_column(default=dict)
    activated_by_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)

    template_version: Mapped[WorkflowTemplateVersion] = relationship()


class TenantTemplatePermission(Base):
    """Which system templates a tenant is permitted to activate. No rows means all published templates."""

    __tablename__ = "tenant_template_permissions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), primary_key=True)
    template_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("workflow_templates.id"), primary_key=True)
