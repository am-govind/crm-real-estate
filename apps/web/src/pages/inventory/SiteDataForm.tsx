import { AREA_UNITS, INVENTORY_PROPERTY_TYPES, INVENTORY_STATUSES, LENGTH_UNITS, type Edge, type LandPlotData, type Measurement, type SiteData } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";

import { Button, Card, Field, Input, Select, TextArea } from "../../components/ui";
import { api } from "../../lib/api";

const AREA_OPTS = AREA_UNITS.map((u) => ({ value: u.key, label: u.label }));
const LENGTH_OPTS = LENGTH_UNITS.map((u) => ({ value: u.key, label: u.label }));

export function emptySiteData(type: SiteData["property_type"] = "land_plot"): SiteData {
  const common = { status: "available", source: {}, location: {} };
  if (type === "land_plot") return { ...common, property_type: "land_plot", cut_dimensions: [], edges: [] };
  if (type === "commercial_unit") return { ...common, property_type: "commercial_unit" };
  return { ...common, property_type: type };
}

/** Drops empty strings and incomplete measurements so the API receives only what was entered. */
export function normalizeSiteData(data: SiteData): SiteData {
  const walk = (v: unknown): unknown => {
    if (Array.isArray(v)) return v.map(walk).filter((x) => x !== undefined);
    if (v && typeof v === "object") {
      const o = v as Record<string, unknown>;
      if ("unit" in o && "value" in o && Object.keys(o).length === 2) return o.value === "" ? undefined : o;
      const out: Record<string, unknown> = {};
      for (const [k, val] of Object.entries(o)) {
        const w = walk(val);
        if (w !== undefined && w !== "") out[k] = w;
      }
      return out;
    }
    return v;
  };
  const out = walk(data) as SiteData;
  if (out.property_type === "land_plot") {
    out.edges = (out.edges ?? []).filter((e) => e.name && e.length);
    out.cut_dimensions = (out.cut_dimensions ?? []).filter((e) => e.name && e.length);
  }
  const loc = out.location;
  if (loc.latitude !== undefined && loc.latitude !== null) loc.latitude = Number(loc.latitude);
  if (loc.longitude !== undefined && loc.longitude !== null) loc.longitude = Number(loc.longitude);
  return out;
}

function MeasureInput({ label, value, onChange, units }: { label: string; value?: Measurement | null; onChange: (m: Measurement | null) => void; units: { value: string; label: string }[] }) {
  return (
    <Field label={label}>
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <Input inputMode="decimal" value={value?.value ?? ""} onChange={(e) => onChange(e.target.value ? { value: e.target.value, unit: value?.unit ?? units[0]!.value } : null)} />
        <Select value={value?.unit ?? units[0]!.value} onChange={(e) => onChange({ value: value?.value ?? "", unit: e.target.value })} options={units} style={{ width: 150 }} />
      </div>
    </Field>
  );
}

function EdgeList({ title, edges, onChange }: { title: string; edges: Edge[]; onChange: (e: Edge[]) => void }) {
  return (
    <Card title={title} actions={<Button size="sm" type="button" onClick={() => onChange([...edges, { name: "", length: { value: "", unit: "ft" } }])}>Add</Button>}>
      {edges.length === 0 && <span className="muted small">None.</span>}
      {edges.map((e, i) => (
        <div key={i} className="row" style={{ marginBottom: 6 }}>
          <Input placeholder="Name (e.g. North, Front, Cut 1)" value={e.name} onChange={(ev) => onChange(edges.map((x, j) => (j === i ? { ...x, name: ev.target.value } : x)))} style={{ width: 200 }} />
          <Input placeholder="Length" inputMode="decimal" value={e.length.value} onChange={(ev) => onChange(edges.map((x, j) => (j === i ? { ...x, length: { ...x.length, value: ev.target.value } } : x)))} style={{ width: 110 }} />
          <Select value={e.length.unit} onChange={(ev) => onChange(edges.map((x, j) => (j === i ? { ...x, length: { ...x.length, unit: ev.target.value } } : x)))} options={LENGTH_OPTS} style={{ width: 90 }} />
          <Input placeholder="Direction" value={e.direction ?? ""} onChange={(ev) => onChange(edges.map((x, j) => (j === i ? { ...x, direction: ev.target.value } : x)))} style={{ width: 110 }} />
          <Button size="sm" variant="danger" type="button" onClick={() => onChange(edges.filter((_, j) => j !== i))}>Remove</Button>
        </div>
      ))}
    </Card>
  );
}

export function SiteDataForm({ value, onChange, lockType }: { value: SiteData; onChange: (d: SiteData) => void; lockType?: boolean }) {
  const properties = useQuery({ queryKey: ["properties", "picker"], queryFn: () => api.properties.list({ limit: 500 }) });
  const propertyId = value.location.property_id ?? "";
  const uploads = useQuery({ queryKey: ["map-uploads", propertyId], queryFn: () => api.maps.uploads(propertyId), enabled: !!propertyId });
  const docs = useQuery({ queryKey: ["documents", { property_id: propertyId }], queryFn: () => api.documents.list({ property_id: propertyId, limit: 500 }), enabled: !!propertyId });
  const set = (patch: Partial<SiteData>) => onChange({ ...value, ...patch } as SiteData);
  const setAny = (k: string, v: unknown) => onChange({ ...value, [k]: v } as SiteData);
  const setLoc = (k: string, v: unknown) => onChange({ ...value, location: { ...value.location, [k]: v } });
  const setSrc = (k: string, v: unknown) => onChange({ ...value, source: { ...value.source, [k]: v } });
  const d = value as SiteData & Record<string, unknown>;

  return (
    <div className="stack">
      <div className="grid grid-3">
        <Field label="Property type">
          <Select disabled={lockType} value={value.property_type} onChange={(e) => onChange({ ...emptySiteData(e.target.value as SiteData["property_type"]), location: value.location, source: value.source, status: value.status })} options={INVENTORY_PROPERTY_TYPES} />
        </Field>
        <Field label="Inventory status"><Select value={value.status} onChange={(e) => set({ status: e.target.value })} options={INVENTORY_STATUSES} /></Field>
      </div>

      <Card title="Location">
        <div className="grid grid-3">
          <Field label="Linked property">
            <Select value={propertyId} onChange={(e) => setLoc("property_id", e.target.value || undefined)} placeholder="None"
              options={(properties.data?.items ?? []).map((p) => ({ value: p.id, label: `${p.code} · ${p.name}` }))} />
          </Field>
          <Field label="Project / layout name"><Input value={value.location.project_name ?? ""} onChange={(e) => setLoc("project_name", e.target.value)} /></Field>
          <Field label="Address"><Input value={value.location.address ?? ""} onChange={(e) => setLoc("address", e.target.value)} /></Field>
          <Field label="Latitude"><Input inputMode="decimal" value={value.location.latitude ?? ""} onChange={(e) => setLoc("latitude", e.target.value === "" ? undefined : e.target.value)} /></Field>
          <Field label="Longitude"><Input inputMode="decimal" value={value.location.longitude ?? ""} onChange={(e) => setLoc("longitude", e.target.value === "" ? undefined : e.target.value)} /></Field>
          <Field label="Location description"><Input value={value.location.description ?? ""} onChange={(e) => setLoc("description", e.target.value)} /></Field>
        </div>
      </Card>

      <Card title="Source">
        <div className="grid grid-3">
          <Field label="Source document">
            <Select value={value.source.document_id ?? ""} onChange={(e) => setSrc("document_id", e.target.value || undefined)} placeholder={propertyId ? "None" : "Link a property first"}
              options={(docs.data?.items ?? []).filter((x) => !x.is_redacted).map((x) => ({ value: x.id, label: x.title ?? x.class_name }))} />
          </Field>
          <Field label="Source site map">
            <Select value={value.source.map_upload_id ?? ""} onChange={(e) => setSrc("map_upload_id", e.target.value || undefined)} placeholder={propertyId ? "None" : "Link a property first"}
              options={(uploads.data ?? []).map((u) => ({ value: u.id, label: u.filename }))} />
          </Field>
          <Field label="Page number"><Input type="number" min={1} value={value.source.page_number ?? ""} onChange={(e) => setSrc("page_number", e.target.value ? Number(e.target.value) : undefined)} /></Field>
          <Field label="Label on map"><Input value={value.source.map_label ?? ""} onChange={(e) => setSrc("map_label", e.target.value)} /></Field>
          <Field label="Region reference"><Input value={value.source.region_reference ?? ""} onChange={(e) => setSrc("region_reference", e.target.value)} /></Field>
          <Field label="Layout reference"><Input value={value.source.layout_reference ?? ""} onChange={(e) => setSrc("layout_reference", e.target.value)} /></Field>
        </div>
      </Card>

      {value.property_type === "land_plot" && (
        <>
          <Card title="Plot dimensions (as recorded)">
            <div className="grid grid-3">
              <Field label="Plot label / number"><Input value={value.plot_label ?? ""} onChange={(e) => set({ plot_label: e.target.value } as Partial<LandPlotData>)} /></Field>
              <MeasureInput label="Area" value={value.area} onChange={(m) => setAny("area", m)} units={AREA_OPTS} />
              <MeasureInput label="Frontage" value={value.frontage} onChange={(m) => setAny("frontage", m)} units={LENGTH_OPTS} />
              <MeasureInput label="Length" value={value.length} onChange={(m) => setAny("length", m)} units={LENGTH_OPTS} />
              <MeasureInput label="Width" value={value.width} onChange={(m) => setAny("width", m)} units={LENGTH_OPTS} />
              <Field label="Road type"><Input value={value.road_access?.road_type ?? ""} onChange={(e) => setAny("road_access", { ...value.road_access, road_type: e.target.value })} /></Field>
              <MeasureInput label="Road width" value={value.road_access?.road_width} onChange={(m) => setAny("road_access", { ...value.road_access, road_width: m })} units={LENGTH_OPTS} />
            </div>
            <div className="muted small">Irregular plots: record each edge and any cut dimensions below instead of forcing a length × width.</div>
          </Card>
          <EdgeList title="Edges" edges={value.edges} onChange={(e) => setAny("edges", e)} />
          <EdgeList title="Cut dimensions" edges={value.cut_dimensions} onChange={(e) => setAny("cut_dimensions", e)} />
        </>
      )}

      {(value.property_type === "apartment" || value.property_type === "studio_flat" || value.property_type === "commercial_unit") && (
        <Card title="Unit details (as recorded)">
          <div className="grid grid-3">
            <Field label="Unit number"><Input value={(d.unit_number as string) ?? ""} onChange={(e) => setAny("unit_number", e.target.value)} /></Field>
            <Field label="Floor"><Input value={(d.floor as string) ?? ""} onChange={(e) => setAny("floor", e.target.value)} /></Field>
            <MeasureInput label="Total area" value={d.total_area as Measurement} onChange={(m) => setAny("total_area", m)} units={AREA_OPTS} />
            <MeasureInput label="Carpet area" value={d.carpet_area as Measurement} onChange={(m) => setAny("carpet_area", m)} units={AREA_OPTS} />
            <MeasureInput label="Built-up area" value={d.built_up_area as Measurement} onChange={(m) => setAny("built_up_area", m)} units={AREA_OPTS} />
            {value.property_type !== "commercial_unit" ? (
              <>
                <MeasureInput label="Super built-up area" value={d.super_built_up_area as Measurement} onChange={(m) => setAny("super_built_up_area", m)} units={AREA_OPTS} />
                <Field label="Rooms"><Input type="number" min={0} value={(d.rooms as number | undefined) ?? ""} onChange={(e) => setAny("rooms", e.target.value === "" ? undefined : Number(e.target.value))} /></Field>
                <Field label="Bathrooms"><Input type="number" min={0} value={(d.bathrooms as number | undefined) ?? ""} onChange={(e) => setAny("bathrooms", e.target.value === "" ? undefined : Number(e.target.value))} /></Field>
              </>
            ) : (
              <>
                <MeasureInput label="Frontage" value={d.frontage as Measurement} onChange={(m) => setAny("frontage", m)} units={LENGTH_OPTS} />
                <Field label="Access"><Input value={(d.access as string) ?? ""} onChange={(e) => setAny("access", e.target.value)} /></Field>
                <Field label="Usage type"><Input value={(d.usage_type as string) ?? ""} onChange={(e) => setAny("usage_type", e.target.value)} /></Field>
              </>
            )}
          </div>
        </Card>
      )}
      <Field label="Notes"><TextArea value={value.notes ?? ""} onChange={(e) => set({ notes: e.target.value })} /></Field>
    </div>
  );
}
