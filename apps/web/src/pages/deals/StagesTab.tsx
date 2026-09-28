import { P, type ChecklistItem, type Deal, type DealStage } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { userName, useUsers } from "../../components/TasksPanel";
import { askReason, Badge, Button, Card, DateText, Field, Modal, Select, StatusBadge, Table, TextArea, useAction } from "../../components/ui";
import { api } from "../../lib/api";
import { useCan } from "../../lib/auth";

export function StagesTab({ deal }: { deal: Deal }) {
  const allowed = useCan();
  const users = useUsers();
  const stages = useQuery({ queryKey: ["deal-stages", deal.id], queryFn: () => api.deals.stages(deal.id) });
  const transitions = useQuery({ queryKey: ["deal-transitions", deal.id], queryFn: () => api.deals.transitions(deal.id) });
  const [moving, setMoving] = useState<DealStage | null>(null);
  const list = stages.data ?? [];
  const current = list.find((s) => s.status === "active");
  const open = deal.status === "open";
  const stageName = (sid: string | null) => list.find((s) => s.stage_definition_id === sid)?.name ?? "—";

  return (
    <div className="stack">
      {list.map((s) => (
        <StageCard
          key={s.id}
          deal={deal}
          stage={s}
          isCurrent={s.id === current?.id}
          canMoveHere={open && allowed(P.DEAL_STAGE_MOVE) && s.status !== "active"}
          onMove={() => setMoving(s)}
        />
      ))}
      <Card title="Stage history">
        <Table
          rows={transitions.data}
          empty="No transitions."
          columns={[
            { key: "w", header: "When", render: (t) => <DateText value={t.occurred_at} time /> },
            { key: "d", header: "Move", render: (t) => <span><StatusBadge status={t.direction} /> {stageName(t.from_stage_id)} → {stageName(t.to_stage_id)}</span> },
            { key: "r", header: "Reason", render: (t) => t.reason ?? "" },
            { key: "b", header: "Bypassed", render: (t) => [t.bypassed_stage_ids.length && `${t.bypassed_stage_ids.length} stage(s)`, t.bypassed_checklist_item_ids.length && `${t.bypassed_checklist_item_ids.length} checklist item(s)`].filter(Boolean).join(", ") || "—" },
            { key: "a", header: "By", render: (t) => userName(users.data, t.actor_id) },
          ]}
        />
      </Card>
      {moving && current && <MoveDialog deal={deal} from={current} to={moving} stages={list} onClose={() => setMoving(null)} />}
    </div>
  );
}

function StageCard({ deal, stage, isCurrent, canMoveHere, onMove }: { deal: Deal; stage: DealStage; isCurrent: boolean; canMoveHere: boolean; onMove: () => void }) {
  const visible = stage.checklist.filter((i) => !i.is_hidden);
  const done = visible.filter((i) => i.status !== "pending").length;
  const [expanded, setExpanded] = useState(isCurrent);
  return (
    <Card
      title={
        <span className="row">
          <span style={{ width: 10, height: 10, borderRadius: 2, background: stage.color ?? "#94a3b8", display: "inline-block" }} />
          {stage.position + 1}. {stage.name}
          <StatusBadge status={stage.status} />
          {stage.is_terminal && <Badge tone="success">final</Badge>}
          {visible.length > 0 && <span className="muted small">{done}/{visible.length} checklist</span>}
        </span>
      }
      actions={
        <>
          {stage.bypass_reason && <span className="small muted">Bypassed: {stage.bypass_reason}</span>}
          {stage.entered_at && <span className="small muted">Entered <DateText value={stage.entered_at} /></span>}
          {canMoveHere && <Button size="sm" onClick={onMove}>Move here</Button>}
          {visible.length > 0 && <Button size="sm" variant="ghost" onClick={() => setExpanded(!expanded)}>{expanded ? "Hide" : "Checklist"}</Button>}
        </>
      }
    >
      {expanded && visible.length > 0 ? <Checklist deal={deal} items={visible} editable={isCurrent || stage.status === "completed"} /> : <span className="muted small">{stage.sla_days ? `SLA ${stage.sla_days} days` : ""}</span>}
    </Card>
  );
}

function Checklist({ deal, items, editable }: { deal: Deal; items: ChecklistItem[]; editable: boolean }) {
  const allowed = useCan();
  const users = useUsers();
  const docs = useQuery({ queryKey: ["documents", { deal_id: deal.id }], queryFn: () => api.documents.list({ deal_id: deal.id, limit: 500 }) });
  const inv = [["deal-stages", deal.id], ["control-center", deal.id]];
  const update = useAction(({ item, status, note, document_id }: { item: ChecklistItem; status: string; note?: string; document_id?: string }) =>
    api.deals.updateChecklist(deal.id, item.id, { status, note, document_id: document_id ?? item.document_id ?? undefined }), { invalidate: inv });
  const bypass = useAction((item: ChecklistItem) => {
    const reason = askReason(`Reason for bypassing "${item.label}":`);
    return reason ? api.deals.bypassChecklist(deal.id, item.id, reason) : Promise.resolve(null);
  }, { invalidate: inv });
  const canEdit = editable && deal.status === "open" && allowed(P.DEAL_WRITE);

  return (
    <Table
      rows={items}
      columns={[
        { key: "l", header: "Item", render: (i) => <span>{i.label} {i.is_required && <Badge tone="info">required</Badge>}</span> },
        { key: "s", header: "Status", render: (i) => <StatusBadge status={i.status} /> },
        { key: "n", header: "Note", render: (i) => <span className="small">{i.note ?? ""}</span> },
        {
          key: "d",
          header: "Evidence",
          render: (i) =>
            canEdit ? (
              <Select
                value={i.document_id ?? ""}
                disabled={i.status === "bypassed"}
                placeholder={i.document_class_key ? `Link ${i.document_class_key.replace(/_/g, " ")}` : "Link document"}
                onChange={(e) => update.mutate({ item: i, status: i.status, note: i.note ?? undefined, document_id: e.target.value || undefined })}
                options={(docs.data?.items ?? []).filter((d) => !d.is_redacted && (!i.document_class_key || d.class_key === i.document_class_key)).map((d) => ({ value: d.id, label: d.title ?? d.class_name }))}
                style={{ width: 200 }}
              />
            ) : i.document_id ? "Linked" : "—",
        },
        { key: "c", header: "Completed", render: (i) => (i.completed_at ? <span className="small">{userName(users.data, i.completed_by_id)} · <DateText value={i.completed_at} /></span> : "—") },
        {
          key: "x",
          header: "",
          render: (i) =>
            canEdit && (
              <div className="row">
                {(i.status === "pending" || i.status === "not_applicable") && <Button size="sm" onClick={() => update.mutate({ item: i, status: "done" })}>Done</Button>}
                {i.status === "pending" && !i.is_required && (
                  <Button size="sm" onClick={() => { const note = askReason("Why is this not applicable?"); if (note) update.mutate({ item: i, status: "not_applicable", note }); }}>N/A</Button>
                )}
                {i.status !== "pending" && <Button size="sm" variant="ghost" onClick={() => update.mutate({ item: i, status: "pending" })}>Reopen</Button>}
                {i.status === "pending" && allowed(P.DEAL_CHECKLIST_BYPASS) && <Button size="sm" variant="danger" onClick={() => bypass.mutate(i)}>Bypass</Button>}
              </div>
            ),
        },
      ]}
    />
  );
}

function MoveDialog({ deal, from, to, stages, onClose }: { deal: Deal; from: DealStage; to: DealStage; stages: DealStage[]; onClose: () => void }) {
  const allowed = useCan();
  const [reason, setReason] = useState("");
  const [bypass, setBypass] = useState(false);
  const backward = to.position < from.position;
  const skipped = stages.filter((s) => s.position > from.position && s.position < to.position);
  const isSkip = skipped.length > 0;
  const unskippable = skipped.filter((s) => !s.is_skippable);
  const pendingRequired = from.checklist.filter((i) => !i.is_hidden && i.is_required && i.status === "pending");
  const needsReason = backward || isSkip || bypass;
  const blocked = (isSkip && (!allowed(P.DEAL_STAGE_SKIP) || unskippable.length > 0)) || (!backward && pendingRequired.length > 0 && !bypass);
  const move = useAction(
    () => api.deals.transition(deal.id, { target_stage_key: to.key, reason: reason || undefined, bypass_incomplete_checklist: bypass }),
    { invalidate: [["deal-stages", deal.id], ["deal-transitions", deal.id], ["control-center", deal.id], ["deals"], ["pipeline"]], success: `Moved to ${to.name}`, onSuccess: onClose },
  );
  return (
    <Modal title={`Move to “${to.name}”`} onClose={onClose}>
      <div className="stack">
        {backward && <div className="warn">Moving back from “{from.name}”. A reason is required and recorded.</div>}
        {isSkip && (
          <div className="warn">
            This skips {skipped.map((s) => s.name).join(", ")}. Skipped stages are recorded as bypassed.
            {!allowed(P.DEAL_STAGE_SKIP) && <div className="error-text">You do not have permission to skip stages.</div>}
            {unskippable.length > 0 && <div className="error-text">These stages cannot be skipped: {unskippable.map((s) => s.name).join(", ")}</div>}
          </div>
        )}
        {to.is_terminal && <div className="warn">This is the final stage; the deal will be marked won.</div>}
        {!backward && pendingRequired.length > 0 && (
          <div className="stack">
            <div className="warn">Required checklist items still pending in “{from.name}”: {pendingRequired.map((i) => i.label).join(", ")}</div>
            {allowed(P.DEAL_CHECKLIST_BYPASS) ? (
              <label className="row small"><input type="checkbox" checked={bypass} onChange={(e) => setBypass(e.target.checked)} /> Bypass incomplete items (audited)</label>
            ) : <div className="error-text">Complete them first, or ask someone with bypass permission.</div>}
          </div>
        )}
        {needsReason && <Field label="Reason"><TextArea required value={reason} onChange={(e) => setReason(e.target.value)} /></Field>}
        <div className="row">
          <Button variant="primary" disabled={blocked || (needsReason && reason.trim().length < 3) || move.isPending} onClick={() => move.mutate(undefined)}>Move</Button>
        </div>
      </div>
    </Modal>
  );
}
