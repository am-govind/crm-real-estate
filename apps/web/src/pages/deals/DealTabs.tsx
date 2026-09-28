import type { ControlCenter } from "@landcrm/api-client";
import { DD_CATEGORIES, DD_STATUSES, formatMoney, humanize, P, parseMoneyInput, type Agreement, type Deal, type DueDiligenceItem } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { userName, useUsers } from "../../components/TasksPanel";
import { Badge, Button, Card, DateText, Field, Input, KV, Modal, Select, StatusBadge, Table, TextArea, useAction } from "../../components/ui";
import { api } from "../../lib/api";
import { Can, useCan } from "../../lib/auth";

// ---- Due diligence ----

export function DueDiligenceTab({ dealId }: { dealId: string }) {
  const allowed = useCan();
  const users = useUsers();
  const items = useQuery({ queryKey: ["due-diligence", dealId], queryFn: () => api.deals.dueDiligence(dealId) });
  const [open, setOpen] = useState<DueDiligenceItem | { category: string } | null>(null);
  return (
    <div className="grid grid-2">
      {DD_CATEGORIES.map((cat) => {
        const rows = items.data?.filter((i) => i.category === cat);
        return (
          <Card key={cat} title={`${humanize(cat)} review`} actions={<Can p={P.DEAL_WRITE}><Button size="sm" onClick={() => setOpen({ category: cat })}>Add item</Button></Can>}>
            <Table
              rows={rows}
              empty="No items."
              onRowClick={allowed(P.DEAL_WRITE) || allowed(P.DUE_DILIGENCE_REVIEW) ? (i) => setOpen(i) : undefined}
              columns={[
                { key: "t", header: "Item", render: (i) => <div>{i.title}{i.findings && <div className="muted small">{i.findings}</div>}</div> },
                { key: "s", header: "Status", render: (i) => <div><StatusBadge status={i.status} /> {i.severity && <Badge tone={i.severity === "critical" || i.severity === "high" ? "danger" : "warning"}>{i.severity}</Badge>}</div> },
                { key: "a", header: "Assignee", render: (i) => userName(users.data, i.assignee_id) },
                { key: "d", header: "Due", render: (i) => <DateText value={i.due_date} /> },
              ]}
            />
          </Card>
        );
      })}
      {open && <DDForm dealId={dealId} item={"id" in open ? open : undefined} category={open.category} onClose={() => setOpen(null)} />}
    </div>
  );
}

function DDForm({ dealId, item, category, onClose }: { dealId: string; item?: DueDiligenceItem; category: string; onClose: () => void }) {
  const allowed = useCan();
  const users = useUsers();
  const docs = useQuery({ queryKey: ["documents", { deal_id: dealId }], queryFn: () => api.documents.list({ deal_id: dealId, limit: 500 }) });
  const [v, setV] = useState({
    title: item?.title ?? "",
    status: item?.status ?? "not_started",
    severity: item?.severity ?? "",
    findings: item?.findings ?? "",
    assignee_id: item?.assignee_id ?? "",
    due_date: item?.due_date ?? "",
    document_ids: item?.document_ids ?? [],
  });
  const reviewStatuses = ["clear", "issue_found", "waived"];
  const statusOptions = DD_STATUSES.filter((s) => allowed(P.DUE_DILIGENCE_REVIEW) || !reviewStatuses.includes(s) || s === item?.status);
  const save = useAction(
    () => {
      if (!item) return api.deals.createDD(dealId, { category, title: v.title, assignee_id: v.assignee_id || undefined, due_date: v.due_date || undefined });
      const body: Record<string, unknown> = {
        title: v.title,
        findings: v.findings || null,
        severity: v.severity || null,
        assignee_id: v.assignee_id || null,
        due_date: v.due_date || null,
        document_ids: v.document_ids,
      };
      if (v.status !== item.status) body.status = v.status;
      return api.deals.updateDD(dealId, item.id, body);
    },
    { invalidate: [["due-diligence", dealId], ["control-center", dealId]], success: "Saved", onSuccess: onClose },
  );
  return (
    <Modal title={item ? item.title : `New ${humanize(category).toLowerCase()} item`} onClose={onClose}>
      <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate(undefined); }}>
        <Field label="Title"><Input required value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} /></Field>
        <div className="grid grid-2">
          {item && <Field label="Status" hint="Clear / issue found / waived require reviewer permission"><Select value={v.status} onChange={(e) => setV({ ...v, status: e.target.value })} options={statusOptions} /></Field>}
          {item && <Field label="Severity"><Select value={v.severity} onChange={(e) => setV({ ...v, severity: e.target.value })} placeholder="—" options={["low", "medium", "high", "critical"]} /></Field>}
          <Field label="Assignee"><Select value={v.assignee_id} onChange={(e) => setV({ ...v, assignee_id: e.target.value })} placeholder="Unassigned" options={(users.data ?? []).map((u) => ({ value: u.id, label: u.display_name ?? u.email ?? u.id }))} /></Field>
          <Field label="Due date"><Input type="date" value={v.due_date} onChange={(e) => setV({ ...v, due_date: e.target.value })} /></Field>
        </div>
        {item && (
          <>
            <Field label="Findings"><TextArea rows={4} value={v.findings} onChange={(e) => setV({ ...v, findings: e.target.value })} /></Field>
            <Field label="Evidence documents">
              <select className="input" multiple value={v.document_ids} style={{ height: 100 }} onChange={(e) => setV({ ...v, document_ids: Array.from(e.target.selectedOptions, (o) => o.value) })}>
                {(docs.data?.items ?? []).filter((d) => !d.is_redacted).map((d) => <option key={d.id} value={d.id}>{d.title ?? d.class_name} ({d.class_name})</option>)}
              </select>
            </Field>
            {item.reviewed_at && <div className="muted small">Reviewed by {userName(users.data, item.reviewer_id)} on <DateText value={item.reviewed_at} /></div>}
          </>
        )}
        <div className="row"><Button variant="primary" disabled={save.isPending}>Save</Button></div>
      </form>
    </Modal>
  );
}

// ---- Negotiation & agreements ----

const PARTIES = ["buyer", "seller", "broker", "other"] as const;
const NEG_KINDS = ["offer", "counter_offer", "accepted", "rejected", "note"] as const;
const AGREEMENT_KINDS = ["loi", "mou", "agreement_to_sell", "sale_deed", "power_of_attorney", "other"] as const;
const AGREEMENT_STATUSES = ["draft", "under_review", "signed", "registered", "cancelled"] as const;

export function NegotiationTab({ deal }: { deal: Deal }) {
  const users = useUsers();
  const id = deal.id;
  const entries = useQuery({ queryKey: ["negotiations", id], queryFn: () => api.deals.negotiations(id) });
  const agreements = useQuery({ queryKey: ["agreements", id], queryFn: () => api.deals.agreements(id) });
  const [entry, setEntry] = useState({ party: "seller", kind: "offer", amount: "", terms: "" });
  const [editingAgreement, setEditingAgreement] = useState<Agreement | "new" | null>(null);
  const add = useAction(
    () => {
      const amount = entry.amount ? parseMoneyInput(entry.amount) : undefined;
      if (amount === null) throw new Error("Amount must be a number with at most two decimals");
      return api.deals.addNegotiation(id, { party: entry.party, kind: entry.kind, amount, terms: entry.terms || undefined });
    },
    { invalidate: [["negotiations", id], ["deals"], ["control-center", id], ["financials", id]], success: "Recorded", onSuccess: () => setEntry({ ...entry, amount: "", terms: "" }) },
  );

  return (
    <div className="stack">
      <Card title={`Negotiation log · negotiated price ${formatMoney(deal.negotiated_price, deal.currency)}`}>
        <Table
          rows={entries.data}
          empty="No negotiation recorded yet."
          columns={[
            { key: "w", header: "When", render: (e) => <DateText value={e.occurred_at} time /> },
            { key: "p", header: "Party", render: (e) => humanize(e.party) },
            { key: "k", header: "Kind", render: (e) => <StatusBadge status={e.kind} /> },
            { key: "a", header: "Amount", align: "right", render: (e) => formatMoney(e.amount, deal.currency) },
            { key: "t", header: "Terms", render: (e) => e.terms ?? "" },
            { key: "b", header: "Recorded by", render: (e) => userName(users.data, e.recorded_by_id) },
          ]}
        />
        <Can p={P.DEAL_WRITE}>
          <form className="row" style={{ marginTop: 12 }} onSubmit={(e) => { e.preventDefault(); add.mutate(undefined); }}>
            <Select value={entry.party} onChange={(e) => setEntry({ ...entry, party: e.target.value })} options={PARTIES} style={{ width: 120 }} />
            <Select value={entry.kind} onChange={(e) => setEntry({ ...entry, kind: e.target.value })} options={NEG_KINDS} style={{ width: 150 }} />
            <Input placeholder="Amount (₹)" inputMode="decimal" value={entry.amount} onChange={(e) => setEntry({ ...entry, amount: e.target.value })} style={{ width: 160 }} />
            <Input placeholder="Terms / note" value={entry.terms} onChange={(e) => setEntry({ ...entry, terms: e.target.value })} style={{ width: 320 }} />
            <Button>Record</Button>
          </form>
          <div className="muted small">Recording an “accepted” entry with an amount sets the deal's negotiated price.</div>
        </Can>
      </Card>
      <Card title="Agreements" actions={<Can p={P.DEAL_WRITE}><Button variant="primary" onClick={() => setEditingAgreement("new")}>Add agreement</Button></Can>}>
        <Table
          rows={agreements.data}
          empty="No agreements."
          onRowClick={(a) => setEditingAgreement(a)}
          columns={[
            { key: "k", header: "Kind", render: (a) => humanize(a.kind) },
            { key: "s", header: "Status", render: (a) => <StatusBadge status={a.status} /> },
            { key: "r", header: "Reference", render: (a) => a.reference_number ?? "—" },
            { key: "a", header: "Amount", align: "right", render: (a) => formatMoney(a.amount, deal.currency) },
            { key: "sg", header: "Signed", render: (a) => <DateText value={a.signed_on} /> },
            { key: "rg", header: "Registered", render: (a) => <DateText value={a.registered_on} /> },
            { key: "v", header: "Valid until", render: (a) => <DateText value={a.valid_until} /> },
          ]}
        />
      </Card>
      {editingAgreement && <AgreementForm dealId={id} agreement={editingAgreement === "new" ? undefined : editingAgreement} onClose={() => setEditingAgreement(null)} />}
    </div>
  );
}

function AgreementForm({ dealId, agreement, onClose }: { dealId: string; agreement?: Agreement; onClose: () => void }) {
  const allowed = useCan();
  const docs = useQuery({ queryKey: ["documents", { deal_id: dealId }], queryFn: () => api.documents.list({ deal_id: dealId, limit: 500 }) });
  const [v, setV] = useState({
    kind: agreement?.kind ?? "agreement_to_sell",
    status: agreement?.status ?? "draft",
    reference_number: agreement?.reference_number ?? "",
    amount: agreement?.amount ?? "",
    signed_on: agreement?.signed_on ?? "",
    registered_on: agreement?.registered_on ?? "",
    valid_until: agreement?.valid_until ?? "",
    document_id: agreement?.document_id ?? "",
    notes: agreement?.notes ?? "",
  });
  const save = useAction(
    () => {
      const amount = v.amount ? parseMoneyInput(v.amount) : null;
      if (v.amount && amount === null) throw new Error("Amount must be a number with at most two decimals");
      const body = {
        status: v.status,
        reference_number: v.reference_number || null,
        amount,
        signed_on: v.signed_on || null,
        registered_on: v.registered_on || null,
        valid_until: v.valid_until || null,
        document_id: v.document_id || null,
        notes: v.notes || null,
      };
      return agreement ? api.deals.updateAgreement(dealId, agreement.id, body) : api.deals.createAgreement(dealId, { ...body, kind: v.kind });
    },
    { invalidate: [["agreements", dealId]], success: "Saved", onSuccess: onClose },
  );
  const readOnly = !allowed(P.DEAL_WRITE);
  return (
    <Modal title={agreement ? humanize(agreement.kind) : "New agreement"} onClose={onClose}>
      <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate(undefined); }}>
        <fieldset disabled={readOnly} style={{ border: 0, padding: 0, margin: 0 }} className="stack">
          <div className="grid grid-2">
            {!agreement && <Field label="Kind"><Select value={v.kind} onChange={(e) => setV({ ...v, kind: e.target.value })} options={AGREEMENT_KINDS} /></Field>}
            <Field label="Status"><Select value={v.status} onChange={(e) => setV({ ...v, status: e.target.value })} options={AGREEMENT_STATUSES} /></Field>
            <Field label="Reference number"><Input value={v.reference_number} onChange={(e) => setV({ ...v, reference_number: e.target.value })} /></Field>
            <Field label="Amount (₹)"><Input inputMode="decimal" value={v.amount} onChange={(e) => setV({ ...v, amount: e.target.value })} /></Field>
            <Field label="Signed on"><Input type="date" value={v.signed_on} onChange={(e) => setV({ ...v, signed_on: e.target.value })} /></Field>
            <Field label="Registered on"><Input type="date" value={v.registered_on} onChange={(e) => setV({ ...v, registered_on: e.target.value })} /></Field>
            <Field label="Valid until"><Input type="date" value={v.valid_until} onChange={(e) => setV({ ...v, valid_until: e.target.value })} /></Field>
            <Field label="Document">
              <Select value={v.document_id} onChange={(e) => setV({ ...v, document_id: e.target.value })} placeholder="None"
                options={(docs.data?.items ?? []).filter((d) => !d.is_redacted).map((d) => ({ value: d.id, label: d.title ?? d.class_name }))} />
            </Field>
          </div>
          <Field label="Notes"><TextArea value={v.notes} onChange={(e) => setV({ ...v, notes: e.target.value })} /></Field>
          {!readOnly && <div className="row"><Button variant="primary" disabled={save.isPending}>Save</Button></div>}
        </fieldset>
      </form>
    </Modal>
  );
}

// ---- Ownership snapshots ----

export function SnapshotsTab({ dealId }: { dealId: string }) {
  const users = useUsers();
  const snaps = useQuery({ queryKey: ["snapshots", dealId], queryFn: () => api.deals.snapshots(dealId) });
  const confirm = useAction(() => api.deals.confirmOwnership(dealId, window.prompt("Confirmation note (optional)") ?? undefined), {
    invalidate: [["snapshots", dealId]],
    success: "Ownership confirmed and snapshotted",
  });
  return (
    <Card title="Ownership snapshots" actions={<Can p={P.DEAL_WRITE}><Button variant="primary" onClick={() => confirm.mutate(undefined)}>Confirm current ownership</Button></Can>}>
      <div className="muted small" style={{ marginBottom: 8 }}>
        A snapshot is taken when the deal starts and each time ownership is confirmed, so later changes to property ownership do not rewrite deal history.
      </div>
      <div className="stack">
        {snaps.data?.map((s) => (
          <Card key={s.id} title={<span>{humanize(s.reason)} · <DateText value={s.taken_at} time /> · {userName(users.data, s.taken_by_id)}</span>}>
            <Table
              rows={s.owners as { full_name?: string; owner_code?: string; share_percent?: string | null; ownership_type?: string; verification_status?: string }[]}
              empty="No owners at the time."
              columns={[
                { key: "n", header: "Owner", render: (o) => <span>{o.full_name ?? "—"} <span className="muted small">{o.owner_code}</span></span> },
                { key: "t", header: "Type", render: (o) => o.ownership_type ?? "—" },
                { key: "s", header: "Share", render: (o) => (o.share_percent ? `${o.share_percent}%` : "—") },
                { key: "v", header: "Verified", render: (o) => <StatusBadge status={o.verification_status} /> },
              ]}
            />
            {s.note && <div className="muted small">{s.note}</div>}
          </Card>
        ))}
      </div>
    </Card>
  );
}

// ---- Team ----

export function TeamTab({ dealId }: { dealId: string }) {
  const allowed = useCan();
  const users = useUsers();
  const team = useQuery({ queryKey: ["deal-assignments", dealId], queryFn: () => api.deals.assignments(dealId) });
  const [user, setUser] = useState("");
  const [role, setRole] = useState("member");
  const inv = [["deal-assignments", dealId]];
  const assign = useAction(() => api.deals.assign(dealId, user, role), { invalidate: inv, onSuccess: () => setUser("") });
  const unassign = useAction((uid: string) => api.deals.unassign(dealId, uid), { invalidate: inv });
  return (
    <Card title="Deal team">
      <Table
        rows={team.data}
        empty="No one assigned."
        columns={[
          { key: "u", header: "User", render: (a) => userName(users.data, a.user_id) },
          { key: "r", header: "Role", render: (a) => humanize(a.role) },
          { key: "x", header: "", render: (a) => <Can p={P.DEAL_ASSIGN}><Button size="sm" variant="danger" onClick={() => unassign.mutate(a.user_id)}>Remove</Button></Can> },
        ]}
      />
      {allowed(P.DEAL_ASSIGN) && (
        <div className="row" style={{ marginTop: 8 }}>
          <Select value={user} onChange={(e) => setUser(e.target.value)} placeholder="Add team member…" style={{ width: 240 }}
            options={(users.data ?? []).filter((u) => !team.data?.some((a) => a.user_id === u.id)).map((u) => ({ value: u.id, label: u.display_name ?? u.email ?? u.id }))} />
          <Select value={role} onChange={(e) => setRole(e.target.value)} options={["member", "lead", "legal", "technical", "finance"]} style={{ width: 140 }} />
          <Button disabled={!user} onClick={() => assign.mutate(undefined)}>Assign</Button>
        </div>
      )}
    </Card>
  );
}

// ---- Activity ----

export function ActivityTab({ dealId }: { dealId: string }) {
  const users = useUsers();
  const events = useQuery({ queryKey: ["deal-audit", dealId], queryFn: () => api.deals.audit(dealId) });
  return (
    <Card title="Activity (audit trail)">
      <Table
        rows={events.data}
        empty="No activity."
        columns={[
          { key: "w", header: "When", render: (e) => <DateText value={e.occurred_at} time /> },
          { key: "a", header: "Action", render: (e) => humanize(e.action.replace(/\./g, " ")) },
          { key: "u", header: "By", render: (e) => userName(users.data, e.actor_id) },
          {
            key: "d",
            header: "Details",
            render: (e) => {
              const details = { ...e.changes, ...e.metadata };
              return Object.keys(details).length ? <code className="small" style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(details)}</code> : "";
            },
          },
        ]}
      />
    </Card>
  );
}

// ---- Score ----

export function ScoreCard({ dealId, score }: { dealId: string; score: ControlCenter["score"] }) {
  const [open, setOpen] = useState(false);
  const compute = useAction(() => api.deals.computeScore(dealId), { invalidate: [["control-center", dealId]] });
  return (
    <Card title="Deal score" actions={<><Button size="sm" onClick={() => compute.mutate(undefined)}>Recompute</Button>{score && <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>Explain</Button>}</>}>
      {score ? (
        <div className="stack">
          <div className="row"><span className="stat-value">{Math.round(score.total)}</span><span className="muted">/ 100</span></div>
          <div className="muted small">Based on {Math.round(score.coverage * 100)}% of weighted factors with data · <DateText value={score.computed_at} time /></div>
          {score.coverage < 0.6 && <div className="warn">Low data coverage; treat this score with caution.</div>}
        </div>
      ) : <span className="muted">Not computed yet.</span>}
      {open && score && (
        <Modal title="Score breakdown" onClose={() => setOpen(false)} wide>
          <Table
            rows={score.breakdown}
            columns={[
              { key: "l", header: "Factor", render: (f) => f.label },
              { key: "w", header: "Weight", render: (f) => f.weight },
              { key: "s", header: "Score", render: (f) => (f.missing ? <Badge tone="warning">missing data</Badge> : Math.round(f.score ?? 0)) },
              { key: "f", header: "Fact", render: (f) => f.fact ?? "—" },
              { key: "e", header: "Explanation", render: (f) => <span className="small">{f.explanation}</span> },
            ]}
          />
          <KV items={[["Note", "Scores summarise recorded facts only. They are decision support, not a valuation or legal opinion."]]} />
        </Modal>
      )}
    </Card>
  );
}
