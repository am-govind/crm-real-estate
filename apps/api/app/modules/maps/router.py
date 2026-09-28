import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from app.core.deps import DB, requires
from app.core.errors import NotFound, ValidationFailed
from app.core.jobs import enqueue
from app.core.permissions import P
from app.core.schemas import DecimalStr, ORMModel
from app.core.storage import build_key, get_storage, safe_filename
from app.core.tenancy import get_scoped
from app.modules.audit import service as audit
from app.modules.maps import service
from app.modules.maps.geometry import affine_residuals_m, apply_affine, fit_affine
from app.modules.maps.jobs import latest_run
from app.modules.maps.models import GeometryVersion, MapProcessingRun, MapUpload, NearbyFeature
from app.modules.maps.providers import get_map_provider
from app.modules.properties.access import get_visible_property

router = APIRouter(tags=["maps"])

EXTENSION_KINDS = {
    ".geojson": "geojson", ".json": "geojson", ".kml": "kml", ".pdf": "pdf",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".tif": "image", ".tiff": "image", ".webp": "image",
}


class MapUploadOut(ORMModel):
    id: uuid.UUID
    property_id: uuid.UUID
    file_kind: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    description: str | None
    uploaded_by_id: uuid.UUID | None
    uploaded_at: datetime
    processing_status: str | None = None
    processing_message: str | None = None


class GeometryOut(ORMModel):
    id: uuid.UUID
    property_id: uuid.UUID
    version_no: int
    geojson: dict
    source: str
    source_upload_id: uuid.UUID | None
    source_page: int | None
    georeference: dict
    status: str
    area_sqm: DecimalStr | None
    perimeter_m: DecimalStr | None
    calc_method: str | None
    validation: dict
    confidence: str | None
    notes: str | None
    created_by_id: uuid.UUID | None
    submitted_at: datetime | None
    reviewed_by_id: uuid.UUID | None
    reviewed_at: datetime | None
    review_note: str | None
    created_at: datetime
    is_active: bool = False
    notice: str = service.INFORMATIONAL_NOTICE


class ControlPoint(BaseModel):
    pixel: tuple[float, float]
    lnglat: tuple[float, float]


class GeometryDraftIn(BaseModel):
    """Either a GeoJSON geometry, or pixel rings traced over a scanned upload plus control points."""

    geometry: dict | None = None
    source_upload_id: uuid.UUID | None = None
    source_page: int | None = None
    pixel_rings: list[list[tuple[float, float]]] | None = None
    control_points: list[ControlPoint] | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _one_mode(self):
        if (self.geometry is None) == (self.pixel_rings is None):
            raise ValueError("Provide either geometry or pixel_rings")
        if self.pixel_rings is not None and (not self.control_points or not self.source_upload_id):
            raise ValueError("Traced geometry requires source_upload_id and control_points")
        return self


class ReviewIn(BaseModel):
    note: str | None = None


class RejectIn(BaseModel):
    note: str = Field(min_length=3)


class NearbyOut(ORMModel):
    id: uuid.UUID
    kind: str
    name: str | None
    ref: str | None
    distance_m: float
    latitude: float | None
    longitude: float | None
    source: str
    confidence: str
    fetched_at: datetime
    derived: Literal[True] = True


def _upload_out(db, u: MapUpload) -> MapUploadOut:
    run = latest_run(db, u.id)
    out = MapUploadOut.model_validate(u)
    out.processing_status = run.status if run else None
    out.processing_message = run.message if run else None
    return out


def _geometry_out(gv: GeometryVersion, active_id: uuid.UUID | None) -> GeometryOut:
    out = GeometryOut.model_validate(gv)
    out.is_active = gv.id == active_id
    return out


# ---- Uploads ----


@router.post("/properties/{property_id}/map-uploads", response_model=MapUploadOut, status_code=201)
def upload_map(
    property_id: uuid.UUID,
    db: DB,
    file: UploadFile = File(...),
    description: str | None = Form(None),
    deal_id: uuid.UUID | None = Form(None),
    ctx=requires(P.GEOMETRY_DRAFT),
):
    prop = get_visible_property(db, property_id, ctx)
    filename = safe_filename(file.filename or "map")
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    kind = EXTENSION_KINDS.get(ext)
    if kind is None:
        raise ValidationFailed("Unsupported map file type", details={"allowed": sorted(EXTENSION_KINDS)})
    upload_id = uuid.uuid4()
    stored = get_storage().put(
        build_key(ctx.tenant_id, "maps", upload_id, filename), file.file, file.content_type or "application/octet-stream"
    )
    upload = MapUpload(
        id=upload_id, tenant_id=ctx.tenant_id, property_id=prop.id, deal_id=deal_id, file_kind=kind,
        storage_key=stored.key, filename=filename, content_type=stored.content_type, size_bytes=stored.size_bytes,
        sha256=stored.sha256, description=description, uploaded_by_id=ctx.user_id,
    )
    db.add(upload)
    db.flush()
    run = MapProcessingRun(tenant_id=ctx.tenant_id, upload_id=upload.id)
    db.add(run)
    db.flush()
    job = enqueue(db, "maps.process_upload", {"run_id": str(run.id)}, tenant_id=ctx.tenant_id)
    run.background_job_id = job.id
    audit.record(db, ctx, "map.uploaded", "property", prop.id, metadata={"upload_id": str(upload.id), "kind": kind, "sha256": stored.sha256})
    return _upload_out(db, upload)


@router.get("/properties/{property_id}/map-uploads", response_model=list[MapUploadOut])
def list_uploads(property_id: uuid.UUID, db: DB, ctx=requires(P.PROPERTY_READ)):
    prop = get_visible_property(db, property_id, ctx)
    uploads = db.scalars(select(MapUpload).where(MapUpload.property_id == prop.id).order_by(MapUpload.uploaded_at.desc()))
    return [_upload_out(db, u) for u in uploads]


@router.get("/map-uploads/{upload_id}/file")
def download_upload(upload_id: uuid.UUID, db: DB, ctx=requires(P.PROPERTY_READ)):
    upload = get_scoped(db, MapUpload, upload_id, ctx, label="Map upload")
    get_visible_property(db, upload.property_id, ctx)
    storage = get_storage()
    url = storage.presigned_get(upload.storage_key, filename=upload.filename, content_type=upload.content_type)
    if url:
        return RedirectResponse(url, status_code=302)
    return StreamingResponse(
        storage.open(upload.storage_key), media_type=upload.content_type,
        headers={"Content-Disposition": f'inline; filename="{upload.filename}"', "Cache-Control": "private, no-store"},
    )


@router.post("/map-uploads/{upload_id}/reprocess", response_model=MapUploadOut)
def reprocess(upload_id: uuid.UUID, db: DB, ctx=requires(P.GEOMETRY_DRAFT)):
    upload = get_scoped(db, MapUpload, upload_id, ctx, label="Map upload")
    get_visible_property(db, upload.property_id, ctx)
    run = MapProcessingRun(tenant_id=ctx.tenant_id, upload_id=upload.id)
    db.add(run)
    db.flush()
    run.background_job_id = enqueue(db, "maps.process_upload", {"run_id": str(run.id)}, tenant_id=ctx.tenant_id).id
    return _upload_out(db, upload)


# ---- Geometry versions ----


@router.get("/properties/{property_id}/geometries", response_model=list[GeometryOut])
def list_geometries(property_id: uuid.UUID, db: DB, ctx=requires(P.PROPERTY_READ)):
    prop = get_visible_property(db, property_id, ctx)
    rows = db.scalars(select(GeometryVersion).where(GeometryVersion.property_id == prop.id).order_by(GeometryVersion.version_no.desc()))
    return [_geometry_out(g, prop.active_geometry_id) for g in rows]


@router.get("/properties/{property_id}/geometry/active")
def active_geometry(property_id: uuid.UUID, db: DB, ctx=requires(P.PROPERTY_READ)):
    prop = get_visible_property(db, property_id, ctx)
    if prop.active_geometry_id is None:
        raise NotFound("No approved geometry")
    gv = db.get(GeometryVersion, prop.active_geometry_id)
    return {
        "type": "Feature",
        "geometry": gv.geojson,
        "properties": {
            "property_id": str(prop.id), "geometry_id": str(gv.id), "version": gv.version_no, "source": gv.source,
            "area_sqm": str(gv.area_sqm) if gv.area_sqm is not None else None,
            "perimeter_m": str(gv.perimeter_m) if gv.perimeter_m is not None else None,
            "calc_method": gv.calc_method, "derived": True, "reviewed_by_id": str(gv.reviewed_by_id),
            "reviewed_at": gv.reviewed_at.isoformat() if gv.reviewed_at else None, "notice": service.INFORMATIONAL_NOTICE,
        },
    }


@router.post("/properties/{property_id}/geometries", response_model=GeometryOut, status_code=201)
def create_geometry(property_id: uuid.UUID, body: GeometryDraftIn, db: DB, ctx=requires(P.GEOMETRY_DRAFT)):
    prop = get_visible_property(db, property_id, ctx)
    upload = None
    if body.source_upload_id:
        upload = get_scoped(db, MapUpload, body.source_upload_id, ctx, label="Map upload")
        if upload.property_id != prop.id:
            raise ValidationFailed("Upload belongs to a different property")

    if body.pixel_rings is not None:
        cps = [cp.model_dump() for cp in body.control_points or []]
        transform = fit_affine(cps)
        rmse = affine_residuals_m(transform, cps)
        geometry = apply_affine(transform, [[list(p) for p in ring] for ring in body.pixel_rings])
        georef = {"method": "affine_least_squares", "control_points": cps, "transform": transform, "rmse_m": round(rmse, 2),
                  "pixel_rings": [[list(p) for p in ring] for ring in body.pixel_rings]}
        confidence = "high" if rmse < 2 else "medium" if rmse < 10 else "low"
        source = "manual_trace"
    else:
        geometry = body.geometry
        georef, confidence = {}, None
        source = "manual_trace" if upload else "manual_entry"

    gv = service.create_draft(
        db, ctx, tenant_id=ctx.tenant_id, prop=prop, geometry=geometry, source=source,
        source_upload_id=upload.id if upload else None, source_page=body.source_page, georeference=georef,
        confidence=confidence, notes=body.notes,
    )
    return _geometry_out(gv, prop.active_geometry_id)


def _load(db, ctx, geometry_id):
    gv = get_scoped(db, GeometryVersion, geometry_id, ctx, label="Geometry")
    prop = get_visible_property(db, gv.property_id, ctx)
    return gv, prop


@router.post("/geometries/{geometry_id}/submit", response_model=GeometryOut)
def submit_geometry(geometry_id: uuid.UUID, db: DB, ctx=requires(P.GEOMETRY_DRAFT)):
    gv, prop = _load(db, ctx, geometry_id)
    return _geometry_out(service.submit(db, ctx, gv), prop.active_geometry_id)


@router.post("/geometries/{geometry_id}/approve", response_model=GeometryOut)
def approve_geometry(geometry_id: uuid.UUID, body: ReviewIn, db: DB, ctx=requires(P.GEOMETRY_APPROVE)):
    gv, prop = _load(db, ctx, geometry_id)
    service.approve(db, ctx, gv, prop, note=body.note)
    enqueue(db, "maps.fetch_nearby", {"property_id": str(prop.id)}, tenant_id=ctx.tenant_id)
    return _geometry_out(gv, prop.active_geometry_id)


@router.post("/geometries/{geometry_id}/reject", response_model=GeometryOut)
def reject_geometry(geometry_id: uuid.UUID, body: RejectIn, db: DB, ctx=requires(P.GEOMETRY_APPROVE)):
    gv, prop = _load(db, ctx, geometry_id)
    return _geometry_out(service.reject(db, ctx, gv, note=body.note), prop.active_geometry_id)


# ---- Nearby context & geocoding ----


@router.get("/properties/{property_id}/nearby", response_model=list[NearbyOut])
def list_nearby(property_id: uuid.UUID, db: DB, ctx=requires(P.PROPERTY_READ)):
    prop = get_visible_property(db, property_id, ctx)
    return list(db.scalars(select(NearbyFeature).where(NearbyFeature.property_id == prop.id).order_by(NearbyFeature.distance_m)))


@router.post("/properties/{property_id}/nearby/refresh", status_code=202)
def refresh_nearby(property_id: uuid.UUID, db: DB, ctx=requires(P.PROPERTY_WRITE)):
    prop = get_visible_property(db, property_id, ctx)
    if prop.latitude is None or prop.longitude is None:
        raise ValidationFailed("Property has no location")
    job = enqueue(db, "maps.fetch_nearby", {"property_id": str(prop.id)}, tenant_id=ctx.tenant_id)
    return {"job_id": str(job.id)}


@router.get("/geocode")
def geocode(q: str, ctx=requires(P.PROPERTY_READ)):
    return [
        {"label": r.label, "latitude": r.latitude, "longitude": r.longitude, "source": get_map_provider().name}
        for r in get_map_provider().geocode(q, country="IN")
    ]
