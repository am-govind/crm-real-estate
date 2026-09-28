import json
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.jobs import BackgroundJob, job_handler
from app.core.storage import get_storage
from app.modules.maps import service
from app.modules.maps.geometry import geometry_from_geojson, geometry_from_kml
from app.modules.maps.models import MapProcessingRun, MapUpload, NearbyFeature
from app.modules.maps.providers import get_map_provider
from app.modules.properties.models import Property


@job_handler("maps.process_upload")
def process_upload(session: Session, job: BackgroundJob) -> dict:
    run = session.get(MapProcessingRun, uuid.UUID(job.payload["run_id"]))
    assert run is not None
    upload = session.get(MapUpload, run.upload_id)
    prop = session.get(Property, upload.property_id)
    run.status = "processing"
    session.commit()

    try:
        if upload.file_kind in ("pdf", "image"):
            run.status = "needs_manual_trace"
            run.message = "Scanned maps require manual tracing and georeferencing"
            session.commit()
            return {"status": run.status}

        raw = get_storage().read_bytes(upload.storage_key)
        if upload.file_kind == "geojson":
            geometries = geometry_from_geojson(json.loads(raw))
        else:
            geometries = geometry_from_kml(raw)

        if not geometries:
            run.status = "no_geometry_found"
            run.message = "No polygon geometry found in the upload"
            session.commit()
            return {"status": run.status}

        ids = []
        for geom in geometries[:20]:
            gv = service.create_draft(
                session, None, tenant_id=upload.tenant_id, prop=prop, geometry=geom,
                source=f"upload_{upload.file_kind}", source_upload_id=upload.id, confidence="source_file",
            )
            ids.append(str(gv.id))
        run.status = "extracted"
        run.extracted_geometry_ids = ids
        run.message = f"{len(ids)} draft geometr{'y' if len(ids) == 1 else 'ies'} created; review required before activation"
        session.commit()
        return {"status": run.status, "geometry_ids": ids}
    except Exception as exc:
        session.rollback()
        run = session.get(MapProcessingRun, run.id)
        run.status = "failed"
        run.message = str(exc)[:2000]
        session.commit()
        raise


@job_handler("maps.fetch_nearby")
def fetch_nearby(session: Session, job: BackgroundJob) -> dict:
    prop = session.get(Property, uuid.UUID(job.payload["property_id"]))
    if prop is None or prop.latitude is None or prop.longitude is None:
        return {"skipped": "no location"}
    provider = get_map_provider()
    results = provider.nearby(float(prop.latitude), float(prop.longitude))
    session.execute(delete(NearbyFeature).where(NearbyFeature.property_id == prop.id, NearbyFeature.source == provider.name))
    for r in results:
        session.add(
            NearbyFeature(
                tenant_id=prop.tenant_id, property_id=prop.id, kind=r.kind, name=r.name, ref=r.ref,
                distance_m=r.distance_m, latitude=r.latitude, longitude=r.longitude, source=provider.name,
                confidence=r.confidence, raw=r.raw,
            )
        )
    session.commit()
    return {"count": len(results), "provider": provider.name}


def latest_run(session: Session, upload_id: uuid.UUID) -> MapProcessingRun | None:
    return session.scalar(
        select(MapProcessingRun).where(MapProcessingRun.upload_id == upload_id).order_by(MapProcessingRun.created_at.desc())
    )
