import { formatDerived, INVENTORY_PROPERTY_TYPES, INVENTORY_STATUSES, P, type MatchCandidate, type SiteData } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { userName, useUsers } from "../../components/TasksPanel";
import { Badge, Button, Card, DateText, Field, Input, PageHeader, Select, StatusBadge, Table, Tabs, useAction } from "../../components/ui";
import { api } from "../../lib/api";
import { Can, useCan } from "../../lib/auth";
import { emptySiteData, normalizeSiteData, SiteDataForm } from "./SiteDataForm";

export function InventoryPage() {
  const allowed = useCan();
  const [tab, setTab] = useState<"search" | "new" | "queue">("search");
  const tabs = [
    { key: "search" as const, label: "Search" },
    ...(allowed(P.INVENTORY_WRITE) ? [{ key: "new" as const, label: "New site" }] : []),
    ...(allowed(P.INVENTORY_APPROVE) ? [{ key: "queue" as const, label: "Approval queue" }] : []),
  ];
  return (
    <div className="stack">
      <PageHeader title="Inventory" subtitle="Approved site records. New sites and changes become searchable once an administrator approves them." />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      {tab === "search" && <Search />}
      {tab === "new" && <NewSite />}
      {tab === "queue" && <Queue />}
    </div>
  );
}

function Search() {
  const navigate = useNavigate();
  const allowed = useCan();
  const [f, setF] = useState({ q: "", property_type: "", status: "", min_area_sqm: "", max_area_sqm: "", min_length_m: "", min_width_m: "", min_rooms: "", floor: "", include_unapproved: false });
  const query = {
    q: f.q,
    property_type: f.property_type ? [f.property_type] : undefined,
    status: f.status ? [f.status] : undefined,
    min_area_sqm: f.min_area_sqm,
    max_area_sqm: f.max_area_sqm,
    min_length_m: f.min_length_m,
    min_width_m: f.min_width_m,
    min_rooms: f.min_rooms,
    floor: f.floor,
    include_unapproved: f.include_unapproved || undefined,
    approval_state: f.include_unapproved ? ["approved", "pending", "rejected"] : undefined,
    limit: 200,
  };
  const sites = useQuery({ queryKey: ["inventory", "search", query], queryFn: () => api.inventory.search(query) });
  const upd = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  return (
    <Card>
      <div className="row" style={{ marginBottom: 12 }}>
        <Input placeholder="Site ID, plot, unit, project, location…" value={f.q} onChange={upd("q")} style={{ width: 280 }} />
        <Select value={f.property_type} onChange={upd("property_type")} options={INVENTORY_PROPERTY_TYPES} placeholder="Any type" style={{ width: 160 }} />
        <Select value={f.status} onChange={upd("status")} options={INVENTORY_STATUSES} placeholder="Any status" style={{ width: 160 }} />
        <Input placeholder="Min m²" value={f.min_area_sqm} onChange={upd("min_area_sqm")} style={{ width: 90 }} />
        <Input placeholder="Max m²" value={f.max_area_sqm} onChange={upd("max_area_sqm")} style={{ width: 90 }} />
        <Input placeholder="Min length m" value={f.min_length_m} onChange={upd("min_length_m")} style={{ width: 110 }} />
        <Input placeholder="Min width m" value={f.min_width_m} onChange={upd("min_width_m")} style={{ width: 110 }} />
        <Input placeholder="Min rooms" value={f.min_rooms} onChange={upd("min_rooms")} style={{ width: 90 }} />
        <Input placeholder="Floor" value={f.floor} onChange={upd("floor")} style={{ width: 80 }} />
        {allowed(P.INVENTORY_APPROVE) && (
          <label className="row small"><input type="checkbox" checked={f.include_unapproved} onChange={(e) => setF({ ...f, include_unapproved: e.target.checked })} /> Include unapproved</label>
        )}
      </div>
      <div className="muted small" style={{ marginBottom: 8 }}>Size filters use derived metric values; regional units are never converted and do not match these filters.</div>
      <Table
        rows={sites.data?.items}
        empty="No matching sites."
        onRowClick={(s) => navigate(`/inventory/${s.id}`)}
        columns={[
          { key: "c", header: "Site ID", render: (s) => <strong className="mono">{s.site_code}</strong> },
          { key: "t", header: "Type", render: (s) => s.property_type },
          { key: "l", header: "Label", render: (s) => s.plot_label ?? s.unit_number ?? "—" },
          { key: "p", header: "Project / location", render: (s) => s.project_name ?? s.location_text ?? "—" },
          { key: "a", header: "Area", render: (s) => (s.area_value ? <div>{s.area_value} {s.area_unit}{s.area_sqm_derived && s.area_unit !== "sqm" && <div className="muted small">{formatDerived(s.area_sqm_derived)}</div>}</div> : "—") },
          { key: "r", header: "Rooms", render: (s) => s.rooms ?? "—" },
          { key: "s", header: "Status", render: (s) => <StatusBadge status={s.status} /> },
          { key: "ap", header: "Approval", render: (s) => <span><StatusBadge status={s.approval_state} /> {s.pending_revision_id && s.approval_state === "approved" && <Badge tone="warning">change pending</Badge>}</span> },
        ]}
      />
    </Card>
  );
}

function NewSite() {
  const navigate = useNavigate();
  const nextId = useQuery({ queryKey: ["inventory", "next-id"], queryFn: api.inventory.nextSiteId, refetchOnWindowFocus: false });
  const [data, setData] = useState<SiteData>(emptySiteData());
  const [matches, setMatches] = useState<MatchCandidate[] | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [note, setNote] = useState("");
  const check = useAction(() => api.inventory.matches(normalizeSiteData(data)), { onSuccess: (m) => { setMatches(m); setConfirmed(false); } });
  const create = useAction(
    () =>
      api.inventory.create({
        confirmed_site_code: nextId.data!.site_code,
        confirmed_new: true,
        considered_candidates: (matches ?? []).map((m) => m.site_id),
        data: normalizeSiteData(data),
        change_note: note || undefined,
      }),
    {
      invalidate: [["inventory"]],
      success: "Site submitted for approval",
      onSuccess: (s) => navigate(`/inventory/${s.id}`),
    },
  );

  return (
    <div className="stack">
      <Card title="Site ID">
        <div className="row">
          <Input readOnly value={nextId.data?.site_code ?? "…"} className="mono" style={{ width: 180, fontWeight: 700 }} />
          <Button size="sm" onClick={() => nextId.refetch()}>Refresh</Button>
          <span className="muted small">Assigned automatically and cannot be edited. If someone else takes it first, you'll be asked to confirm the next one.</span>
        </div>
      </Card>
      <SiteDataForm value={data} onChange={(d) => { setData(d); setMatches(null); }} />
      <Card title="Duplicate check">
        <div className="stack">
          <div className="row"><Button onClick={() => check.mutate(undefined)} disabled={check.isPending}>Check for possible matches</Button></div>
          {matches && matches.length === 0 && <div className="muted">No similar sites found.</div>}
          {matches && matches.length > 0 && (
            <>
              <div className="warn">These existing sites look similar. If this is one of them, open it and propose a change instead of creating a duplicate. Records are never merged automatically.</div>
              <Table
                rows={matches}
                columns={[
                  { key: "c", header: "Site", render: (m) => <Link to={`/inventory/${m.site_id}`} target="_blank">{m.site_code}</Link> },
                  { key: "s", header: "Similarity", render: (m) => `${Math.round(m.score * 100)}%` },
                  { key: "r", header: "Why", render: (m) => m.reasons.join("; ") },
                  { key: "a", header: "Approval", render: (m) => <StatusBadge status={m.approval_state} /> },
                ]}
              />
            </>
          )}
          {matches && (
            <label className="row"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} /> I confirm this is a new site{matches.length ? ", not one of the matches above" : ""}.</label>
          )}
          <Field label="Note for approver"><Input value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          <div className="row">
            <Button variant="primary" disabled={!matches || !confirmed || !nextId.data || create.isPending} onClick={() => create.mutate(undefined, { onError: () => nextId.refetch() })}>
              Create {nextId.data?.site_code}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}

function Queue() {
  const users = useUsers();
  const queue = useQuery({ queryKey: ["inventory", "queue"], queryFn: () => api.inventory.queue("pending") });
  return (
    <Card title="Pending revisions">
      <Table
        rows={queue.data}
        empty="Nothing awaiting approval."
        columns={[
          { key: "s", header: "Site", render: (r) => <Link to={`/inventory/${r.site_record_id}`}>Open</Link> },
          { key: "t", header: "Change", render: (r) => <span><StatusBadge status={r.change_type} /> rev {r.revision_no}</span> },
          { key: "p", header: "Type", render: (r) => r.data.property_type },
          { key: "n", header: "Note", render: (r) => r.change_note ?? "" },
          { key: "b", header: "Submitted by", render: (r) => <span>{userName(users.data, r.submitted_by_id)} · <DateText value={r.submitted_at} /></span> },
        ]}
      />
      <Can p={P.INVENTORY_APPROVE}><div className="muted small" style={{ marginTop: 8 }}>You cannot approve changes you submitted yourself.</div></Can>
    </Card>
  );
}
