"""Provider-neutral authentication boundary (Keycloak, Zitadel, Auth0, Entra ID, Google, ...)."""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class TokenClaims:
    issuer: str
    subject: str
    email: str | None = None
    email_verified: bool = False
    name: str | None = None
    expires_at: int | None = None
    auth_time: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    expires_in: int
    refresh_token: str | None = None
    id_token: str | None = None


class AuthProvider(Protocol):
    def validate_access_token(self, token: str) -> TokenClaims: ...

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str, redirect_uri: str) -> str: ...

    def exchange_code(self, *, code: str, code_verifier: str, redirect_uri: str) -> TokenSet: ...

    def refresh(self, refresh_token: str) -> TokenSet: ...

    def revoke(self, refresh_token: str) -> None: ...

    def end_session_url(self, *, id_token_hint: str | None, post_logout_redirect_uri: str) -> str | None: ...
