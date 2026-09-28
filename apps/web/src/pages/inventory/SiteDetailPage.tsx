import { formatDerived, humanize, P, type SiteData, type SiteRevision } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { userName, useUsers } from "../../components/TasksPanel";
import { askReason, Badge, Button, Card, DateText, Field, Input, KV, Modal, PageHeader, StatusBadge, Table, useAction } from "../../components/ui";
import { api } from "../../lib/api";
import { Can, useCan, useMe } from "../../lib/auth";
import { normalizeSiteData, SiteDataForm } from "./SiteDataForm";

function flatten(obj: unknown, prefix = ""): Record<string, string> {
  const out: Record<string, string> = {};
  if (obj === null || obj === undefined) return out;
  if (typeof obj !== "object") return { [prefix]: String(obj) };
  const o = obj as Record<string, unknown>;
  if ("value" in o && "unit" in o && Object.keys(o).length === 2) return { [prefix]: `${o.value} ${o.unit}` };
  for (const [k, v] of Object.entries(o)) Object.assign(out, flatten(v, prefix ? `${prefix}.${k}` : k));
  return out;
}

function Diff({ before, after }: { before?: SiteData; after: SiteData }) {
  const a = flatten(before);
  const b = flatten(after);
  const keys = [...new Set([...Object.keys(a), ...Object.keys(b)])].filter((k) => a[k] !== b[k]).sort();
  if (!keys.length) return <div className="muted">No field changes.</div>;
  return (
    <Table
      rows={keys}
      columns={[
        { key: "f", header: "Field", render: (k) => <span className="mono small">{k}</span> },
        { key: "b", header: "Current", render: (k) => a[k] ?? <span className="muted">—</span> },
        { key: "a", header: "Proposed", render: (k) => <strong>{b[k] ?? "—"}</strong> },
      ]}
    />
  );
}

function DerivedList({ derived }: { derived: Record<string, unknown> }) {
  const entries = Object.entries(derived).filter(([, v]) => v && typeof v === "object" && "value" in (v as object));
  if (!entries.length) return <span className="muted small">No derived values (regional units are not converted).</span>;
  return (
    <div className="stack small">
      {entries.map(([k, v]) => {
        const d = v as { value: string; unit: string; formula: string };
        return <div key={k}>{humanize(k)}: {formatDerived(d.value, d.unit === "sqm" ? "m²" : d.unit)} <span className="muted">— {d.formula}</span></div>;
      })}
    </div>
  );
}

export function SiteDetailPage() {
  const { id = "" } = useParams();
  const me = useMe();
  const allowed = useCan();
  const users = useUsers();
  const site = useQuery({ queryKey: ["inventory", "site", id], queryFn: () => api.inventory.get(id) });
  const [proposing, setProposing] = useState(false);
  const inv = [["inventory"]];
  const approve = useAction((rev: SiteRevision) => api.inventory.approve(rev.id, window.prompt("Approval note (optional)") ?? undefined), { invalidate: inv, success: "Approved" });
  const reject = useAction((rev: SiteRevision) => {
    const note = askReason("Why is this change rejected?");
    return note ? api.inventory.reject(rev.id, note) : Promise.resolve(null);
  }, { invalidate: inv });

  const s = site.data;
  if (!s) return <div className="muted">Loading…</div>;
  const current = s.active_revision;
  const pending = s.pending_revision;
  const canDecide = pending && allowed(P.INVENTORY_APPROVE) && pending.submitted_by_id !== me.id;

  return (
    <div className="stack">
      <PageHeader
        title={<span className="mono">{s.site_code}</span>}
        subtitle={<span className="row">{humanize(s.property_type)} <StatusBadge status={s.approval_state} /> {s.status && <StatusBadge status={s.status} />}</span>}
        actions={<Can p={P.INVENTORY_WRITE}><Button disabled={!!pending} onClick={() => setProposing(true)} title={pending ? "A change is already awaiting approval" : undefined}>Propose change</Button></Can>}
      />
      {pending && (
        <Card
          title={<span>Pending {pending.change_type === "create" ? "new record" : "change"} · rev {pending.revision_no} by {userName(users.data, pending.submitted_by_id)}</span>}
          actions={
            canDecide ? (
              <>
                <Button variant="primary" onClick={() => approve.mutate(pending)}>Approve</Button>
                <Button variant="danger" onClick={() => reject.mutate(pending)}>Reject</Button>
              </>
            ) : pending.submitted_by_id === me.id ? <span className="muted small">Awaiting another administrator</span> : null
          }
        >
          {pending.change_note && <div style={{ marginBottom: 8 }}>“{pending.change_note}”</div>}
          {pending.match_decision.considered_candidates.length > 0 && (
            <div className="warn" style={{ marginBottom: 8 }}>Submitter reviewed {pending.match_decision.considered_candidates.length} possible match(es) and confirmed this is {pending.match_decision.decision === "new" ? "a new site" : "an update"}.</div>
          )}
          <Diff before={current?.data} after={pending.data} />
          <div style={{ marginTop: 8 }}><DerivedList derived={pending.derived} /></div>
        </Card>
      )}
      <div className="grid grid-2">
        <Card title="Current approved data">
          {current ? (
            <div className="stack">
              <KV items={Object.entries(flatten(current.data)).map(([k, v]) => [k, v])} />
              <DerivedList derived={current.derived} />
            </div>
          ) : <span className="muted">Not approved yet — this record is not visible in standard searches.</span>}
        </Card>
        <Card title="Links">
          <KV
            items={[
              ["Property", s.property_id ? <Link to={`/properties/${s.property_id}`}>Open property</Link> : null],
              ["Source document", s.source_document_id ? "Linked" : null],
              ["Source map", s.source_map_upload_id ? "Linked" : null],
              ["Created", <DateText value={s.created_at} time />],
              ["Updated", <DateText value={s.updated_at} time />],
            ]}
          />
        </Card>
      </div>
      <Card title="Revision history">
        <Table
          rows={s.history}
          columns={[
            { key: "n", header: "Rev", render: (r) => r.revision_no },
            { key: "t", header: "Type", render: (r) => r.change_type },
            { key: "s", header: "Status", render: (r) => <span><StatusBadge status={r.status} /> {r.id === s.active_revision_id && <Badge tone="success">active</Badge>}</span> },
            { key: "b", header: "Submitted", render: (r) => <span>{userName(users.data, r.submitted_by_id)} · <DateText value={r.submitted_at} /></span> },
            { key: "rv", header: "Reviewed", render: (r) => (r.reviewed_at ? <span>{userName(users.data, r.reviewed_by_id)} · <DateText value={r.reviewed_at} />{r.review_note && <div className="muted small">{r.review_note}</div>}</span> : "—") },
            { key: "c", header: "Note", render: (r) => r.change_note ?? "" },
          ]}
        />
      </Card>
      {proposing && <ProposeChange siteId={s.id} base={(current ?? s.history[0])!.data} onClose={() => setProposing(false)} />}
    </div>
  );
}

function ProposeChange({ siteId, base, onClose }: { siteId: string; base: SiteData; onClose: () => void }) {
  const [data, setData] = useState<SiteData>(structuredClone(base));
  const [note, setNote] = useState("");
  const save = useAction(() => api.inventory.proposeRevision(siteId, { data: normalizeSiteData(data), change_note: note }), {
    invalidate: [["inventory"]],
    success: "Change submitted for approval",
    onSuccess: onClose,
  });
  return (
    <Modal title="Propose change" onClose={onClose} wide>
      <div className="stack">
        <SiteDataForm value={data} onChange={setData} lockType />
        <Field label="Reason for change"><Input required value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        <div className="row"><Button variant="primary" disabled={note.trim().length < 3 || save.isPending} onClick={() => save.mutate(undefined)}>Submit for approval</Button></div>
      </div>
    </Modal>
  );
}
