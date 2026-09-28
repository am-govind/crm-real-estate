import uuid
from datetime import timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.auth import get_auth_provider
from app.core.auth.crypto import pkce_challenge, random_token
from app.core.config import get_settings
from app.core.deps import DB, Ctx, TenantCtx, requires
from app.core.db import utcnow
from app.core.errors import Forbidden, NotFound, Unauthorized, ValidationFailed
from app.core.permissions import ALL_PERMISSIONS, P
from app.modules.audit import service as audit
from app.modules.identity import service
from app.modules.identity.models import (
    LoginAttempt,
    MembershipRole,
    Role,
    RolePermission,
    Tenant,
    TenantInvitation,
    TenantMembership,
    User,
)
from app.modules.identity.schemas import (
    InvitationCreate,
    InvitationOut,
    MemberOut,
    MembershipSummary,
    MemberUpdate,
    MeOut,
    RoleOut,
    RoleUpsert,
    TenantCreate,
    TenantOut,
    TenantSettingsUpdate,
    UserOut,
)
from app.modules.identity.sessions import create_web_session, revoke_web_session

DEFAULT_TERMINOLOGY = {"state": "State", "district": "District", "tehsil": "Tehsil", "village": "Village"}

auth_router = APIRouter(prefix="/auth", tags=["auth"])
router = APIRouter(tags=["identity"])


def _safe_return_to(value: str | None) -> str:
    settings = get_settings()
    if not value:
        return settings.web_app_url
    parsed = urlparse(value)
    allowed = urlparse(settings.web_app_url)
    if parsed.scheme and (parsed.scheme, parsed.netloc) != (allowed.scheme, allowed.netloc):
        return settings.web_app_url
    return value if parsed.scheme else settings.web_app_url.rstrip("/") + "/" + value.lstrip("/")


def _callback_uri() -> str:
    return get_settings().public_api_url.rstrip("/") + "/auth/callback"


@auth_router.get("/login")
def login(db: DB, return_to: str | None = None) -> RedirectResponse:
    verifier = random_token(48)
    attempt = LoginAttempt(
        state=random_token(24),
        code_verifier=verifier,
        nonce=random_token(24),
        return_to=_safe_return_to(return_to),
        expires_at=utcnow() + timedelta(minutes=10),
    )
    db.add(attempt)
    url = get_auth_provider().authorization_url(
        state=attempt.state, nonce=attempt.nonce, code_challenge=pkce_challenge(verifier), redirect_uri=_callback_uri()
    )
    return RedirectResponse(url, status_code=302)


@auth_router.get("/callback")
def callback(request: Request, db: DB, code: str, state: str) -> RedirectResponse:
    attempt = db.scalar(select(LoginAttempt).where(LoginAttempt.state == state))
    if attempt is None:
        raise Unauthorized("Unknown login attempt")
    expires = attempt.expires_at if attempt.expires_at.tzinfo else attempt.expires_at.replace(tzinfo=utcnow().tzinfo)
    if expires < utcnow():
        db.delete(attempt)
        raise Unauthorized("Login attempt expired")
    provider = get_auth_provider()
    tokens = provider.exchange_code(code=code, code_verifier=attempt.code_verifier, redirect_uri=_callback_uri())
    claims = provider.validate_access_token(tokens.access_token)
    user = service.upsert_user_from_claims(db, claims)
    user.last_login_at = utcnow()
    raw = create_web_session(db, user, tokens, auth_time=claims.auth_time, user_agent=request.headers.get("user-agent"))
    return_to = attempt.return_to or get_settings().web_app_url
    db.delete(attempt)
    audit.record(db, None, "auth.login", "user", user.id, metadata={"channel": "web"})

    settings = get_settings()
    resp = RedirectResponse(return_to, status_code=302)
    resp.set_cookie(
        settings.session_cookie_name,
        raw,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return resp


@auth_router.post("/logout")
def logout(request: Request, response: Response, db: DB) -> dict:
    settings = get_settings()
    raw = request.cookies.get(settings.session_cookie_name)
    end_session_url = None
    if raw:
        tokens = revoke_web_session(db, raw)
        if tokens is not None:
            end_session_url = get_auth_provider().end_session_url(
                id_token_hint=tokens.get("id_token"), post_logout_redirect_uri=settings.web_app_url
            )
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"end_session_url": end_session_url}


@router.get("/me", response_model=MeOut)
def me(ctx: Ctx, db: DB) -> MeOut:
    user = db.get(User, ctx.user_id)
    assert user is not None
    memberships = db.scalars(
        select(TenantMembership)
        .where(TenantMembership.user_id == user.id, TenantMembership.is_active.is_(True))
        .options(selectinload(TenantMembership.roles).selectinload(MembershipRole.role))
    ).all()
    tenants = {t.id: t for t in db.scalars(select(Tenant).where(Tenant.id.in_([m.tenant_id for m in memberships])))}
    terminology = dict(DEFAULT_TERMINOLOGY)
    if ctx.tenant_id and ctx.tenant_id in tenants:
        terminology.update(tenants[ctx.tenant_id].settings.get("terminology", {}))
    return MeOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_system_admin=user.is_system_admin,
        tenant_id=ctx.tenant_id,
        permissions=sorted(ctx.permissions),
        role_keys=sorted(ctx.role_keys),
        memberships=[
            MembershipSummary(
                tenant_id=m.tenant_id,
                tenant_name=tenants[m.tenant_id].name if m.tenant_id in tenants else "",
                role_keys=sorted(r.role.key for r in m.roles),
            )
            for m in memberships
        ],
        terminology=terminology,
    )


@router.get("/permissions", response_model=list[str])
def list_permissions(_: Ctx) -> list[str]:
    return sorted(ALL_PERMISSIONS)


# ---- System administration ----


@router.post("/admin/tenants", response_model=TenantOut, status_code=201)
def create_tenant(body: TenantCreate, ctx: Ctx, db: DB) -> Tenant:
    if not ctx.is_system_admin:
        raise Forbidden("System administrator only")
    tenant = service.create_tenant(
        db, ctx, name=body.name, slug=body.slug, country_code=body.country_code, default_currency=body.default_currency
    )
    if body.admin_email:
        db.add(TenantInvitation(tenant_id=tenant.id, email=body.admin_email.lower(), role_keys=["tenant_admin"], invited_by_id=ctx.user_id))
    return tenant


@router.get("/admin/tenants", response_model=list[TenantOut])
def list_tenants(ctx: Ctx, db: DB) -> list[Tenant]:
    if not ctx.is_system_admin:
        raise Forbidden("System administrator only")
    return list(db.scalars(select(Tenant).order_by(Tenant.name)))


# ---- Current tenant ----


@router.get("/tenant", response_model=TenantOut)
def get_tenant(ctx: TenantCtx, db: DB) -> Tenant:
    tenant = db.get(Tenant, ctx.tenant_id)
    if tenant is None:
        raise NotFound("Tenant not found")
    return tenant


@router.patch("/tenant/settings", response_model=TenantOut)
def update_tenant_settings(body: TenantSettingsUpdate, db: DB, ctx=requires(P.TENANT_MANAGE)) -> Tenant:
    tenant = db.get(Tenant, ctx.tenant_id)
    assert tenant is not None
    before = dict(tenant.settings)
    tenant.settings = {**before, **body.settings}
    audit.record(db, ctx, "tenant.settings_updated", "tenant", tenant.id, changes={"from": before, "to": tenant.settings})
    return tenant


@router.get("/tenant/users", response_model=list[UserOut])
def list_tenant_users(ctx: TenantCtx, db: DB) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .join(TenantMembership, TenantMembership.user_id == User.id)
            .where(TenantMembership.tenant_id == ctx.tenant_id, TenantMembership.is_active.is_(True))
            .order_by(User.display_name)
        )
    )


@router.get("/tenant/members", response_model=list[MemberOut])
def list_members(db: DB, ctx=requires(P.USER_MANAGE)) -> list[MemberOut]:
    rows = db.scalars(
        select(TenantMembership)
        .where(TenantMembership.tenant_id == ctx.tenant_id)
        .options(selectinload(TenantMembership.user), selectinload(TenantMembership.roles).selectinload(MembershipRole.role))
    ).all()
    return [
        MemberOut(
            membership_id=m.id,
            user=UserOut.model_validate(m.user),
            is_active=m.is_active,
            title=m.title,
            role_keys=sorted(r.role.key for r in m.roles),
        )
        for m in rows
    ]


@router.patch("/tenant/members/{membership_id}", response_model=MemberOut)
def update_member(membership_id: uuid.UUID, body: MemberUpdate, db: DB, ctx=requires(P.USER_MANAGE)) -> MemberOut:
    m = db.get(TenantMembership, membership_id)
    if m is None or m.tenant_id != ctx.tenant_id:
        raise NotFound("Member not found")
    before = {"roles": sorted(r.role.key for r in m.roles), "is_active": m.is_active, "title": m.title}
    if body.role_keys is not None:
        service.set_membership_roles(db, m, body.role_keys)
    if body.is_active is not None:
        if m.user_id == ctx.user_id and not body.is_active:
            raise ValidationFailed("You cannot deactivate yourself")
        m.is_active = body.is_active
    if body.title is not None:
        m.title = body.title
    db.flush()
    db.refresh(m)
    after = {"roles": sorted(r.role.key for r in m.roles), "is_active": m.is_active, "title": m.title}
    audit.record(db, ctx, "membership.updated", "tenant_membership", m.id, changes={"from": before, "to": after})
    return MemberOut(
        membership_id=m.id, user=UserOut.model_validate(m.user), is_active=m.is_active, title=m.title, role_keys=after["roles"]
    )


@router.get("/tenant/invitations", response_model=list[InvitationOut])
def list_invitations(db: DB, ctx=requires(P.USER_MANAGE)) -> list[TenantInvitation]:
    return list(db.scalars(select(TenantInvitation).where(TenantInvitation.tenant_id == ctx.tenant_id)))


@router.post("/tenant/invitations", response_model=InvitationOut, status_code=201)
def create_invitation(body: InvitationCreate, db: DB, ctx=requires(P.USER_MANAGE)) -> TenantInvitation:
    return service.invite(db, ctx, email=body.email, role_keys=body.role_keys)


def _role_out(role: Role) -> RoleOut:
    return RoleOut(
        id=role.id, key=role.key, name=role.name, description=role.description, is_builtin=role.is_builtin,
        permissions=sorted(p.permission for p in role.permissions),
    )


@router.get("/tenant/roles", response_model=list[RoleOut])
def list_roles(ctx: TenantCtx, db: DB) -> list[RoleOut]:
    roles = db.scalars(select(Role).where(Role.tenant_id == ctx.tenant_id).options(selectinload(Role.permissions)))
    return [_role_out(r) for r in roles]


@router.post("/tenant/roles", response_model=RoleOut, status_code=201)
def create_role(body: RoleUpsert, db: DB, ctx=requires(P.ROLE_MANAGE)) -> RoleOut:
    unknown = set(body.permissions) - ALL_PERMISSIONS
    if unknown:
        raise ValidationFailed("Unknown permissions", details={"permissions": sorted(unknown)})
    role = Role(tenant_id=ctx.tenant_id, key=body.key, name=body.name, description=body.description)
    role.permissions = [RolePermission(permission=p) for p in sorted(set(body.permissions))]
    db.add(role)
    db.flush()
    audit.record(db, ctx, "role.created", "role", role.id, metadata={"key": role.key, "permissions": body.permissions})
    return _role_out(role)


@router.put("/tenant/roles/{role_id}", response_model=RoleOut)
def update_role(role_id: uuid.UUID, body: RoleUpsert, db: DB, ctx=requires(P.ROLE_MANAGE)) -> RoleOut:
    role = db.get(Role, role_id)
    if role is None or role.tenant_id != ctx.tenant_id:
        raise NotFound("Role not found")
    unknown = set(body.permissions) - ALL_PERMISSIONS
    if unknown:
        raise ValidationFailed("Unknown permissions", details={"permissions": sorted(unknown)})
    before = sorted(p.permission for p in role.permissions)
    role.name = body.name
    role.description = body.description
    role.permissions = [RolePermission(permission=p) for p in sorted(set(body.permissions))]
    db.flush()
    audit.record(db, ctx, "role.updated", "role", role.id, changes={"permissions": {"from": before, "to": sorted(set(body.permissions))}})
    return _role_out(role)
