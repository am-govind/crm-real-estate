import type { FeatureCollection } from "@landcrm/api-client";
import { formatDerived, GEOMETRY_NOTICE, P, type GeometryVersion, type MapUpload, type Property } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";

import { MapView } from "../../components/MapView";
import { userName, useUsers } from "../../components/TasksPanel";
import { askReason, Badge, Button, Card, DateText, Field, Input, Modal, StatusBadge, Table, Tabs, TextArea, useAction } from "../../components/ui";
import { api } from "../../lib/api";
import { Can, useCan, useMe } from "../../lib/auth";

export function GeometryPanel({ property }: { property: Property }) {
  const me = useMe();
  const allowed = useCan();
  const users = useUsers();
  const pid = property.id;
  const uploads = useQuery({
    queryKey: ["map-uploads", pid],
    queryFn: () => api.maps.uploads(pid),
    refetchInterval: (q) => (q.state.data?.some((u) => u.processing_status === "queued" || u.processing_status === "processing") ? 3000 : false),
  });
  const geoms = useQuery({ queryKey: ["geometries", pid], queryFn: () => api.maps.geometries(pid) });
  const [drafting, setDrafting] = useState<MapUpload | "new" | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const inv = [["geometries", pid], ["properties"], ["map-layers"], ["map-pins"], ["control-center"]];
  const submit = useAction(api.maps.submit, { invalidate: inv, success: "Submitted for review" });
  const approve = useAction((id: string) => api.maps.approve(id, window.prompt("Approval note (optional)") ?? undefined), { invalidate: inv, success: "Approved" });
  const reject = useAction((id: string) => {
    const note = askReason("Why is this boundary rejected?");
    return note ? api.maps.reject(id, note) : Promise.resolve(null);
  }, { invalidate: inv });
  const reprocess = useAction(api.maps.reprocess, { invalidate: [["map-uploads", pid]] });
  const upload = useAction((file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.maps.upload(pid, form);
  }, { invalidate: [["map-uploads", pid], ["geometries", pid]], success: "Uploaded; processing started" });

  const shown = geoms.data?.find((g) => g.id === selected) ?? geoms.data?.find((g) => g.is_active) ?? geoms.data?.[0];
  const parcels = useMemo<FeatureCollection | undefined>(
    () => (shown ? { type: "FeatureCollection", features: [{ type: "Feature", geometry: shown.geojson, properties: { color: shown.is_active ? "#16a34a" : "#f59e0b" } }] } : undefined),
    [shown],
  );

  return (
    <div className="stack">
      <div className="warn">{GEOMETRY_NOTICE}</div>
      <div className="grid grid-2">
        <div className="stack">
          <MapView key={shown?.id ?? "none"} parcels={parcels} small center={property.longitude && property.latitude ? [Number(property.longitude), Number(property.latitude)] : undefined} />
          {shown && (
            <div className="small">
              Showing v{shown.version_no} ({shown.status}). Area {formatDerived(shown.area_sqm)}; perimeter {formatDerived(shown.perimeter_m, "m")}.
              {shown.confidence && <> Georeference confidence: <strong>{shown.confidence}</strong>.</>}
              {!shown.validation.valid && <div className="error-text">Invalid: {shown.validation.errors.join("; ")}</div>}
              {shown.validation.warnings.length > 0 && <div className="muted">Warnings: {shown.validation.warnings.join("; ")}</div>}
            </div>
          )}
        </div>
        <Card
          title="Site-map uploads"
          actions={
            <Can p={P.GEOMETRY_DRAFT}>
              <label className="btn">
                Upload map
                <input type="file" hidden accept=".geojson,.json,.kml,.pdf,.png,.jpg,.jpeg,.tif,.tiff,.webp" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />
              </label>
            </Can>
          }
        >
          <Table
            rows={uploads.data}
            empty="No site maps uploaded. GeoJSON and KML are converted to draft boundaries automatically; scanned maps can be traced."
            columns={[
              { key: "f", header: "File", render: (u) => <a href={api.maps.uploadFileUrl(u.id)} target="_blank" rel="noreferrer">{u.filename}</a> },
              { key: "k", header: "Kind", render: (u) => u.file_kind },
              { key: "s", header: "Processing", render: (u) => <div><StatusBadge status={u.processing_status} />{u.processing_message && <div className="muted small">{u.processing_message}</div>}</div> },
              {
                key: "a",
                header: "",
                render: (u) => (
                  <Can p={P.GEOMETRY_DRAFT}>
                    <div className="row">
                      {u.file_kind === "image" && <Button size="sm" onClick={() => setDrafting(u)}>Trace</Button>}
                      {u.file_kind === "pdf" && <span className="muted small" title="Export the map page as PNG/JPEG and upload it to trace">Upload as image to trace</span>}
                      <Button size="sm" onClick={() => reprocess.mutate(u.id)}>Reprocess</Button>
                    </div>
                  </Can>
                ),
              },
            ]}
          />
        </Card>
      </div>
      <Card title="Boundary versions" actions={<Can p={P.GEOMETRY_DRAFT}><Button variant="primary" onClick={() => setDrafting("new")}>Draw / paste boundary</Button></Can>}>
        <Table
          rows={geoms.data}
          empty="No boundary drafted yet."
          onRowClick={(g) => setSelected(g.id)}
          columns={[
            { key: "v", header: "Version", render: (g) => <span>v{g.version_no} {g.is_active && <Badge tone="success">active</Badge>}</span> },
            { key: "s", header: "Status", render: (g) => <StatusBadge status={g.status} /> },
            { key: "src", header: "Source", render: (g) => g.source },
            { key: "a", header: "Area (derived)", render: (g) => formatDerived(g.area_sqm) },
            { key: "val", header: "Valid", render: (g) => (g.validation.valid ? "Yes" : <span className="error-text">{g.validation.errors.length} issue(s)</span>) },
            { key: "by", header: "Drafted by", render: (g) => userName(users.data, g.created_by_id) },
            { key: "r", header: "Review", render: (g) => (g.reviewed_at ? <span>{userName(users.data, g.reviewed_by_id)} · <DateText value={g.reviewed_at} />{g.review_note && <div className="muted small">{g.review_note}</div>}</span> : "—") },
            {
              key: "x",
              header: "",
              render: (g: GeometryVersion) => (
                <div className="row" onClick={(e) => e.stopPropagation()}>
                  {g.status === "draft" && g.created_by_id === me.id && <Button size="sm" onClick={() => submit.mutate(g.id)}>Submit</Button>}
                  {g.status === "submitted" && allowed(P.GEOMETRY_APPROVE) && g.created_by_id !== me.id && (
                    <>
                      <Button size="sm" variant="primary" disabled={!g.validation.valid} onClick={() => approve.mutate(g.id)}>Approve</Button>
                      <Button size="sm" variant="danger" onClick={() => reject.mutate(g.id)}>Reject</Button>
                    </>
                  )}
                </div>
              ),
            },
          ]}
        />
      </Card>
      {drafting && <DraftBoundary property={property} upload={drafting === "new" ? undefined : drafting} onClose={() => setDrafting(null)} />}
    </div>
  );
}

type Mode = "draw" | "geojson" | "trace";

function DraftBoundary({ property, upload, onClose }: { property: Property; upload?: MapUpload; onClose: () => void }) {
  const [mode, setMode] = useState<Mode>(upload ? "trace" : "draw");
  const [ring, setRing] = useState<[number, number][]>([]);
  const [geojson, setGeojson] = useState("");
  const [notes, setNotes] = useState("");
  const [pixelRing, setPixelRing] = useState<[number, number][]>([]);
  const [controls, setControls] = useState<{ pixel: [number, number]; lng: string; lat: string }[]>([]);
  const [pickControl, setPickControl] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  const inv = [["geometries", property.id]];

  const save = useAction(
    () => {
      if (mode === "trace") {
        return api.maps.createGeometry(property.id, {
          source_upload_id: upload!.id,
          pixel_rings: [[...pixelRing, pixelRing[0]!]],
          control_points: controls.map((c) => ({ pixel: c.pixel, lnglat: [Number(c.lng), Number(c.lat)] })),
          notes: notes || undefined,
        });
      }
      const geometry = mode === "draw" ? { type: "Polygon", coordinates: [[...ring, ring[0]!]] } : JSON.parse(geojson);
      return api.maps.createGeometry(property.id, { geometry: geometry.type === "Feature" ? geometry.geometry : geometry, notes: notes || undefined });
    },
    { invalidate: inv, success: "Draft saved", onSuccess: onClose },
  );

  function onImageClick(e: React.MouseEvent<HTMLDivElement>) {
    const img = imgRef.current;
    if (!img) return;
    const rect = img.getBoundingClientRect();
    const px: [number, number] = [
      Math.round(((e.clientX - rect.left) / rect.width) * img.naturalWidth),
      Math.round(((e.clientY - rect.top) / rect.height) * img.naturalHeight),
    ];
    if (pickControl) {
      setControls([...controls, { pixel: px, lng: "", lat: "" }]);
      setPickControl(false);
    } else setPixelRing([...pixelRing, px]);
  }

  const img = imgRef.current;
  const scale = (p: [number, number]) => (img ? `${(p[0] / img.naturalWidth) * 100}%` : "0");
  const scaleY = (p: [number, number]) => (img ? `${(p[1] / img.naturalHeight) * 100}%` : "0");
  const canSave =
    mode === "draw" ? ring.length >= 3 : mode === "geojson" ? geojson.trim().length > 0 : pixelRing.length >= 3 && controls.length >= 3 && controls.every((c) => c.lng && c.lat);

  return (
    <Modal title="Draft boundary" onClose={onClose} wide>
      <div className="stack">
        <Tabs
          value={mode}
          onChange={setMode}
          tabs={[
            { key: "draw", label: "Draw on map" },
            { key: "geojson", label: "Paste GeoJSON" },
            ...(upload ? [{ key: "trace" as const, label: `Trace over ${upload.filename}` }] : []),
          ]}
        />
        {mode === "draw" && (
          <>
            <div className="muted small">Click the map to add corners in order. At least three points are required.</div>
            <MapView draft={ring} onMapClick={(p) => setRing([...ring, p])} center={property.longitude && property.latitude ? [Number(property.longitude), Number(property.latitude)] : undefined} />
            <div className="row">
              <Button size="sm" onClick={() => setRing(ring.slice(0, -1))} disabled={!ring.length}>Undo point</Button>
              <Button size="sm" onClick={() => setRing([])}>Clear</Button>
              <span className="small muted">{ring.length} points</span>
            </div>
          </>
        )}
        {mode === "geojson" && (
          <Field label="GeoJSON Polygon, MultiPolygon or Feature (WGS84 lng/lat)">
            <TextArea rows={10} value={geojson} onChange={(e) => setGeojson(e.target.value)} className="mono" />
          </Field>
        )}
        {mode === "trace" && upload && (
          <>
            <div className="muted small">
              Click corners of the parcel on the scanned map. Then add at least three control points: click “Add control point”, click a recognisable
              spot on the image, and enter its real longitude and latitude. The fit error is reported as georeference confidence.
            </div>
            <div className="trace-canvas" onClick={onImageClick}>
              <img ref={imgRef} src={api.maps.uploadFileUrl(upload.id)} alt={upload.filename} />
              <svg>
                {pixelRing.map((p, i) => <circle key={`r${i}`} cx={scale(p)} cy={scaleY(p)} r={4} fill="#f59e0b" />)}
                {pixelRing.map((p, i) => {
                  const q = pixelRing[(i + 1) % pixelRing.length]!;
                  return pixelRing.length > 1 ? <line key={`l${i}`} x1={scale(p)} y1={scaleY(p)} x2={scale(q)} y2={scaleY(q)} stroke="#f59e0b" strokeWidth={2} /> : null;
                })}
                {controls.map((c, i) => <circle key={`c${i}`} cx={scale(c.pixel)} cy={scaleY(c.pixel)} r={6} fill="none" stroke="#2563eb" strokeWidth={2} />)}
              </svg>
            </div>
            <div className="row">
              <Button size="sm" onClick={() => setPixelRing(pixelRing.slice(0, -1))} disabled={!pixelRing.length}>Undo corner</Button>
              <Button size="sm" variant={pickControl ? "primary" : "default"} onClick={() => setPickControl(true)}>Add control point</Button>
              <span className="small muted">{pixelRing.length} corners, {controls.length} control points</span>
            </div>
            {controls.map((c, i) => (
              <div key={i} className="row">
                <span className="small mono">#{i + 1} px({c.pixel.join(", ")})</span>
                <Input placeholder="Longitude" value={c.lng} onChange={(e) => setControls(controls.map((x, j) => (j === i ? { ...x, lng: e.target.value } : x)))} style={{ width: 140 }} />
                <Input placeholder="Latitude" value={c.lat} onChange={(e) => setControls(controls.map((x, j) => (j === i ? { ...x, lat: e.target.value } : x)))} style={{ width: 140 }} />
                <Button size="sm" variant="danger" onClick={() => setControls(controls.filter((_, j) => j !== i))}>Remove</Button>
              </div>
            ))}
          </>
        )}
        <Field label="Notes"><Input value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
        <div className="row"><Button variant="primary" disabled={!canSave || save.isPending} onClick={() => save.mutate(undefined)}>Save draft</Button></div>
      </div>
    </Modal>
  );
}
