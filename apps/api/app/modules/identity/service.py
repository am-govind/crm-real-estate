import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.auth.provider import TokenClaims
from app.core.context import RequestContext
from app.core.db import utcnow
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.permissions import ALL_PERMISSIONS, DEFAULT_ROLES
from app.modules.audit import service as audit
from app.modules.identity.models import (
    MembershipRole,
    Role,
    RolePermission,
    Tenant,
    TenantInvitation,
    TenantMembership,
    User,
)


def upsert_user_from_claims(session: Session, claims: TokenClaims) -> User:
    user = session.scalar(
        select(User).where(User.oidc_issuer == claims.issuer, User.oidc_subject == claims.subject)
    )
    if user is None:
        user = User(
            oidc_issuer=claims.issuer,
            oidc_subject=claims.subject,
            email=(claims.email or "").lower() or None,
            display_name=claims.name,
        )
        session.add(user)
        session.flush()
        audit.record(session, None, "user.provisioned", "user", user.id, metadata={"issuer": claims.issuer})
    else:
        if claims.email and claims.email_verified:
            user.email = claims.email.lower()
        if claims.name:
            user.display_name = claims.name
    if not user.is_active:
        raise Forbidden("User is deactivated")
    if claims.email and claims.email_verified:
        _accept_invitations(session, user)
    return user


def _accept_invitations(session: Session, user: User) -> None:
    invitations = session.scalars(
        select(TenantInvitation).where(TenantInvitation.email == user.email, TenantInvitation.accepted_at.is_(None))
    ).all()
    now = utcnow()
    for inv in invitations:
        if inv.expires_at and inv.expires_at < now:
            continue
        membership = session.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == inv.tenant_id, TenantMembership.user_id == user.id
            )
        )
        if membership is None:
            membership = TenantMembership(tenant_id=inv.tenant_id, user_id=user.id, invited_by_id=inv.invited_by_id)
            session.add(membership)
            session.flush()
        set_membership_roles(session, membership, inv.role_keys)
        inv.accepted_at = now
        audit.record(
            session, None, "membership.invitation_accepted", "tenant_membership", membership.id,
            tenant_id=inv.tenant_id, metadata={"user_id": str(user.id), "roles": inv.role_keys},
        )


def set_membership_roles(session: Session, membership: TenantMembership, role_keys: list[str]) -> None:
    roles = session.scalars(
        select(Role).where(Role.tenant_id == membership.tenant_id, Role.key.in_(role_keys))
    ).all()
    found = {r.key for r in roles}
    missing = set(role_keys) - found
    if missing:
        raise NotFound("Unknown roles", details={"roles": sorted(missing)})
    membership.roles = [MembershipRole(role_id=r.id) for r in roles]


def build_context(
    session: Session,
    user: User,
    requested_tenant_id: uuid.UUID | None,
    *,
    request_id: str | None = None,
    ip_address: str | None = None,
    auth_time: int | None = None,
) -> RequestContext:
    memberships = session.scalars(
        select(TenantMembership)
        .where(TenantMembership.user_id == user.id, TenantMembership.is_active.is_(True))
        .options(selectinload(TenantMembership.roles).selectinload(MembershipRole.role).selectinload(Role.permissions))
    ).all()

    membership: TenantMembership | None = None
    if requested_tenant_id is not None:
        membership = next((m for m in memberships if m.tenant_id == requested_tenant_id), None)
        if membership is None and not user.is_system_admin:
            raise Forbidden("You are not a member of this tenant")
    elif len(memberships) == 1:
        membership = memberships[0]

    tenant_id = membership.tenant_id if membership else requested_tenant_id
    if tenant_id is not None:
        tenant = session.get(Tenant, tenant_id)
        if tenant is None or not tenant.is_active:
            raise Forbidden("Tenant is not active")

    permissions: set[str] = set()
    role_keys: set[str] = set()
    if membership:
        for mr in membership.roles:
            role_keys.add(mr.role.key)
            permissions.update(rp.permission for rp in mr.role.permissions)
    if user.is_system_admin:
        permissions = set(ALL_PERMISSIONS)

    return RequestContext(
        user_id=user.id,
        tenant_id=tenant_id,
        email=user.email,
        is_system_admin=user.is_system_admin,
        permissions=frozenset(permissions),
        role_keys=frozenset(role_keys),
        request_id=request_id,
        ip_address=ip_address,
        auth_time=auth_time,
    )


def seed_default_roles(session: Session, tenant: Tenant) -> list[Role]:
    roles = []
    for key, spec in DEFAULT_ROLES.items():
        role = session.scalar(select(Role).where(Role.tenant_id == tenant.id, Role.key == key))
        if role is None:
            role = Role(tenant_id=tenant.id, key=key, name=spec["name"], is_builtin=True)
            session.add(role)
        role.permissions = [RolePermission(permission=str(p)) for p in sorted(spec["permissions"])]
        roles.append(role)
    session.flush()
    return roles


def create_tenant(session: Session, ctx: RequestContext | None, *, name: str, slug: str, **extra) -> Tenant:
    if session.scalar(select(Tenant).where(Tenant.slug == slug)):
        raise Conflict("Tenant slug already in use")
    tenant = Tenant(name=name, slug=slug, **extra)
    session.add(tenant)
    session.flush()
    seed_default_roles(session, tenant)
    audit.record(session, ctx, "tenant.created", "tenant", tenant.id, tenant_id=tenant.id, metadata={"slug": slug})
    return tenant


def invite(session: Session, ctx: RequestContext, *, email: str, role_keys: list[str]) -> TenantInvitation:
    tenant_id = ctx.require_tenant()
    email = email.lower()
    existing = session.scalar(
        select(TenantInvitation).where(TenantInvitation.tenant_id == tenant_id, TenantInvitation.email == email)
    )
    if existing and existing.accepted_at is None:
        existing.role_keys = role_keys
        inv = existing
    else:
        inv = TenantInvitation(tenant_id=tenant_id, email=email, role_keys=role_keys, invited_by_id=ctx.user_id)
        session.add(inv)
    session.flush()
    audit.record(session, ctx, "membership.invited", "tenant_invitation", inv.id, metadata={"email": email, "roles": role_keys})
    return inv
