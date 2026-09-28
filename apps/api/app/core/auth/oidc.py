import threading
import time
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from app.core.auth.provider import TokenClaims, TokenSet
from app.core.config import Settings
from app.core.errors import Unauthorized


class OIDCAuthProvider:
    """Generic OIDC provider using discovery, JWKS validation and authorization code + PKCE."""

    def __init__(self, settings: Settings):
        self._s = settings
        self._lock = threading.Lock()
        self._discovery: dict[str, Any] | None = None
        self._jwk_client: jwt.PyJWKClient | None = None
        self._discovered_at = 0.0

    def _meta(self) -> dict[str, Any]:
        with self._lock:
            stale = time.time() - self._discovered_at > self._s.oidc_jwks_cache_seconds
            if self._discovery is None or stale:
                url = self._s.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration"
                resp = httpx.get(url, timeout=10)
                resp.raise_for_status()
                self._discovery = resp.json()
                self._jwk_client = jwt.PyJWKClient(
                    self._discovery["jwks_uri"], cache_keys=True, lifespan=self._s.oidc_jwks_cache_seconds
                )
                self._discovered_at = time.time()
            return self._discovery

    def validate_access_token(self, token: str) -> TokenClaims:
        meta = self._meta()
        assert self._jwk_client is not None
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=meta.get("id_token_signing_alg_values_supported", ["RS256"]),
                audience=self._s.oidc_audience,
                issuer=meta["issuer"],
                options={"require": ["exp", "iat", "sub", "iss"]},
                leeway=30,
            )
        except jwt.PyJWTError as exc:
            raise Unauthorized(f"Invalid access token: {exc}") from exc
        return TokenClaims(
            issuer=claims["iss"],
            subject=claims["sub"],
            email=claims.get("email"),
            email_verified=bool(claims.get("email_verified", False)),
            name=claims.get("name") or claims.get("preferred_username"),
            expires_at=claims.get("exp"),
            auth_time=claims.get("auth_time"),
            raw=claims,
        )

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str, redirect_uri: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self._s.oidc_web_client_id,
            "redirect_uri": redirect_uri,
            "scope": self._s.oidc_scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{self._meta()['authorization_endpoint']}?{urlencode(params)}"

    def _token_request(self, data: dict[str, str]) -> TokenSet:
        data = {**data, "client_id": self._s.oidc_web_client_id}
        auth = None
        if self._s.oidc_web_client_secret:
            auth = (self._s.oidc_web_client_id, self._s.oidc_web_client_secret)
        resp = httpx.post(self._meta()["token_endpoint"], data=data, auth=auth, timeout=15)
        if resp.status_code >= 400:
            raise Unauthorized("Token request rejected by identity provider", details={"status": resp.status_code})
        body = resp.json()
        return TokenSet(
            access_token=body["access_token"],
            expires_in=int(body.get("expires_in", 300)),
            refresh_token=body.get("refresh_token"),
            id_token=body.get("id_token"),
        )

    def exchange_code(self, *, code: str, code_verifier: str, redirect_uri: str) -> TokenSet:
        return self._token_request(
            {"grant_type": "authorization_code", "code": code, "code_verifier": code_verifier, "redirect_uri": redirect_uri}
        )

    def refresh(self, refresh_token: str) -> TokenSet:
        return self._token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})

    def revoke(self, refresh_token: str) -> None:
        endpoint = self._meta().get("revocation_endpoint")
        if not endpoint:
            return
        auth = None
        if self._s.oidc_web_client_secret:
            auth = (self._s.oidc_web_client_id, self._s.oidc_web_client_secret)
        httpx.post(
            endpoint,
            data={"token": refresh_token, "token_type_hint": "refresh_token", "client_id": self._s.oidc_web_client_id},
            auth=auth,
            timeout=10,
        )

    def end_session_url(self, *, id_token_hint: str | None, post_logout_redirect_uri: str) -> str | None:
        endpoint = self._meta().get("end_session_endpoint")
        if not endpoint:
            return None
        params = {"post_logout_redirect_uri": post_logout_redirect_uri, "client_id": self._s.oidc_web_client_id}
        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        return f"{endpoint}?{urlencode(params)}"
