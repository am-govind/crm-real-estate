import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, IdMixin, TimestampMixin, uuid_fk


class Tenant(IdMixin, TimestampMixin, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    country_code: Mapped[str] = mapped_column(String(2), default="IN")
    default_currency: Mapped[str] = mapped_column(String(3), default="INR")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    settings: Mapped[dict] = mapped_column(default=dict)


class User(IdMixin, TimestampMixin, Base):
    """A person, identified by an OIDC issuer + subject. Tenant access is via memberships."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("oidc_issuer", "oidc_subject", name="uq_user_oidc_identity"),)

    oidc_issuer: Mapped[str] = mapped_column(String(500))
    oidc_subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_system_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None]

    memberships: Mapped[list["TenantMembership"]] = relationship(back_populates="user", foreign_keys="TenantMembership.user_id")


class Role(IdMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_role_tenant_key"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)

    permissions: Mapped[list["RolePermission"]] = relationship(cascade="all, delete-orphan", back_populates="role")


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission: Mapped[str] = mapped_column(String(80), primary_key=True)

    role: Mapped[Role] = relationship(back_populates="permissions")


class TenantMembership(IdMixin, TimestampMixin, Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_membership"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    title: Mapped[str | None] = mapped_column(String(200))
    invited_by_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)

    user: Mapped[User] = relationship(back_populates="memberships", foreign_keys=[user_id])
    roles: Mapped[list["MembershipRole"]] = relationship(cascade="all, delete-orphan")


class MembershipRole(Base):
    __tablename__ = "membership_roles"

    membership_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenant_memberships.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)

    role: Mapped[Role] = relationship()


class TenantInvitation(IdMixin, TimestampMixin, Base):
    """Grants tenant membership to the user who signs in with this verified email."""

    __tablename__ = "tenant_invitations"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_invitation_email"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    role_keys: Mapped[list] = mapped_column(default=list)
    invited_by_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", index=False)
    accepted_at: Mapped[datetime | None]
    expires_at: Mapped[datetime | None]


class WebSession(IdMixin, TimestampMixin, Base):
    """Backend-for-frontend session. Tokens never reach browser JavaScript."""

    __tablename__ = "web_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    session_hash: Mapped[str] = mapped_column(String(128), unique=True)
    encrypted_tokens: Mapped[str] = mapped_column(Text)
    access_expires_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    auth_time: Mapped[int | None]
    user_agent: Mapped[str | None] = mapped_column(String(500))


class LoginAttempt(IdMixin, TimestampMixin, Base):
    """Short-lived PKCE state for the web authorization-code flow."""

    __tablename__ = "login_attempts"

    state: Mapped[str] = mapped_column(String(128), unique=True)
    code_verifier: Mapped[str] = mapped_column(String(128))
    nonce: Mapped[str] = mapped_column(String(128))
    return_to: Mapped[str | None] = mapped_column(String(1000))
    expires_at: Mapped[datetime]
