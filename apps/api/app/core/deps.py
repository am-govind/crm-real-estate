import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.auth import get_auth_provider
from app.core.config import get_settings
from app.core.context import RequestContext
from app.core.db import SessionLocal, apply_tenant_guc
from app.core.errors import Forbidden, Unauthorized

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "landcrm"


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DB = Annotated[Session, Depends(get_db)]


def get_ctx(
    request: Request,
    db: DB,
    x_tenant_id: Annotated[str | None, Header()] = None,
) -> RequestContext:
    from app.modules.identity.service import build_context, upsert_user_from_claims
    from app.modules.identity.sessions import load_web_session

    settings = get_settings()
    auth_header = request.headers.get("authorization", "")
    token: str | None = None
    via_cookie = False

    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    else:
        raw = request.cookies.get(settings.session_cookie_name)
        if raw:
            _, token = load_web_session(db, raw)
            via_cookie = True

    if not token:
        raise Unauthorized("Authentication required")

    if via_cookie and request.method not in SAFE_METHODS:
        if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
            raise Forbidden("Missing CSRF header")

    claims = get_auth_provider().validate_access_token(token)
    user = upsert_user_from_claims(db, claims)

    # Plain links (downloads opened in a new tab) cannot send headers, so safe requests may pass ?_tenant=.
    requested_tenant = x_tenant_id or (request.query_params.get("_tenant") if request.method in SAFE_METHODS else None)
    tenant_id: uuid.UUID | None = None
    if requested_tenant:
        try:
            tenant_id = uuid.UUID(requested_tenant)
        except ValueError as exc:
            raise Forbidden("Invalid tenant id") from exc

    ctx = build_context(
        db,
        user,
        tenant_id,
        request_id=getattr(request.state, "request_id", None),
        ip_address=request.client.host if request.client else None,
        auth_time=claims.auth_time,
    )
    apply_tenant_guc(db, ctx.tenant_id)
    request.state.ctx = ctx
    return ctx


Ctx = Annotated[RequestContext, Depends(get_ctx)]


def get_tenant_ctx(ctx: Ctx) -> RequestContext:
    ctx.require_tenant()
    return ctx


TenantCtx = Annotated[RequestContext, Depends(get_tenant_ctx)]


def requires(*permissions: str):
    def _dep(ctx: TenantCtx) -> RequestContext:
        ctx.require(*permissions)
        return ctx

    return Depends(_dep)
