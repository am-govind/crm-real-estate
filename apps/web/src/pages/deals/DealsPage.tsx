import { formatMoney, formatMoneyCompact, P, PRIORITIES } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useUsers } from "../../components/TasksPanel";
import { Badge, Card, DateText, Empty, Input, PageHeader, Select, StatusBadge, Table, Tabs, useAction } from "../../components/ui";
import { api } from "../../lib/api";
import { useCan } from "../../lib/auth";

const DEAL_STATUSES = ["open", "on_hold", "won", "lost", "cancelled"] as const;

export function DealsPage() {
  const [view, setView] = useState<"pipeline" | "list">("pipeline");
  return (
    <div className="stack">
      <PageHeader title="Deals" actions={<Tabs value={view} onChange={setView} tabs={[{ key: "pipeline", label: "Pipeline" }, { key: "list", label: "List" }]} />} />
      {view === "pipeline" ? <Pipeline /> : <DealList />}
    </div>
  );
}

function Pipeline() {
  const navigate = useNavigate();
  const allowed = useCan();
  const users = useUsers();
  const [activationId, setActivationId] = useState("");
  const [assignee, setAssignee] = useState("");
  const activations = useQuery({ queryKey: ["workflow-activations"], queryFn: api.workflows.activations });
  const templates = useQuery({ queryKey: ["workflow-templates"], queryFn: api.workflows.templates });
  const pipeline = useQuery({
    queryKey: ["pipeline", activationId, assignee],
    queryFn: () => api.reports.pipeline({ activation_id: activationId, assignee_id: assignee }),
  });
  const [dragging, setDragging] = useState<{ dealId: string; fromIndex: number } | null>(null);
  const move = useAction(
    ({ dealId, key, reason }: { dealId: string; key: string; reason?: string }) => api.deals.transition(dealId, { target_stage_key: key, reason }),
    { invalidate: [["pipeline"], ["deals"], ["dashboard"]], success: "Deal moved" },
  );

  function drop(toIndex: number, key: string) {
    if (!dragging || dragging.fromIndex === toIndex) return;
    let reason: string | undefined;
    if (toIndex < dragging.fromIndex || toIndex > dragging.fromIndex + 1) {
      const r = window.prompt(toIndex < dragging.fromIndex ? "Reason for moving back:" : "Reason for skipping stages:");
      if (!r || r.trim().length < 3) return;
      reason = r.trim();
    }
    move.mutate({ dealId: dragging.dealId, key, reason });
    setDragging(null);
  }

  const data = pipeline.data;
  const tName = (id: string) => templates.data?.find((t) => t.id === id)?.name ?? "Workflow";
  return (
    <div className="stack">
      <div className="row">
        <Select value={activationId} onChange={(e) => setActivationId(e.target.value)} placeholder="Default workflow" style={{ width: 260 }}
          options={(activations.data ?? []).filter((a) => a.is_active).map((a) => ({ value: a.id, label: `${tName(a.template_version.template_id)} v${a.template_version.version}` }))} />
        <Select value={assignee} onChange={(e) => setAssignee(e.target.value)} placeholder="Everyone" style={{ width: 200 }}
          options={(users.data ?? []).map((u) => ({ value: u.id, label: u.display_name ?? u.email ?? u.id }))} />
        {data?.totals.deals !== undefined && (
          <span className="muted">{data.totals.deals} active deals · {formatMoneyCompact(data.totals.value)}</span>
        )}
      </div>
      {data && data.stages.length === 0 && <Empty>No workflow is activated yet. An administrator can activate one under Administration → Workflows.</Empty>}
      <div className="kanban">
        {data?.stages.map((s, idx) => (
          <div key={s.key} className="kanban-col" onDragOver={(e) => e.preventDefault()} onDrop={() => drop(idx, s.key)}>
            <div className="kanban-col-header" style={{ borderTop: `3px solid ${s.color ?? "#94a3b8"}` }}>
              <span>{s.name}</span>
              <span className="muted small">{s.count} · {formatMoneyCompact(s.value)}</span>
            </div>
            {s.deals.map((d) => (
              <div
                key={d.deal_id}
                className={`kanban-card ${d.is_stuck ? "stuck" : ""}`}
                draggable={allowed(P.DEAL_STAGE_MOVE)}
                onDragStart={() => setDragging({ dealId: d.deal_id, fromIndex: idx })}
                onClick={() => navigate(`/deals/${d.deal_id}`)}
              >
                <strong>{d.title}</strong>
                <span className="muted small">{d.code} · {d.property_name}</span>
                <span className="row small">
                  <StatusBadge status={d.priority} />
                  {d.amount && <span className="mono">{formatMoneyCompact(d.amount, d.currency)}</span>}
                </span>
                {d.days_in_stage !== null && (
                  <span className={`small ${d.is_stuck ? "error-text" : "muted"}`}>
                    {d.days_in_stage} day(s) in stage{d.is_stuck && s.sla_days !== null ? ` · SLA ${s.sla_days}d exceeded` : ""}
                  </span>
                )}
                {d.next_action && <span className="small">Next: {d.next_action} {d.next_action_due && <>(<DateText value={d.next_action_due} />)</>}</span>}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function DealList() {
  const navigate = useNavigate();
  const [f, setF] = useState({ q: "", status: "open", priority: "" });
  const query = { q: f.q, status: f.status ? [f.status] : undefined, priority: f.priority, limit: 200 };
  const deals = useQuery({ queryKey: ["deals", "list", query], queryFn: () => api.deals.list(query) });
  return (
    <Card>
      <div className="row" style={{ marginBottom: 12 }}>
        <Input placeholder="Search deal, property…" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} style={{ width: 280 }} />
        <Select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })} options={DEAL_STATUSES} placeholder="Any status" style={{ width: 150 }} />
        <Select value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })} options={PRIORITIES} placeholder="Any priority" style={{ width: 150 }} />
      </div>
      <Table
        rows={deals.data?.items}
        onRowClick={(d) => navigate(`/deals/${d.id}`)}
        columns={[
          { key: "c", header: "Code", render: (d) => d.code },
          { key: "t", header: "Deal", render: (d) => <div>{d.title}<div className="muted small">{d.property_code} · {d.property_name}</div></div> },
          { key: "s", header: "Stage", render: (d) => d.current_stage_name ?? "—" },
          { key: "st", header: "Status", render: (d) => <span><StatusBadge status={d.status} /> {d.active_override_reason && <Badge tone="warning">override</Badge>}</span> },
          { key: "p", header: "Priority", render: (d) => <StatusBadge status={d.priority} /> },
          { key: "v", header: "Value", align: "right", render: (d) => formatMoney(d.negotiated_price ?? d.expected_price ?? d.asking_price, d.currency) },
          { key: "n", header: "Next action", render: (d) => d.next_action ?? "—" },
        ]}
      />
    </Card>
  );
}
