import { formatMoney, humanize, MILESTONE_KINDS, P, parseMoneyInput, PAYMENT_MODES, type Deal, type Payment, type PaymentMilestone } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { userName, useUsers } from "../../components/TasksPanel";
import { askReason, Button, Card, DateText, Field, Input, KV, Modal, Select, StatusBadge, Table, TextArea, useAction, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { Can, useCan, useMe } from "../../lib/auth";

export function FinanceTab({ deal }: { deal: Deal }) {
  const me = useMe();
  const allowed = useCan();
  const users = useUsers();
  const id = deal.id;
  const summary = useQuery({ queryKey: ["financials", id], queryFn: () => api.deals.financials(id) });
  const milestones = useQuery({ queryKey: ["milestones", id], queryFn: () => api.deals.milestones(id) });
  const payments = useQuery({ queryKey: ["payments", id], queryFn: () => api.deals.payments(id) });
  const [editing, setEditing] = useState<PaymentMilestone | "new" | null>(null);
  const [paying, setPaying] = useState<PaymentMilestone | "adhoc" | null>(null);
  const inv = [["financials", id], ["milestones", id], ["payments", id], ["control-center", id], ["dashboard"]];

  const decideMilestone = useAction(({ m, decision }: { m: PaymentMilestone; decision: string }) => {
    const note = decision === "rejected" ? askReason("Why is this milestone rejected?") : window.prompt("Approval note (optional)") ?? undefined;
    return note === null ? Promise.resolve(null) : api.deals.decideMilestone(id, m.id, decision, note);
  }, { invalidate: inv });
  const cancelMilestone = useAction((m: PaymentMilestone) => {
    const reason = askReason(`Reason for cancelling "${m.label}":`);
    return reason ? api.deals.cancelMilestone(id, m.id, reason) : Promise.resolve(null);
  }, { invalidate: inv });
  const decidePayment = useAction(({ p, decision }: { p: Payment; decision: string }) => {
    const note = decision === "rejected" ? askReason("Why is this payment rejected?") : window.prompt("Approval note (optional)") ?? undefined;
    return note === null ? Promise.resolve(null) : api.deals.decidePayment(id, p.id, decision, note);
  }, { invalidate: inv });
  const reversePayment = useAction((p: Payment) => {
    const reason = askReason("Reason for reversing this payment:");
    return reason ? api.deals.reversePayment(id, p.id, reason) : Promise.resolve(null);
  }, { invalidate: inv });

  const s = summary.data;
  const cur = deal.currency;
  return (
    <div className="stack">
      {s && (
        <Card title="Summary">
          <div className="grid grid-2">
            <KV
              items={[
                ["Asking price", formatMoney(s.asking_price, cur)],
                ["Expected price", formatMoney(s.expected_price, cur)],
                ["Negotiated price", formatMoney(s.negotiated_price, cur)],
                ["Planned in milestones", formatMoney(s.planned_total, cur)],
                ["Not yet planned", s.unplanned_amount ? formatMoney(s.unplanned_amount, cur) : "—"],
              ]}
            />
            <KV
              items={[
                ["Advance", `${formatMoney(s.advance_paid, cur)} paid of ${formatMoney(s.advance_planned, cur)} planned`],
                ["Paid (approved)", formatMoney(s.paid_total, cur)],
                ["Awaiting approval", formatMoney(s.pending_approval_total, cur)],
                ["Balance", s.balance_amount ? `${formatMoney(s.balance_amount, cur)} (against ${humanize(s.balance_basis)})` : "—"],
                ["Overdue milestones", s.overdue_milestones ? <span className="error-text">{s.overdue_milestones}</span> : "0"],
              ]}
            />
          </div>
        </Card>
      )}
      <Card title="Payment milestones" actions={<Can p={P.PAYMENT_WRITE}><Button variant="primary" onClick={() => setEditing("new")}>Add milestone</Button></Can>}>
        <Table
          rows={milestones.data}
          empty="No milestones planned."
          columns={[
            { key: "l", header: "Milestone", render: (m) => <div>{m.label}<div className="muted small">{m.kind}</div></div> },
            { key: "a", header: "Planned", align: "right", render: (m) => formatMoney(m.planned_amount, m.currency) },
            { key: "d", header: "Due", render: (m) => <DateText value={m.due_date} /> },
            { key: "s", header: "Status", render: (m) => <StatusBadge status={m.status} /> },
            { key: "ap", header: "Approval", render: (m) => <div><StatusBadge status={m.approval_status} />{m.approved_by_id && <div className="muted small">{userName(users.data, m.approved_by_id)}</div>}</div> },
            {
              key: "x",
              header: "",
              render: (m) =>
                m.status !== "cancelled" && (
                  <div className="row">
                    {allowed(P.PAYMENT_APPROVE) && m.approval_status !== "approved" && m.created_by_id !== me.id && (
                      <>
                        <Button size="sm" variant="primary" onClick={() => decideMilestone.mutate({ m, decision: "approved" })}>Approve</Button>
                        <Button size="sm" variant="danger" onClick={() => decideMilestone.mutate({ m, decision: "rejected" })}>Reject</Button>
                      </>
                    )}
                    {allowed(P.PAYMENT_WRITE) && m.approval_status === "approved" && m.status !== "paid" && <Button size="sm" onClick={() => setPaying(m)}>Record payment</Button>}
                    {allowed(P.PAYMENT_WRITE) && m.status !== "paid" && <Button size="sm" variant="ghost" onClick={() => setEditing(m)}>Edit</Button>}
                    {allowed(P.PAYMENT_APPROVE) && m.status !== "paid" && <Button size="sm" variant="ghost" onClick={() => cancelMilestone.mutate(m)}>Cancel</Button>}
                  </div>
                ),
            },
          ]}
        />
      </Card>
      <Card title="Payments" actions={<Can p={P.PAYMENT_WRITE}><Button onClick={() => setPaying("adhoc")}>Record unplanned payment</Button></Can>}>
        <Table
          rows={payments.data}
          empty="No payments recorded."
          columns={[
            { key: "d", header: "Paid on", render: (p) => <DateText value={p.paid_on} /> },
            { key: "a", header: "Amount", align: "right", render: (p) => <span className={p.status === "reversed" ? "muted" : ""} style={p.status === "reversed" ? { textDecoration: "line-through" } : undefined}>{formatMoney(p.amount, p.currency)}</span> },
            { key: "m", header: "Milestone", render: (p) => milestones.data?.find((m) => m.id === p.milestone_id)?.label ?? "Unplanned" },
            { key: "mo", header: "Mode", render: (p) => <div>{humanize(p.mode)}{p.reference && <div className="muted small">{p.reference}</div>}</div> },
            { key: "s", header: "Status", render: (p) => <div><StatusBadge status={p.status} />{(p.decision_note || p.reversal_reason) && <div className="muted small">{p.reversal_reason ?? p.decision_note}</div>}</div> },
            { key: "r", header: "Recorded by", render: (p) => userName(users.data, p.recorded_by_id) },
            {
              key: "x",
              header: "",
              render: (p) =>
                allowed(P.PAYMENT_APPROVE) && (
                  <div className="row">
                    {p.status === "recorded" && p.recorded_by_id !== me.id && (
                      <>
                        <Button size="sm" variant="primary" onClick={() => decidePayment.mutate({ p, decision: "approved" })}>Approve</Button>
                        <Button size="sm" variant="danger" onClick={() => decidePayment.mutate({ p, decision: "rejected" })}>Reject</Button>
                      </>
                    )}
                    {p.status !== "reversed" && <Button size="sm" variant="ghost" onClick={() => reversePayment.mutate(p)}>Reverse</Button>}
                  </div>
                ),
            },
          ]}
        />
        <div className="muted small" style={{ marginTop: 8 }}>Payments are never edited or deleted. Mistakes are corrected by reversing and re-recording. Approval must come from someone other than the recorder.</div>
      </Card>
      {editing && <MilestoneForm dealId={id} milestone={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
      {paying && <PaymentForm dealId={id} milestone={paying === "adhoc" ? undefined : paying} onClose={() => setPaying(null)} />}
    </div>
  );
}

function MilestoneForm({ dealId, milestone, onClose }: { dealId: string; milestone?: PaymentMilestone; onClose: () => void }) {
  const toast = useToast();
  const [v, setV] = useState({
    kind: milestone?.kind ?? "advance",
    label: milestone?.label ?? "",
    planned_amount: milestone?.planned_amount ?? "",
    due_date: milestone?.due_date ?? "",
    position: String(milestone?.position ?? 0),
    notes: milestone?.notes ?? "",
    reason: "",
  });
  const save = useAction(
    () => {
      const amount = parseMoneyInput(v.planned_amount);
      if (!amount) throw new Error("Enter the amount as a number with at most two decimals");
      const body = { label: v.label, planned_amount: amount, due_date: v.due_date || undefined, position: Number(v.position) || 0, notes: v.notes || undefined };
      return milestone ? api.deals.updateMilestone(dealId, milestone.id, { ...body, reason: v.reason }) : api.deals.createMilestone(dealId, { ...body, kind: v.kind });
    },
    { invalidate: [["milestones", dealId], ["financials", dealId], ["control-center", dealId]], success: "Saved; awaiting approval", onSuccess: onClose },
  );
  return (
    <Modal title={milestone ? "Edit milestone" : "New payment milestone"} onClose={onClose}>
      <form className="stack" onSubmit={(e) => { e.preventDefault(); if (milestone && v.reason.trim().length < 3) return toast("error", "A reason is required"); save.mutate(undefined); }}>
        <div className="grid grid-2">
          {!milestone && <Field label="Kind"><Select value={v.kind} onChange={(e) => setV({ ...v, kind: e.target.value })} options={MILESTONE_KINDS} /></Field>}
          <Field label="Label"><Input required value={v.label} onChange={(e) => setV({ ...v, label: e.target.value })} /></Field>
          <Field label="Planned amount (₹)"><Input required inputMode="decimal" value={v.planned_amount} onChange={(e) => setV({ ...v, planned_amount: e.target.value })} /></Field>
          <Field label="Due date"><Input type="date" value={v.due_date} onChange={(e) => setV({ ...v, due_date: e.target.value })} /></Field>
          <Field label="Order"><Input type="number" value={v.position} onChange={(e) => setV({ ...v, position: e.target.value })} /></Field>
        </div>
        <Field label="Notes"><TextArea value={v.notes} onChange={(e) => setV({ ...v, notes: e.target.value })} /></Field>
        {milestone && <Field label="Reason for change" hint="Changing the amount or due date resets approval"><Input required value={v.reason} onChange={(e) => setV({ ...v, reason: e.target.value })} /></Field>}
        <div className="row"><Button variant="primary" disabled={save.isPending}>Save</Button></div>
      </form>
    </Modal>
  );
}

function PaymentForm({ dealId, milestone, onClose }: { dealId: string; milestone?: PaymentMilestone; onClose: () => void }) {
  const docs = useQuery({ queryKey: ["documents", { deal_id: dealId }], queryFn: () => api.documents.list({ deal_id: dealId, limit: 500 }) });
  const [v, setV] = useState({ amount: milestone?.planned_amount ?? "", paid_on: new Date().toISOString().slice(0, 10), mode: "bank_transfer", reference: "", receipt_document_id: "", notes: "" });
  const save = useAction(
    () => {
      const amount = parseMoneyInput(v.amount);
      if (!amount) throw new Error("Enter the amount as a number with at most two decimals");
      return api.deals.recordPayment(dealId, {
        milestone_id: milestone?.id,
        amount,
        paid_on: v.paid_on,
        mode: v.mode,
        reference: v.reference || undefined,
        receipt_document_id: v.receipt_document_id || undefined,
        notes: v.notes || undefined,
      });
    },
    { invalidate: [["payments", dealId], ["milestones", dealId], ["financials", dealId], ["control-center", dealId]], success: "Payment recorded; awaiting approval", onSuccess: onClose },
  );
  return (
    <Modal title={milestone ? `Record payment — ${milestone.label}` : "Record unplanned payment"} onClose={onClose}>
      <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate(undefined); }}>
        <div className="grid grid-2">
          <Field label="Amount (₹)"><Input required inputMode="decimal" value={v.amount} onChange={(e) => setV({ ...v, amount: e.target.value })} /></Field>
          <Field label="Paid on"><Input type="date" required value={v.paid_on} onChange={(e) => setV({ ...v, paid_on: e.target.value })} /></Field>
          <Field label="Mode"><Select value={v.mode} onChange={(e) => setV({ ...v, mode: e.target.value })} options={PAYMENT_MODES} /></Field>
          <Field label="Reference (UTR / cheque no.)"><Input value={v.reference} onChange={(e) => setV({ ...v, reference: e.target.value })} /></Field>
        </div>
        <Field label="Receipt document">
          <Select value={v.receipt_document_id} onChange={(e) => setV({ ...v, receipt_document_id: e.target.value })} placeholder="None"
            options={(docs.data?.items ?? []).filter((d) => !d.is_redacted).map((d) => ({ value: d.id, label: `${d.title ?? d.class_name} (${d.class_name})` }))} />
        </Field>
        <Field label="Notes"><TextArea value={v.notes} onChange={(e) => setV({ ...v, notes: e.target.value })} /></Field>
        <div className="row"><Button variant="primary" disabled={save.isPending}>Record</Button></div>
      </form>
    </Modal>
  );
}
