from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LANDCRM_", env_file=".env", extra="ignore")

    env: Literal["development", "staging", "production"] = "development"
    database_url: str = "sqlite:///./landcrm.db"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    public_api_url: str = "http://localhost:8000"
    web_app_url: str = "http://localhost:5173"

    auth_mode: Literal["oidc", "dev"] = "oidc"
    oidc_issuer: str = "http://localhost:8080/realms/landcrm"
    oidc_audience: str = "landcrm-api"
    oidc_web_client_id: str = "landcrm-web"
    oidc_web_client_secret: str = ""
    oidc_mobile_client_id: str = "landcrm-mobile"
    oidc_jwks_cache_seconds: int = 3600
    oidc_scopes: str = "openid profile email offline_access"

    session_secret: str = "change-me"
    session_cookie_name: str = "landcrm_session"
    session_cookie_secure: bool = False
    session_ttl_seconds: int = 60 * 60 * 12

    storage_backend: Literal["local", "s3"] = "local"
    storage_local_root: str = "./.storage"
    s3_endpoint_url: str | None = None
    s3_bucket: str = "landcrm-documents"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "us-east-1"
    presigned_url_ttl_seconds: int = 300
    max_upload_bytes: int = 200 * 1024 * 1024

    queue_backend: Literal["inline", "redis"] = "inline"
    redis_url: str = "redis://localhost:6379/0"

    map_provider: Literal["none", "osm"] = "none"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    map_user_agent: str = "landcrm/0.1"

    rate_limit_per_minute: int = 300
    document_expiry_reminder_days: int = 30
    default_currency: str = "INR"

    @model_validator(mode="after")
    def _guard_production(self) -> "Settings":
        if self.env == "production":
            if self.auth_mode == "dev":
                raise ValueError("Dev auth mode is not allowed in production")
            if self.session_secret in ("", "change-me"):
                raise ValueError("A strong LANDCRM_SESSION_SECRET is required in production")
            if not self.session_cookie_secure:
                raise ValueError("Session cookies must be secure in production")
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
