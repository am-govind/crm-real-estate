from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_auth_provider
from app.core.auth.crypto import decrypt_json, encrypt_json, hash_token, random_token
from app.core.auth.provider import TokenSet
from app.core.config import get_settings
from app.core.db import utcnow
from app.core.errors import Unauthorized
from app.modules.identity.models import User, WebSession


def _store(tokens: TokenSet, previous: dict | None = None) -> str:
    prev = previous or {}
    return encrypt_json(
        {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token or prev.get("refresh_token"),
            "id_token": tokens.id_token or prev.get("id_token"),
        }
    )


def create_web_session(
    session: Session, user: User, tokens: TokenSet, *, auth_time: int | None, user_agent: str | None
) -> str:
    raw = random_token(48)
    now = utcnow()
    session.add(
        WebSession(
            user_id=user.id,
            session_hash=hash_token(raw),
            encrypted_tokens=_store(tokens),
            access_expires_at=now + timedelta(seconds=tokens.expires_in),
            expires_at=now + timedelta(seconds=get_settings().session_ttl_seconds),
            auth_time=auth_time,
            user_agent=(user_agent or "")[:500] or None,
        )
    )
    session.flush()
    return raw


def load_web_session(session: Session, raw: str) -> tuple[WebSession, str]:
    """Returns the session and a currently valid access token, refreshing server-side if needed."""
    ws = session.scalar(select(WebSession).where(WebSession.session_hash == hash_token(raw)))
    now = utcnow()
    if ws is None or ws.revoked_at is not None or _aware(ws.expires_at) < now:
        raise Unauthorized("Session expired")
    tokens = decrypt_json(ws.encrypted_tokens)
    if _aware(ws.access_expires_at) - timedelta(seconds=30) < now:
        if not tokens.get("refresh_token"):
            raise Unauthorized("Session expired")
        refreshed = get_auth_provider().refresh(tokens["refresh_token"])
        ws.encrypted_tokens = _store(refreshed, tokens)
        ws.access_expires_at = now + timedelta(seconds=refreshed.expires_in)
        tokens["access_token"] = refreshed.access_token
    return ws, tokens["access_token"]


def revoke_web_session(session: Session, raw: str) -> dict | None:
    ws = session.scalar(select(WebSession).where(WebSession.session_hash == hash_token(raw)))
    if ws is None or ws.revoked_at is not None:
        return None
    ws.revoked_at = utcnow()
    tokens = decrypt_json(ws.encrypted_tokens)
    if tokens.get("refresh_token"):
        try:
            get_auth_provider().revoke(tokens["refresh_token"])
        except Exception:  # noqa: BLE001 - revocation is best-effort
            pass
    return tokens


def _aware(dt):
    from datetime import timezone

    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
