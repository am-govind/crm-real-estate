import logging

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import install_error_handlers
from app.core.middleware import RateLimitMiddleware, RequestContextMiddleware
from app.modules.audit.router import router as audit_router
from app.modules.deals.router import router as deals_router
from app.modules.documents.router import router as documents_router
from app.modules.geography.router import router as geography_router
from app.modules.identity.router import auth_router
from app.modules.identity.router import router as identity_router
from app.modules.inventory.router import router as inventory_router
from app.modules.maps.router import router as maps_router
from app.modules.notifications.router import router as notifications_router
from app.modules.owners.router import router as owners_router
from app.modules.payments.router import router as payments_router
from app.modules.properties.router import router as properties_router
from app.modules.reporting.router import router as reporting_router
from app.modules.scoring.router import router as scoring_router
from app.modules.site_visits.router import router as site_visits_router
from app.modules.sync.router import router as sync_router
from app.modules.tasks.router import router as tasks_router
from app.modules.workflows.router import router as workflows_router

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    app = FastAPI(
        title="Land Deal CRM API",
        version="0.1.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs" if settings.env != "production" else None,
        redoc_url=None,
    )
    app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["authorization", "content-type", "x-tenant-id", "x-requested-with", "x-request-id"],
        expose_headers=["x-request-id"],
    )
    install_error_handlers(app)

    api = APIRouter(prefix=API_PREFIX)
    for r in (
        identity_router, audit_router, geography_router, owners_router, properties_router, workflows_router,
        deals_router, tasks_router, documents_router, maps_router, payments_router, site_visits_router,
        inventory_router, scoring_router, reporting_router, notifications_router, sync_router,
    ):
        api.include_router(r)
    app.include_router(api)
    app.include_router(auth_router)

    @app.get("/health", include_in_schema=False)
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/ready", include_in_schema=False)
    def ready() -> dict:
        with SessionLocal() as s:
            s.execute(text("SELECT 1"))
        return {"status": "ready"}

    return app


app = create_app()
