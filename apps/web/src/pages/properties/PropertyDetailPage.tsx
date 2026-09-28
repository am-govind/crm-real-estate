import { formatDerived, formatMoney, OWNERSHIP_TYPES, P, PRIORITIES, type Property, type PropertyOwner } from "@landcrm/domain";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { DocumentsPanel } from "../../components/DocumentsPanel";
import { TasksPanel, userName, useUsers } from "../../components/TasksPanel";
import { VisitsPanel } from "../../components/VisitsPanel";
import {
  askReason,
  Badge,
  Button,
  Card,
  DateText,
  Field,
  Input,
  KV,
  Modal,
  PageHeader,
  Select,
  StatusBadge,
  Table,
  Tabs,
  useAction,
} from "../../components/ui";
import { api } from "../../lib/api";
import { Can, useCan, useMe } from "../../lib/auth";
import { OwnerForm } from "../OwnersPage";
import { VisitDetailModal } from "../SiteVisitsPage";
import { GeometryPanel } from "./GeometryPanel";
import { PropertyForm } from "./PropertyForm";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "owners", label: "Owners" },
  { key: "deals", label: "Deals" },
  { key: "documents", label: "Documents" },
  { key: "boundary", label: "Boundary & site maps" },
  { key: "nearby", label: "Nearby" },
  { key: "visits", label: "Site visits" },
  { key: "tasks", label: "Tasks" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export function PropertyDetailPage() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as TabKey) ?? "overview";
  const [editing, setEditing] = useState(false);
  const [visitId, setVisitId] = useState<string | null>(null);
  const property = useQuery({ queryKey: ["properties", "detail", id], queryFn: () => api.properties.get(id) });
  const p = property.data;
  if (!p) return <div className="muted">Loading…</div>;

  return (
    <div className="stack">
      <PageHeader
        title={<span>{p.name} <span className="muted small">{p.code}</span></span>}
        subtitle={<span><StatusBadge status={p.status} /> {p.land_type} · Title: <StatusBadge status={p.title_status} /></span>}
        actions={<Can p={P.PROPERTY_WRITE}><Button onClick={() => setEditing(true)}>Edit</Button></Can>}
      />
      <Tabs tabs={TABS} value={tab} onChange={(t) => setParams({ tab: t })} />
      {tab === "overview" && <Overview p={p} />}
      {tab === "owners" && <OwnersTab property={p} />}
      {tab === "deals" && <DealsTab property={p} />}
      {tab === "documents" && <DocumentsPanel scope={{ property_id: p.id }} landType={p.land_type} />}
      {tab === "boundary" && <GeometryPanel property={p} />}
      {tab === "nearby" && <NearbyTab property={p} />}
      {tab === "visits" && <VisitsPanel link={{ property_id: p.id }} onOpen={setVisitId} />}
      {tab === "tasks" && <TasksPanel link={{ property_id: p.id }} />}
      {editing && <PropertyForm property={p} onClose={() => setEditing(false)} />}
      {visitId && <VisitDetailModal id={visitId} onClose={() => setVisitId(null)} />}
    </div>
  );
}

function Overview({ p }: { p: Property }) {
  const me = useMe();
  const allowed = useCan();
  const users = useUsers();
  const summary = useQuery({ queryKey: ["ownership-summary", p.id], queryFn: () => api.properties.ownershipSummary(p.id) });
  const assignments = useQuery({ queryKey: ["property-assignments", p.id], queryFn: () => api.properties.assignments(p.id) });
  const geo = useQueries({
    queries: (
      [
        ["state", undefined],
        ["district", p.state_id],
        ["tehsil", p.district_id],
        ["village", p.tehsil_id],
      ] as const
    ).map(([level, parent]) => ({
      queryKey: ["geo-units", level, parent ?? undefined],
      queryFn: () => api.geo.list({ level, parent_id: parent ?? undefined }),
      enabled: level === "state" || !!parent,
    })),
  });
  const [assignee, setAssignee] = useState("");
  const inv = [["property-assignments", p.id]];
  const assign = useAction(() => api.properties.assign(p.id, assignee), { invalidate: inv, onSuccess: () => setAssignee("") });
  const unassign = useAction((uid: string) => api.properties.unassign(p.id, uid), { invalidate: inv });
  const name = (gid: string | null) => (gid ? geo.flatMap((g) => g.data ?? []).find((g) => g.id === gid)?.name ?? "…" : "—");

  return (
    <div className="grid grid-2">
      <Card title="Land record">
        <KV
          items={[
            [me.terminology.state, name(p.state_id)],
            [me.terminology.district, name(p.district_id)],
            [me.terminology.tehsil, name(p.tehsil_id)],
            [me.terminology.village, name(p.village_id)],
            ["Survey no.", p.survey_number],
            ["Khasra no.", p.khasra_number],
            ["Khata no.", p.khata_number],
            ["Address", p.address],
            ["PIN code", p.pincode],
            ["Area (recorded)", p.area_value ? `${p.area_value} ${p.area_unit}` : null],
            ["Area (derived)", p.area_sqm_derived && p.area_unit !== "sqm" ? formatDerived(p.area_sqm_derived) : null],
            ["Road access", p.road_access],
            ["Road frontage", p.road_frontage_value ? `${p.road_frontage_value} ${p.road_frontage_unit}` : null],
            ["Land use", p.land_use],
            ["Coordinates", p.latitude ? `${p.latitude}, ${p.longitude}` : null],
            ["Notes", p.notes],
          ]}
        />
      </Card>
      <div className="stack">
        <Card title="Ownership">
          {summary.data && (
            <div className="stack">
              <div>
                {summary.data.current_owner_count} current owner(s), {summary.data.verified_owner_count} verified, shares total {summary.data.total_share_percent}%.{" "}
                {summary.data.is_complete ? <Badge tone="success">complete</Badge> : <Badge tone="warning">incomplete</Badge>}
              </div>
              {summary.data.warnings.map((w) => <div key={w} className="warn">{w}</div>)}
            </div>
          )}
        </Card>
        <Card title="Assigned team">
          <Table
            rows={assignments.data}
            empty="Nobody assigned."
            columns={[
              { key: "u", header: "User", render: (a) => userName(users.data, a.user_id) },
              { key: "r", header: "Role", render: (a) => a.role },
              { key: "x", header: "", render: (a) => <Can p={P.PROPERTY_ASSIGN}><Button size="sm" variant="danger" onClick={() => unassign.mutate(a.user_id)}>Remove</Button></Can> },
            ]}
          />
          {allowed(P.PROPERTY_ASSIGN) && (
            <div className="row" style={{ marginTop: 8 }}>
              <Select value={assignee} onChange={(e) => setAssignee(e.target.value)} placeholder="Add team member…" style={{ width: 240 }}
                options={(users.data ?? []).filter((u) => !assignments.data?.some((a) => a.user_id === u.id)).map((u) => ({ value: u.id, label: u.display_name ?? u.email ?? u.id }))} />
              <Button disabled={!assignee} onClick={() => assign.mutate(undefined)}>Assign</Button>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function OwnersTab({ property }: { property: Property }) {
  const allowed = useCan();
  const [history, setHistory] = useState(false);
  const [adding, setAdding] = useState<{ supersedes?: PropertyOwner } | null>(null);
  const owners = useQuery({ queryKey: ["property-owners", property.id, history], queryFn: () => api.properties.owners(property.id, history) });
  const summary = useQuery({ queryKey: ["ownership-summary", property.id], queryFn: () => api.properties.ownershipSummary(property.id) });
  const inv = [["property-owners", property.id], ["ownership-summary", property.id], ["control-center"]];
  const end = useAction((po: PropertyOwner) => {
    const reason = askReason(`Why is ${po.owner.full_name}'s ownership ending?`);
    return reason ? api.properties.endOwner(property.id, po.id, reason) : Promise.resolve(null);
  }, { invalidate: inv });
  const verify = useAction(({ po, status }: { po: PropertyOwner; status: string }) => api.properties.verifyOwner(property.id, po.id, status, window.prompt("Note (optional)") ?? undefined), { invalidate: inv });

  return (
    <div className="stack">
      {summary.data?.warnings.map((w) => <div key={w} className="warn">{w}</div>)}
      <Card
        title={`Owners — shares total ${summary.data?.total_share_percent ?? "…"}%`}
        actions={
          <>
            <label className="row small"><input type="checkbox" checked={history} onChange={(e) => setHistory(e.target.checked)} /> Include history</label>
            <Can p={P.PROPERTY_WRITE}><Button variant="primary" onClick={() => setAdding({})}>Add owner</Button></Can>
          </>
        }
      >
        <Table
          rows={owners.data}
          empty="No owners recorded."
          columns={[
            { key: "n", header: "Owner", render: (po) => <div>{po.owner.full_name} <span className="muted small">{po.owner.code}</span>{!po.is_current && <div><Badge>ended {po.valid_to ?? ""}</Badge> <span className="muted small">{po.ended_reason}</span></div>}</div> },
            { key: "t", header: "Type", render: (po) => po.ownership_type },
            { key: "s", header: "Share", render: (po) => (po.share_percent ? `${po.share_percent}%` : "—") },
            { key: "r", header: "Record ref.", render: (po) => po.record_reference ?? "—" },
            { key: "id", header: "Identity", render: (po) => <StatusBadge status={po.owner.verification_status} /> },
            { key: "v", header: "Ownership verified", render: (po) => <StatusBadge status={po.verification_status} /> },
            { key: "rd", header: "Readiness", render: (po) => <StatusBadge status={po.owner.readiness} /> },
            {
              key: "x",
              header: "",
              render: (po) =>
                po.is_current && (
                  <div className="row">
                    {allowed(P.OWNER_VERIFY) && po.verification_status !== "verified" && <Button size="sm" onClick={() => verify.mutate({ po, status: "verified" })}>Verify</Button>}
                    <Can p={P.PROPERTY_WRITE}>
                      <Button size="sm" onClick={() => setAdding({ supersedes: po })}>Transfer</Button>
                      <Button size="sm" variant="danger" onClick={() => end.mutate(po)}>End</Button>
                    </Can>
                  </div>
                ),
            },
          ]}
        />
      </Card>
      {adding && <AddOwner property={property} supersedes={adding.supersedes} onClose={() => setAdding(null)} />}
    </div>
  );
}

function AddOwner({ property, supersedes, onClose }: { property: Property; supersedes?: PropertyOwner; onClose: () => void }) {
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const [v, setV] = useState({ owner_id: "", ownership_type: supersedes?.ownership_type ?? "sole", share_percent: supersedes?.share_percent ?? "", record_reference: "", valid_from: "" });
  const search = useQuery({ queryKey: ["owners", q], queryFn: () => api.owners.list({ q, limit: 20 }) });
  const save = useAction(
    () =>
      api.properties.addOwner(property.id, {
        owner_id: v.owner_id,
        ownership_type: v.ownership_type,
        share_percent: v.share_percent || undefined,
        record_reference: v.record_reference || undefined,
        valid_from: v.valid_from || undefined,
        supersedes_id: supersedes?.id,
      }),
    { invalidate: [["property-owners", property.id], ["ownership-summary", property.id], ["control-center"]], success: "Owner linked", onSuccess: onClose },
  );
  return (
    <Modal title={supersedes ? `Transfer from ${supersedes.owner.full_name}` : "Add owner"} onClose={onClose}>
      <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate(undefined); }}>
        <Field label="Find owner">
          <Input placeholder="Search by name or code" value={q} onChange={(e) => setQ(e.target.value)} />
        </Field>
        <Select required value={v.owner_id} onChange={(e) => setV({ ...v, owner_id: e.target.value })} placeholder="Choose owner…"
          options={(search.data?.items ?? []).map((o) => ({ value: o.id, label: `${o.full_name} (${o.code})` }))} />
        <Button type="button" variant="ghost" onClick={() => setCreating(true)}>+ Create a new owner</Button>
        <div className="grid grid-2">
          <Field label="Ownership type"><Select value={v.ownership_type} onChange={(e) => setV({ ...v, ownership_type: e.target.value })} options={OWNERSHIP_TYPES} /></Field>
          <Field label="Share %" hint="Current shares may not exceed 100%"><Input inputMode="decimal" value={v.share_percent} onChange={(e) => setV({ ...v, share_percent: e.target.value })} /></Field>
          <Field label="Land-record reference"><Input value={v.record_reference} onChange={(e) => setV({ ...v, record_reference: e.target.value })} /></Field>
          <Field label="Valid from"><Input type="date" value={v.valid_from} onChange={(e) => setV({ ...v, valid_from: e.target.value })} /></Field>
        </div>
        <div className="row"><Button variant="primary" disabled={!v.owner_id || save.isPending}>Save</Button></div>
      </form>
      {creating && <OwnerForm onClose={() => setCreating(false)} onCreated={(o) => { setQ(o.full_name); setV((x) => ({ ...x, owner_id: o.id })); }} />}
    </Modal>
  );
}

function DealsTab({ property }: { property: Property }) {
  const navigate = useNavigate();
  const [starting, setStarting] = useState(false);
  const deals = useQuery({ queryKey: ["deals", "property", property.id], queryFn: () => api.deals.list({ property_id: property.id, limit: 100 }) });
  const hasActive = deals.data?.items.some((d) => d.is_active) ?? false;
  return (
    <Card title="Deals" actions={<Can p={P.DEAL_WRITE}><Button variant="primary" onClick={() => setStarting(true)}>Start deal</Button></Can>}>
      <Table
        rows={deals.data?.items}
        empty="No deals for this property yet."
        onRowClick={(d) => navigate(`/deals/${d.id}`)}
        columns={[
          { key: "c", header: "Code", render: (d) => d.code },
          { key: "t", header: "Title", render: (d) => d.title },
          { key: "s", header: "Stage", render: (d) => d.current_stage_name ?? "—" },
          { key: "st", header: "Status", render: (d) => <span><StatusBadge status={d.status} /> {d.is_active && <Badge tone="info">active</Badge>}</span> },
          { key: "p", header: "Price", render: (d) => formatMoney(d.negotiated_price ?? d.expected_price ?? d.asking_price, d.currency) },
          { key: "d", header: "Started", render: (d) => <DateText value={d.started_at} /> },
        ]}
      />
      {starting && <StartDeal property={property} hasActive={hasActive} onClose={() => setStarting(false)} />}
    </Card>
  );
}

export function StartDeal({ property, hasActive, onClose }: { property: Property; hasActive: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const allowed = useCan();
  const activations = useQuery({ queryKey: ["workflow-activations"], queryFn: api.workflows.activations });
  const templates = useQuery({ queryKey: ["workflow-templates"], queryFn: api.workflows.templates });
  const templateName = (templateId: string) => templates.data?.find((t) => t.id === templateId)?.name ?? "Workflow";
  const [v, setV] = useState({ title: "", activation_id: "", priority: "medium", source: "", asking_price: "", expected_price: "", override_reason: "" });
  const eligible = (activations.data ?? []).filter((a) => a.is_active && (a.land_types.length === 0 || a.land_types.includes(property.land_type)));
  const save = useAction(
    () =>
      api.deals.create({
        property_id: property.id,
        title: v.title || undefined,
        activation_id: v.activation_id || undefined,
        priority: v.priority,
        source: v.source || undefined,
        asking_price: v.asking_price || undefined,
        expected_price: v.expected_price || undefined,
        override_active_deal: hasActive,
        override_reason: hasActive ? v.override_reason : undefined,
      }),
    { invalidate: [["deals"], ["properties"]], success: "Deal started", onSuccess: (d) => navigate(`/deals/${d.id}`) },
  );
  if (hasActive && !allowed(P.DEAL_ACTIVE_OVERRIDE)) {
    return (
      <Modal title="Start deal" onClose={onClose}>
        <p>This property already has an active deal. Only an administrator can open a second active deal.</p>
      </Modal>
    );
  }
  return (
    <Modal title="Start deal" onClose={onClose}>
      <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate(undefined); }}>
        {hasActive && <div className="warn">This property already has an active deal. Starting another requires an override reason, which is audited.</div>}
        <Field label="Title" hint="Defaults to the property name"><Input value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} /></Field>
        <Field label="Workflow" hint="Defaults to the workflow configured for this land type">
          <Select value={v.activation_id} onChange={(e) => setV({ ...v, activation_id: e.target.value })} placeholder="Default"
            options={eligible.map((a) => ({ value: a.id, label: `${templateName(a.template_version.template_id)} v${a.template_version.version}${a.is_default ? " (default)" : ""}` }))} />
        </Field>
        <div className="grid grid-2">
          <Field label="Priority"><Select value={v.priority} onChange={(e) => setV({ ...v, priority: e.target.value })} options={PRIORITIES} /></Field>
          <Field label="Source"><Input value={v.source} onChange={(e) => setV({ ...v, source: e.target.value })} placeholder="Broker, referral, direct…" /></Field>
          <Field label="Asking price (₹)"><Input inputMode="decimal" value={v.asking_price} onChange={(e) => setV({ ...v, asking_price: e.target.value })} /></Field>
          <Field label="Expected price (₹)"><Input inputMode="decimal" value={v.expected_price} onChange={(e) => setV({ ...v, expected_price: e.target.value })} /></Field>
        </div>
        {hasActive && <Field label="Override reason"><Input required minLength={3} value={v.override_reason} onChange={(e) => setV({ ...v, override_reason: e.target.value })} /></Field>}
        <div className="row"><Button variant="primary" disabled={save.isPending}>Start</Button></div>
      </form>
    </Modal>
  );
}

function NearbyTab({ property }: { property: Property }) {
  const nearby = useQuery({ queryKey: ["nearby", property.id], queryFn: () => api.maps.nearby(property.id) });
  const refresh = useAction(() => api.maps.refreshNearby(property.id), { success: "Refresh queued; results appear shortly", onSuccess: () => setTimeout(() => nearby.refetch(), 4000) });
  return (
    <Card
      title="Nearby features (derived from OpenStreetMap)"
      actions={<Can p={P.PROPERTY_WRITE}><Button onClick={() => refresh.mutate(undefined)} disabled={!property.latitude}>Refresh</Button></Can>}
    >
      {!property.latitude && <div className="warn">Add coordinates or an approved boundary to look up nearby features.</div>}
      <Table
        rows={nearby.data}
        empty="No nearby features fetched yet."
        columns={[
          { key: "k", header: "Kind", render: (n) => n.kind },
          { key: "n", header: "Name", render: (n) => n.name ?? n.ref ?? "Unnamed" },
          { key: "d", header: "Distance", render: (n) => (n.distance_m >= 1000 ? `${(n.distance_m / 1000).toFixed(1)} km` : `${Math.round(n.distance_m)} m`) },
          { key: "c", header: "Confidence", render: (n) => n.confidence },
          { key: "s", header: "Source", render: (n) => <span className="small">{n.source} · <DateText value={n.fetched_at} /></span> },
        ]}
      />
    </Card>
  );
}