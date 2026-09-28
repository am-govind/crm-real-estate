from functools import lru_cache

from app.core.auth.provider import AuthProvider
from app.core.config import get_settings


@lru_cache
def get_auth_provider() -> AuthProvider:
    settings = get_settings()
    if settings.auth_mode == "dev":
        from app.core.auth.dev import DevAuthProvider

        return DevAuthProvider()
    from app.core.auth.oidc import OIDCAuthProvider

    return OIDCAuthProvider(settings)
