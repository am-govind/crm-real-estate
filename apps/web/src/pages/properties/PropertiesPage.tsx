import { formatDerived, LAND_TYPES, P, PROPERTY_STATUSES, TITLE_STATUSES } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button, Card, Input, PageHeader, Select, StatusBadge, Table } from "../../components/ui";
import { api } from "../../lib/api";
import { Can } from "../../lib/auth";
import { PropertyForm } from "./PropertyForm";

const PAGE = 50;

export function PropertiesPage() {
  const navigate = useNavigate();
  const [f, setF] = useState({ q: "", status: "", land_type: "", title_status: "", assigned_to_me: false, min_area_sqm: "", max_area_sqm: "" });
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false);
  const query = {
    q: f.q,
    status: f.status ? [f.status] : undefined,
    land_type: f.land_type ? [f.land_type] : undefined,
    title_status: f.title_status,
    assigned_to_me: f.assigned_to_me || undefined,
    min_area_sqm: f.min_area_sqm,
    max_area_sqm: f.max_area_sqm,
    limit: PAGE,
    offset,
  };
  const list = useQuery({ queryKey: ["properties", query], queryFn: () => api.properties.list(query) });
  const upd = (k: keyof typeof f) => (e: { target: { value: string } }) => {
    setOffset(0);
    setF({ ...f, [k]: e.target.value });
  };
  const total = list.data?.total ?? 0;

  return (
    <div className="stack">
      <PageHeader
        title="Properties"
        subtitle={`${total} properties`}
        actions={<Can p={P.PROPERTY_WRITE}><Button variant="primary" onClick={() => setCreating(true)}>New property</Button></Can>}
      />
      <Card>
        <div className="row" style={{ marginBottom: 12 }}>
          <Input placeholder="Search name, code, survey / khasra no., village…" value={f.q} onChange={upd("q")} style={{ width: 320 }} />
          <Select value={f.status} onChange={upd("status")} options={PROPERTY_STATUSES} placeholder="Any status" style={{ width: 150 }} />
          <Select value={f.land_type} onChange={upd("land_type")} options={LAND_TYPES} placeholder="Any land type" style={{ width: 170 }} />
          <Select value={f.title_status} onChange={upd("title_status")} options={TITLE_STATUSES} placeholder="Any title status" style={{ width: 160 }} />
          <Input placeholder="Min m²" value={f.min_area_sqm} onChange={upd("min_area_sqm")} style={{ width: 100 }} />
          <Input placeholder="Max m²" value={f.max_area_sqm} onChange={upd("max_area_sqm")} style={{ width: 100 }} />
          <label className="row small">
            <input type="checkbox" checked={f.assigned_to_me} onChange={(e) => setF({ ...f, assigned_to_me: e.target.checked })} /> Assigned to me
          </label>
        </div>
        <Table
          rows={list.data?.items}
          onRowClick={(p) => navigate(`/properties/${p.id}`)}
          columns={[
            { key: "code", header: "Code", render: (p) => p.code },
            { key: "name", header: "Name", render: (p) => p.name },
            { key: "survey", header: "Survey / Khasra", render: (p) => [p.survey_number, p.khasra_number].filter(Boolean).join(" / ") || "—" },
            { key: "type", header: "Land type", render: (p) => p.land_type },
            {
              key: "area",
              header: "Area",
              render: (p) =>
                p.area_value ? (
                  <div>
                    {p.area_value} {p.area_unit}
                    {p.area_sqm_derived && p.area_unit !== "sqm" && <div className="muted small">{formatDerived(p.area_sqm_derived)}</div>}
                  </div>
                ) : "—",
            },
            { key: "title", header: "Title", render: (p) => <StatusBadge status={p.title_status} /> },
            { key: "status", header: "Status", render: (p) => <StatusBadge status={p.status} /> },
          ]}
        />
        {total > PAGE && (
          <div className="row" style={{ marginTop: 12, justifyContent: "flex-end" }}>
            <Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</Button>
            <span className="small muted">{offset + 1}–{Math.min(offset + PAGE, total)} of {total}</span>
            <Button size="sm" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Next</Button>
          </div>
        )}
      </Card>
      {creating && <PropertyForm onClose={() => setCreating(false)} onSaved={(p) => navigate(`/properties/${p.id}`)} />}
    </div>
  );
}
