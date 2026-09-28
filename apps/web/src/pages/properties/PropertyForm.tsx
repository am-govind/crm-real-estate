import { AREA_UNITS, LAND_TYPES, LENGTH_UNITS, PROPERTY_STATUSES, ROAD_ACCESS, TITLE_STATUSES, type Property } from "@landcrm/domain";
import { useState } from "react";

import { GeoPicker, type GeoValue } from "../../components/GeoPicker";
import { Button, clean, Field, Input, Modal, Select, TextArea, useAction, useForm } from "../../components/ui";
import { api } from "../../lib/api";

const DECIMAL = /^\d+(\.\d+)?$/;
const COORD = /^-?\d+(\.\d+)?$/;

export function PropertyForm({ property, onClose, onSaved }: { property?: Property; onClose: () => void; onSaved?: (p: Property) => void }) {
  const [v, set] = useForm({
    name: property?.name ?? "",
    land_type: property?.land_type ?? "agricultural",
    status: property?.status ?? "prospect",
    survey_number: property?.survey_number ?? "",
    khasra_number: property?.khasra_number ?? "",
    khata_number: property?.khata_number ?? "",
    address: property?.address ?? "",
    pincode: property?.pincode ?? "",
    latitude: property?.latitude ?? "",
    longitude: property?.longitude ?? "",
    area_value: property?.area_value ?? "",
    area_unit: property?.area_unit ?? "acre",
    land_use: property?.land_use ?? "",
    road_access: property?.road_access ?? "unknown",
    road_frontage_value: property?.road_frontage_value ?? "",
    road_frontage_unit: property?.road_frontage_unit ?? "ft",
    title_status: property?.title_status ?? "unknown",
    notes: property?.notes ?? "",
  });
  const [geo, setGeo] = useState<GeoValue>({
    state_id: property?.state_id ?? undefined,
    district_id: property?.district_id ?? undefined,
    tehsil_id: property?.tehsil_id ?? undefined,
    village_id: property?.village_id ?? undefined,
  });
  const [error, setError] = useState<string | null>(null);

  const save = useAction(
    async () => {
      const { status, ...rest } = v;
      const body: Record<string, unknown> = { ...clean(rest), ...geo };
      if (!v.area_value) delete body.area_unit;
      if (!v.road_frontage_value) delete body.road_frontage_unit;
      if (property) return api.properties.update(property.id, { ...body, status });
      return api.properties.create(body);
    },
    { invalidate: [["properties"], ["map-pins"]], success: property ? "Property updated" : "Property created", onSuccess: (p) => { onSaved?.(p); onClose(); } },
  );

  function submit(e: React.FormEvent) {
    e.preventDefault();
    for (const [k, re] of [["area_value", DECIMAL], ["road_frontage_value", DECIMAL], ["latitude", COORD], ["longitude", COORD]] as const) {
      if (v[k] && !re.test(String(v[k]))) return setError(`${k.replace(/_/g, " ")} must be a plain number`);
    }
    setError(null);
    save.mutate(undefined);
  }

  return (
    <Modal title={property ? `Edit ${property.code}` : "New property"} onClose={onClose} wide>
      <form className="stack" onSubmit={submit}>
        <div className="grid grid-3">
          <Field label="Name"><Input required value={v.name} onChange={set("name")} /></Field>
          <Field label="Land type"><Select value={v.land_type} onChange={set("land_type")} options={LAND_TYPES} /></Field>
          {property && <Field label="Status"><Select value={v.status} onChange={set("status")} options={PROPERTY_STATUSES} /></Field>}
        </div>
        <GeoPicker value={geo} onChange={setGeo} />
        <div className="grid grid-3">
          <Field label="Survey number"><Input value={v.survey_number} onChange={set("survey_number")} /></Field>
          <Field label="Khasra number"><Input value={v.khasra_number} onChange={set("khasra_number")} /></Field>
          <Field label="Khata number"><Input value={v.khata_number} onChange={set("khata_number")} /></Field>
        </div>
        <div className="grid grid-3">
          <Field label="Address"><Input value={v.address} onChange={set("address")} /></Field>
          <Field label="PIN code"><Input value={v.pincode} onChange={set("pincode")} /></Field>
          <Field label="Land use"><Input value={v.land_use} onChange={set("land_use")} /></Field>
          <Field label="Latitude" hint="Filled automatically from an approved boundary if left empty"><Input inputMode="decimal" value={v.latitude} onChange={set("latitude")} /></Field>
          <Field label="Longitude"><Input inputMode="decimal" value={v.longitude} onChange={set("longitude")} /></Field>
        </div>
        <div className="grid grid-4">
          <Field label="Area (as recorded)"><Input inputMode="decimal" value={v.area_value} onChange={set("area_value")} /></Field>
          <Field label="Area unit" hint="Regional units are stored as entered and never converted">
            <Select value={v.area_unit} onChange={set("area_unit")} options={AREA_UNITS.map((u) => ({ value: u.key, label: u.label }))} />
          </Field>
          <Field label="Road frontage"><Input inputMode="decimal" value={v.road_frontage_value} onChange={set("road_frontage_value")} /></Field>
          <Field label="Frontage unit"><Select value={v.road_frontage_unit} onChange={set("road_frontage_unit")} options={LENGTH_UNITS.map((u) => ({ value: u.key, label: u.label }))} /></Field>
          <Field label="Road access"><Select value={v.road_access} onChange={set("road_access")} options={ROAD_ACCESS} /></Field>
          <Field label="Title status"><Select value={v.title_status} onChange={set("title_status")} options={TITLE_STATUSES} /></Field>
        </div>
        <Field label="Notes"><TextArea value={v.notes} onChange={set("notes")} /></Field>
        {error && <div className="error-text">{error}</div>}
        <div className="row"><Button variant="primary" disabled={save.isPending}>Save</Button></div>
      </form>
    </Modal>
  );
}
