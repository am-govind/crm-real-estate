"""Local-development auth provider. Accepts bearer tokens of the form ``dev:<email>``.

Settings validation refuses this mode when LANDCRM_ENV=production.
"""

import time
from urllib.parse import urlencode

from app.core.auth.provider import TokenClaims, TokenSet
from app.core.config import get_settings
from app.core.errors import Unauthorized

DEV_ISSUER = "urn:landcrm:dev"


class DevAuthProvider:
    def __init__(self) -> None:
        if get_settings().env == "production":
            raise RuntimeError("DevAuthProvider cannot be used in production")

    def validate_access_token(self, token: str) -> TokenClaims:
        if not token.startswith("dev:") or "@" not in token:
            raise Unauthorized("Dev tokens must look like 'dev:<email>'")
        email = token[4:].strip().lower()
        return TokenClaims(
            issuer=DEV_ISSUER,
            subject=email,
            email=email,
            email_verified=True,
            name=email.split("@")[0],
            expires_at=int(time.time()) + 3600,
            auth_time=int(time.time()),
        )

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str, redirect_uri: str) -> str:
        return f"{redirect_uri}?{urlencode({'state': state, 'code': 'dev:developer@example.com'})}"

    def exchange_code(self, *, code: str, code_verifier: str, redirect_uri: str) -> TokenSet:
        return TokenSet(access_token=code, expires_in=3600, refresh_token=code)

    def refresh(self, refresh_token: str) -> TokenSet:
        return TokenSet(access_token=refresh_token, expires_in=3600, refresh_token=refresh_token)

    def revoke(self, refresh_token: str) -> None:
        return None

    def end_session_url(self, *, id_token_hint: str | None, post_logout_redirect_uri: str) -> str | None:
        return None
