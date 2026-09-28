import type { ControlCenter } from "@landcrm/api-client";
import { formatDerived, formatMoney, humanize, P, PRIORITIES, type Deal } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { DocumentsPanel } from "../../components/DocumentsPanel";
import { TasksPanel, useUsers } from "../../components/TasksPanel";
import { VisitsPanel } from "../../components/VisitsPanel";
import {
  askReason,
  Badge,
  Button,
  Card,
  clean,
  DateText,
  Field,
  Input,
  KV,
  Modal,
  PageHeader,
  Select,
  StatusBadge,
  Tabs,
  TextArea,
  useAction,
  useForm,
} from "../../components/ui";
import { api } from "../../lib/api";
import { Can, useCan } from "../../lib/auth";
import { VisitDetailModal } from "../SiteVisitsPage";
import { ActivityTab, DueDiligenceTab, NegotiationTab, ScoreCard, SnapshotsTab, TeamTab } from "./DealTabs";
import { FinanceTab } from "./FinanceTab";
import { StagesTab } from "./StagesTab";

const TABS = [
  { key: "stages", label: "Stages & checklist" },
  { key: "dd", label: "Due diligence" },
  { key: "negotiation", label: "Negotiation & agreements" },
  { key: "finance", label: "Finance" },
  { key: "documents", label: "Documents" },
  { key: "tasks", label: "Tasks" },
  { key: "visits", label: "Site visits" },
  { key: "ownership", label: "Ownership snapshots" },
  { key: "team", label: "Team" },
  { key: "activity", label: "Activity" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export function DealControlCenterPage() {
  const { id = "" } = useParams();
  const allowed = useCan();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as TabKey) ?? "stages";
  const [editing, setEditing] = useState(false);
  const [visitId, setVisitId] = useState<string | null>(null);
  const cc = useQuery({ queryKey: ["control-center", id], queryFn: () => api.reports.controlCenter(id) });
  const deal = useQuery({ queryKey: ["deals", "detail", id], queryFn: () => api.deals.get(id) });
  const inv = [["control-center", id], ["deals"], ["pipeline"], ["deal-stages", id]];
  const close = useAction(({ outcome }: { outcome: string }) => {
    const reason = askReason(`Reason for marking this deal ${humanize(outcome).toLowerCase()}:`);
    return reason ? api.deals.close(id, outcome, reason) : Promise.resolve(null);
  }, { invalidate: inv });
  const reopen = useAction(() => {
    const reason = askReason("Reason for reopening:");
    return reason ? api.deals.reopen(id, reason) : Promise.resolve(null);
  }, { invalidate: inv });

  const c = cc.data;
  const d = deal.data;
  if (!c || !d) return <div className="muted">Loading…</div>;
  const closed = ["won", "lost", "cancelled"].includes(d.status);

  return (
    <div className="stack">
      <PageHeader
        title={<span>{d.title} <span className="muted small">{d.code}</span></span>}
        subtitle={
          <span className="row">
            <Link to={`/properties/${c.property.id}`}>{c.property.code} · {c.property.name}</Link>
            <StatusBadge status={d.status} />
            <StatusBadge status={d.priority} />
            {d.active_override_reason && <Badge tone="warning" >active-deal override: {d.active_override_reason}</Badge>}
          </span>
        }
        actions={
          <Can p={P.DEAL_WRITE}>
            <Button onClick={() => setEditing(true)}>Edit</Button>
            {!closed && d.status !== "on_hold" && <Button onClick={() => close.mutate({ outcome: "on_hold" })}>Put on hold</Button>}
            {!closed && <Button variant="danger" onClick={() => close.mutate({ outcome: "lost" })}>Mark lost</Button>}
            {!closed && <Button variant="danger" onClick={() => close.mutate({ outcome: "cancelled" })}>Cancel</Button>}
            {(closed || d.status === "on_hold") && <Button onClick={() => reopen.mutate(undefined)}>Reopen</Button>}
          </Can>
        }
      />
      <Stepper c={c} />
      <Summary c={c} deal={d} />
      <Tabs tabs={TABS.filter((t) => t.key !== "finance" || allowed(P.PAYMENT_READ))} value={tab} onChange={(t) => setParams({ tab: t })} />
      {tab === "stages" && <StagesTab deal={d} />}
      {tab === "dd" && <DueDiligenceTab dealId={id} />}
      {tab === "negotiation" && <NegotiationTab deal={d} />}
      {tab === "finance" && <FinanceTab deal={d} />}
      {tab === "documents" && <DocumentsPanel scope={{ deal_id: id }} landType={c.property.land_type} />}
      {tab === "tasks" && <TasksPanel link={{ deal_id: id }} />}
      {tab === "visits" && <VisitsPanel link={{ deal_id: id, property_id: c.property.id }} onOpen={setVisitId} />}
      {tab === "ownership" && <SnapshotsTab dealId={id} />}
      {tab === "team" && <TeamTab dealId={id} />}
      {tab === "activity" && <ActivityTab dealId={id} />}
      {editing && <EditDeal deal={d} onClose={() => setEditing(false)} />}
      {visitId && <VisitDetailModal id={visitId} onClose={() => setVisitId(null)} />}
    </div>
  );
}

function Stepper({ c }: { c: ControlCenter }) {
  const s = c.stage;
  return (
    <Card>
      <div className="stack">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <span>
            Current stage: <strong>{s.current?.name ?? "—"}</strong>{" "}
            {s.days_in_stage !== null && (
              <span className={s.is_overdue ? "error-text" : "muted"}>
                · {s.days_in_stage} day(s){s.sla_days !== null && ` of ${s.sla_days}-day SLA`}{s.is_overdue && " — overdue"}
              </span>
            )}
          </span>
          <span className="muted small">
            {s.progress.completed_stages}/{s.progress.total_stages} stages complete{s.progress.bypassed_stages ? `, ${s.progress.bypassed_stages} bypassed` : ""} · {s.progress.percent}%
          </span>
        </div>
        <div className="stepper">
          {s.stages.map((st) => (
            <div key={st.key} className={`step step-${st.status}`} title={`${st.name}: ${st.status}`}>{st.name}</div>
          ))}
        </div>
      </div>
    </Card>
  );
}

function Summary({ c, deal }: { c: ControlCenter; deal: Deal }) {
  const allowed = useCan();
  const f = c.financials;
  return (
    <div className="grid grid-3">
      <Card title="Property">
        <KV
          items={[
            ["Location", [c.property.location.village, c.property.location.tehsil, c.property.location.district, c.property.location.state].filter(Boolean).join(", ") || null],
            ["Survey / Khasra", [c.property.survey_number, c.property.khasra_number].filter(Boolean).join(" / ") || null],
            ["Area (recorded)", c.property.area.value ? `${c.property.area.value} ${c.property.area.unit}` : null],
            ["Boundary area", c.property.geometry ? formatDerived(c.property.geometry.area_sqm) : "No approved boundary"],
            ["Road access", humanize(c.property.road_access)],
            ["Title", <StatusBadge status={c.property.title_status} />],
          ]}
        />
      </Card>
      <Card title="Owners">
        <div className="stack small">
          {c.owners.items.map((o) => (
            <div key={o.owner_id} className="row" style={{ justifyContent: "space-between" }}>
              <span>{o.name} {o.share_percent && <span className="muted">({o.share_percent}%)</span>}</span>
              <span className="row"><StatusBadge status={o.identity_verification} /><StatusBadge status={o.readiness} /></span>
            </div>
          ))}
          {c.owners.items.length === 0 && <span className="muted">No owners recorded.</span>}
          {c.owners.summary.warnings.map((w) => <div key={w} className="warn">{w}</div>)}
        </div>
      </Card>
      <Card title="Next action">
        <div className="stack">
          <div>{c.next_action.action ?? <span className="muted">No next action set.</span>}</div>
          {c.next_action.due_date && <div className={c.next_action.is_overdue ? "error-text" : "muted"}>Due <DateText value={c.next_action.due_date} />{c.next_action.is_overdue && " (overdue)"}</div>}
          {c.next_action.assignee && <div className="muted small">Owner: {c.next_action.assignee.name}</div>}
          <div className="muted small">{c.open_tasks.length} open task(s) · {c.upcoming_visits.length} upcoming visit(s)</div>
        </div>
      </Card>
      <Card title="Documents">
        {c.documents ? (
          <div className="stack">
            <strong>{c.documents.label}</strong>
            <div className="progress"><div style={{ width: `${c.documents.percent}%` }} /></div>
            {c.documents.missing.length > 0 && <div className="small muted">Missing: {c.documents.missing.map((m) => m.class_name).join(", ")}</div>}
          </div>
        ) : <span className="muted">No access.</span>}
      </Card>
      <Card title="Due diligence">
        <div className="stack small">
          {Object.values(c.due_diligence).map((dd) => (
            <div key={dd.category} className="row" style={{ justifyContent: "space-between" }}>
              <span>{humanize(dd.category)}</span>
              <span className="row"><StatusBadge status={dd.status} /> <span className="muted">{dd.clear}/{dd.total} clear{dd.issues ? `, ${dd.issues} issue(s)` : ""}</span></span>
            </div>
          ))}
        </div>
      </Card>
      {allowed(P.PAYMENT_READ) && f && (
        <Card title="Finance">
          <KV
            items={[
              ["Asking", formatMoney(f.asking_price, f.currency)],
              ["Negotiated", formatMoney(f.negotiated_price ?? deal.negotiated_price, f.currency)],
              ["Advance paid", `${formatMoney(f.advance_paid, f.currency)} of ${formatMoney(f.advance_planned, f.currency)}`],
              ["Paid (approved)", formatMoney(f.paid_total, f.currency)],
              ["Balance", f.balance_amount ? `${formatMoney(f.balance_amount, f.currency)} (vs ${humanize(f.balance_basis)})` : "—"],
              ["Next due", f.next_due ? <span>{formatMoney(f.next_due.planned_amount, f.currency)} on <DateText value={f.next_due.due_date} /></span> : "—"],
            ]}
          />
          {f.overdue_milestones > 0 && <div className="error-text">{f.overdue_milestones} overdue milestone(s)</div>}
        </Card>
      )}
      <ScoreCard dealId={deal.id} score={c.score} />
    </div>
  );
}

function EditDeal({ deal, onClose }: { deal: Deal; onClose: () => void }) {
  const users = useUsers();
  const [v, set] = useForm({
    title: deal.title,
    priority: deal.priority,
    source: deal.source ?? "",
    asking_price: deal.asking_price ?? "",
    expected_price: deal.expected_price ?? "",
    next_action: deal.next_action ?? "",
    next_action_due: deal.next_action_due ?? "",
    next_action_assignee_id: deal.next_action_assignee_id ?? "",
    notes: deal.notes ?? "",
  });
  const save = useAction(() => api.deals.update(deal.id, clean(v)), { invalidate: [["deals"], ["control-center"], ["pipeline"]], success: "Deal updated", onSuccess: onClose });
  return (
    <Modal title="Edit deal" onClose={onClose}>
      <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate(undefined); }}>
        <Field label="Title"><Input required value={v.title} onChange={set("title")} /></Field>
        <div className="grid grid-2">
          <Field label="Priority"><Select value={v.priority} onChange={set("priority")} options={PRIORITIES} /></Field>
          <Field label="Source"><Input value={v.source} onChange={set("source")} /></Field>
          <Field label="Asking price (₹)"><Input inputMode="decimal" value={v.asking_price} onChange={set("asking_price")} /></Field>
          <Field label="Expected price (₹)"><Input inputMode="decimal" value={v.expected_price} onChange={set("expected_price")} /></Field>
        </div>
        <div className="muted small">The negotiated price is set by recording an accepted offer under Negotiation.</div>
        <Field label="Next action"><Input value={v.next_action} onChange={set("next_action")} /></Field>
        <div className="grid grid-2">
          <Field label="Next action due"><Input type="date" value={v.next_action_due} onChange={set("next_action_due")} /></Field>
          <Field label="Next action owner">
            <Select value={v.next_action_assignee_id} onChange={set("next_action_assignee_id")} placeholder="—" options={(users.data ?? []).map((u) => ({ value: u.id, label: u.display_name ?? u.email ?? u.id }))} />
          </Field>
        </div>
        <Field label="Notes"><TextArea value={v.notes} onChange={set("notes")} /></Field>
        <div className="row"><Button variant="primary" disabled={save.isPending}>Save</Button></div>
      </form>
    </Modal>
  );
}
