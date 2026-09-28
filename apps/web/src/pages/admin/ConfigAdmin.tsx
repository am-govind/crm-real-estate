import { humanize, LAND_TYPES, type GeoUnit } from "@landcrm/domain";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { GEO_LEVELS, type GeoLevel } from "../../components/GeoPicker";
import { userName, useUsers } from "../../components/TasksPanel";
import { Badge, Button, Card, DateText, Field, Input, Modal, Select, Table, TextArea, useAction } from "../../components/ui";
import { api } from "../../lib/api";
import { useMe } from "../../lib/auth";

const DOC_CATEGORIES = ["ownership", "property", "transaction", "identity", "financial", "internal"] as const;

// ---- Documents ----

export function DocumentAdmin() {
  const classes = useQuery({ queryKey: ["document-classes"], queryFn: api.documents.classes });
  const rules = useQuery({ queryKey: ["document-rules"], queryFn: api.documents.rules });
  const [creating, setCreating] = useState(false);
  const [rule, setRule] = useState({ scope: "deal", class_id: "", land_types: [] as string[] });
  const inv = [["document-rules"], ["documents"]];
  const addRule = useAction(() => api.documents.createRule(rule), { invalidate: inv, success: "Rule added", onSuccess: () => setRule({ ...rule, class_id: "", land_types: [] }) });
  const deactivate = useAction(api.documents.deactivateRule, { invalidate: inv });

  return (
    <div className="stack">
      <Card title="Required documents" actions={<span className="muted small">Drives the “N/M received” completeness on properties and deals.</span>}>
        <Table
          rows={rules.data?.filter((r) => r.is_active)}
          empty="No required documents configured."
          columns={[
            { key: "c", header: "Document", render: (r) => r.document_class.name },
            { key: "s", header: "Required for", render: (r) => humanize(r.scope) },
            { key: "l", header: "Land types", render: (r) => (r.land_types.length ? r.land_types.map(humanize).join(", ") : "All") },
            { key: "x", header: "", render: (r) => <Button size="sm" variant="danger" onClick={() => deactivate.mutate(r.id)}>Remove</Button> },
          ]}
        />
        <div className="row" style={{ marginTop: 12 }}>
          <Select value={rule.scope} onChange={(e) => setRule({ ...rule, scope: e.target.value })} options={["property", "deal"]} style={{ width: 120 }} />
          <Select value={rule.class_id} onChange={(e) => setRule({ ...rule, class_id: e.target.value })} placeholder="Document type…" style={{ width: 260 }}
            options={(classes.data ?? []).filter((c) => c.applies_to.includes(rule.scope)).map((c) => ({ value: c.id, label: c.name }))} />
          <select className="input" multiple value={rule.land_types} onChange={(e) => setRule({ ...rule, land_types: Array.from(e.target.selectedOptions, (o) => o.value) })} style={{ width: 200, height: 70 }} title="Land types (none = all)">
            {LAND_TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
          </select>
          <Button disabled={!rule.class_id} onClick={() => addRule.mutate(undefined)}>Add requirement</Button>
        </div>
      </Card>
      <Card title="Document types" actions={<Button onClick={() => setCreating(true)}>New document type</Button>}>
        <Table
          rows={classes.data}
          columns={[
            { key: "n", header: "Name", render: (c) => <div>{c.name} {c.tenant_id === null && <Badge>system</Badge>}<div className="muted small mono">{c.key}</div></div> },
            { key: "c", header: "Category", render: (c) => c.category },
            { key: "s", header: "Sensitive", render: (c) => (c.is_sensitive ? <Badge tone="warning">sensitive</Badge> : "") },
            { key: "a", header: "Default access", render: (c) => c.default_access_policy },
            { key: "e", header: "Expiry", render: (c) => (c.requires_expiry ? "Required" : "") },
            { key: "ap", header: "Applies to", render: (c) => c.applies_to.join(", ") },
          ]}
        />
      </Card>
      {creating && <ClassForm onClose={() => setCreating(false)} />}
    </div>
  );
}

function ClassForm({ onClose }: { onClose: () => void }) {
  const [v, setV] = useState({ key: "", name: "", category: "property", is_sensitive: false, default_access_policy: "standard", requires_expiry: false, applies_to: ["property", "deal"], description: "" });
  const save = useAction(() => api.documents.createClass({ ...v, description: v.description || undefined }), { invalidate: [["document-classes"]], success: "Document type created", onSuccess: onClose });
  return (
    <Modal title="New document type" onClose={onClose}>
      <div className="stack">
        <div className="grid grid-2">
          <Field label="Key"><Input value={v.key} onChange={(e) => setV({ ...v, key: e.target.value })} placeholder="e.g. mutation_order" /></Field>
          <Field label="Name"><Input value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} /></Field>
          <Field label="Category"><Select value={v.category} onChange={(e) => setV({ ...v, category: e.target.value })} options={DOC_CATEGORIES} /></Field>
          <Field label="Default access"><Select value={v.default_access_policy} onChange={(e) => setV({ ...v, default_access_policy: e.target.value })} options={["standard", "restricted", "confidential"]} /></Field>
        </div>
        <label className="row"><input type="checkbox" checked={v.is_sensitive} onChange={(e) => setV({ ...v, is_sensitive: e.target.checked })} /> Sensitive (identity, bank or similar personal data)</label>
        <label className="row"><input type="checkbox" checked={v.requires_expiry} onChange={(e) => setV({ ...v, requires_expiry: e.target.checked })} /> Requires an expiry date</label>
        <Field label="Applies to">
          <div className="row">
            {["property", "deal", "owner", "site_visit"].map((a) => (
              <label key={a} className="row small"><input type="checkbox" checked={v.applies_to.includes(a)} onChange={(e) => setV({ ...v, applies_to: e.target.checked ? [...v.applies_to, a] : v.applies_to.filter((x) => x !== a) })} />{humanize(a)}</label>
            ))}
          </div>
        </Field>
        <Field label="Description"><TextArea value={v.description} onChange={(e) => setV({ ...v, description: e.target.value })} /></Field>
        <div className="row"><Button variant="primary" disabled={!v.key || !v.name || save.isPending} onClick={() => save.mutate(undefined)}>Create</Button></div>
      </div>
    </Modal>
  );
}

// ---- Scoring ----

export function ScoringAdmin() {
  const factors = useQuery({ queryKey: ["scoring-factors"], queryFn: api.scoring.factors });
  const model = useQuery({ queryKey: ["scoring-model"], queryFn: api.scoring.model });
  const [draft, setDraft] = useState<{ name: string; factors: { key: string; weight: string; params: string }[] } | null>(null);
  const current = draft ?? (model.data && {
    name: model.data.name,
    factors: model.data.factors.map((f) => ({ key: f.key, weight: String(f.weight), params: JSON.stringify(f.params ?? {}) })),
  });
  const save = useAction(
    () => api.scoring.updateModel({ name: current!.name, factors: current!.factors.map((f) => ({ key: f.key, weight: Number(f.weight), params: f.params ? JSON.parse(f.params) : {} })) }),
    { invalidate: [["scoring-model"]], success: "Scoring model saved", onSuccess: () => setDraft(null) },
  );
  if (!current) return <div className="muted">Loading…</div>;
  const set = (next: typeof current) => setDraft(next);
  const unused = (factors.data ?? []).filter((f) => !current.factors.some((x) => x.key === f.key));
  return (
    <Card title="Deal scoring model">
      <div className="stack">
        <div className="muted small">Each factor scores a recorded fact from 0–100 and explains itself. Missing data is flagged and excluded from coverage rather than guessed.</div>
        <Field label="Model name"><Input value={current.name} onChange={(e) => set({ ...current, name: e.target.value })} /></Field>
        <Table
          rows={current.factors}
          columns={[
            { key: "k", header: "Factor", render: (f) => factors.data?.find((x) => x.key === f.key)?.label ?? f.key },
            { key: "w", header: "Weight", render: (f) => <Input type="number" min={0} step="0.5" value={f.weight} onChange={(e) => set({ ...current, factors: current.factors.map((x) => (x.key === f.key ? { ...x, weight: e.target.value } : x)) })} style={{ width: 90 }} /> },
            { key: "p", header: "Parameters (JSON)", render: (f) => <Input className="mono" value={f.params} onChange={(e) => set({ ...current, factors: current.factors.map((x) => (x.key === f.key ? { ...x, params: e.target.value } : x)) })} /> },
            { key: "x", header: "", render: (f) => <Button size="sm" variant="danger" onClick={() => set({ ...current, factors: current.factors.filter((x) => x.key !== f.key) })}>Remove</Button> },
          ]}
        />
        {unused.length > 0 && (
          <div className="row">
            <Select value="" onChange={(e) => e.target.value && set({ ...current, factors: [...current.factors, { key: e.target.value, weight: "1", params: "{}" }] })} placeholder="Add factor…" options={unused.map((f) => ({ value: f.key, label: f.label }))} style={{ width: 280 }} />
          </div>
        )}
        <div className="row"><Button variant="primary" disabled={!draft || save.isPending} onClick={() => save.mutate(undefined)}>Save</Button></div>
      </div>
    </Card>
  );
}

// ---- Geography ----

export function GeographyAdmin() {
  const me = useMe();
  const qc = useQueryClient();
  const [path, setPath] = useState<GeoUnit[]>([]);
  const level: GeoLevel | undefined = GEO_LEVELS[path.length];
  const parent = path[path.length - 1];
  const units = useQuery({ queryKey: ["geo-units", level, parent?.id], queryFn: () => api.geo.list({ level, parent_id: parent?.id }), enabled: !!level });
  const [v, setV] = useState({ name: "", local_name: "", code: "" });
  const add = useAction(() => api.geo.create({ level, parent_id: parent?.id, name: v.name, local_name: v.local_name || undefined, code: v.code || undefined }), {
    success: "Added",
    onSuccess: () => { setV({ name: "", local_name: "", code: "" }); qc.invalidateQueries({ queryKey: ["geo-units"] }); },
  });
  return (
    <Card title="Geography">
      <div className="row" style={{ marginBottom: 12 }}>
        <Button size="sm" variant="ghost" onClick={() => setPath([])}>All {me.terminology.state}s</Button>
        {path.map((u, i) => (
          <span key={u.id} className="row">› <Button size="sm" variant="ghost" onClick={() => setPath(path.slice(0, i + 1))}>{u.name}</Button></span>
        ))}
      </div>
      {level ? (
        <>
          <Table
            rows={units.data}
            empty={`No ${me.terminology[level].toLowerCase()} entries yet.`}
            onRowClick={GEO_LEVELS[path.length + 1] ? (u) => setPath([...path, u]) : undefined}
            columns={[
              { key: "n", header: me.terminology[level], render: (u) => u.name },
              { key: "l", header: "Local name", render: (u) => u.local_name ?? "" },
              { key: "c", header: "Code", render: (u) => u.code ?? "" },
              { key: "s", header: "", render: (u) => (u.tenant_id === null ? <Badge>shared</Badge> : "") },
            ]}
          />
          <form className="row" style={{ marginTop: 12 }} onSubmit={(e) => { e.preventDefault(); add.mutate(undefined); }}>
            <Input required placeholder={`New ${me.terminology[level].toLowerCase()}`} value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} style={{ width: 220 }} />
            <Input placeholder="Local name" value={v.local_name} onChange={(e) => setV({ ...v, local_name: e.target.value })} style={{ width: 180 }} />
            <Input placeholder="Code" value={v.code} onChange={(e) => setV({ ...v, code: e.target.value })} style={{ width: 120 }} />
            <Button>Add</Button>
          </form>
        </>
      ) : <div className="muted">Lowest level reached.</div>}
    </Card>
  );
}

// ---- Settings ----

export function SettingsAdmin() {
  const me = useMe();
  const tenant = useQuery({ queryKey: ["tenant"], queryFn: api.tenant.get });
  const [terms, setTerms] = useState<Record<string, string> | null>(null);
  const current = terms ?? me.terminology;
  const save = useAction(() => api.tenant.updateSettings({ terminology: current }), { invalidate: [["tenant"], ["me"]], success: "Settings saved", onSuccess: () => setTerms(null) });
  return (
    <Card title={`Organisation settings — ${tenant.data?.name ?? ""}`}>
      <div className="stack">
        <div className="muted small">Default currency: {tenant.data?.default_currency} · Country: {tenant.data?.country_code}</div>
        <div className="muted small">Region names differ across states (e.g. Tehsil, Taluka, Mandal). These labels are used across the app.</div>
        <div className="grid grid-4">
          {GEO_LEVELS.map((l) => (
            <Field key={l} label={`Label for ${l}`}><Input value={current[l] ?? ""} onChange={(e) => setTerms({ ...current, [l]: e.target.value })} /></Field>
          ))}
        </div>
        <div className="row"><Button variant="primary" disabled={!terms || save.isPending} onClick={() => save.mutate(undefined)}>Save</Button></div>
      </div>
    </Card>
  );
}

// ---- Audit ----

export function AuditAdmin() {
  const users = useUsers();
  const [f, setF] = useState({ entity_type: "", action: "", actor_id: "" });
  const [offset, setOffset] = useState(0);
  const query = { ...f, limit: 100, offset };
  const events = useQuery({ queryKey: ["audit", query], queryFn: () => api.audit(query) });
  const total = events.data?.total ?? 0;
  return (
    <Card title="Audit log">
      <div className="row" style={{ marginBottom: 12 }}>
        <Input placeholder="Entity type (e.g. deal, document)" value={f.entity_type} onChange={(e) => { setOffset(0); setF({ ...f, entity_type: e.target.value }); }} style={{ width: 220 }} />
        <Input placeholder="Action prefix (e.g. payment.)" value={f.action} onChange={(e) => { setOffset(0); setF({ ...f, action: e.target.value }); }} style={{ width: 220 }} />
        <Select value={f.actor_id} onChange={(e) => { setOffset(0); setF({ ...f, actor_id: e.target.value }); }} placeholder="Any user" style={{ width: 200 }}
          options={(users.data ?? []).map((u) => ({ value: u.id, label: u.display_name ?? u.email ?? u.id }))} />
      </div>
      <Table
        rows={events.data?.items}
        columns={[
          { key: "w", header: "When", render: (e) => <DateText value={e.occurred_at} time /> },
          { key: "u", header: "User", render: (e) => userName(users.data, e.actor_id) },
          { key: "a", header: "Action", render: (e) => <span className="mono small">{e.action}</span> },
          { key: "e", header: "Entity", render: (e) => <span className="small">{e.entity_type} {e.entity_id && <span className="muted mono">{e.entity_id.slice(0, 8)}</span>}</span> },
          { key: "d", header: "Details", render: (e) => <code className="small" style={{ whiteSpace: "pre-wrap", wordBreak: "break-all" }}>{JSON.stringify({ ...e.changes, ...e.metadata_ })}</code> },
        ]}
      />
      <div className="row" style={{ marginTop: 12, justifyContent: "flex-end" }}>
        <Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 100))}>Newer</Button>
        <span className="small muted">{total ? `${offset + 1}–${Math.min(offset + 100, total)} of ${total}` : "0"}</span>
        <Button size="sm" disabled={offset + 100 >= total} onClick={() => setOffset(offset + 100)}>Older</Button>
      </div>
    </Card>
  );
}

// ---- Tenants (system admin) ----

export function TenantsAdmin() {
  const tenants = useQuery({ queryKey: ["admin-tenants"], queryFn: api.admin.tenants });
  const [v, setV] = useState({ name: "", slug: "", admin_email: "" });
  const create = useAction(() => api.admin.createTenant({ name: v.name, slug: v.slug, admin_email: v.admin_email || undefined }), {
    invalidate: [["admin-tenants"]],
    success: "Tenant created",
    onSuccess: () => setV({ name: "", slug: "", admin_email: "" }),
  });
  return (
    <div className="stack">
      <Card title="Create tenant">
        <form className="row" onSubmit={(e) => { e.preventDefault(); create.mutate(undefined); }}>
          <Input required placeholder="Organisation name" value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} style={{ width: 240 }} />
          <Input required placeholder="slug" pattern="[a-z0-9][a-z0-9-]{1,78}" value={v.slug} onChange={(e) => setV({ ...v, slug: e.target.value })} style={{ width: 160 }} />
          <Input type="email" placeholder="First administrator email" value={v.admin_email} onChange={(e) => setV({ ...v, admin_email: e.target.value })} style={{ width: 260 }} />
          <Button variant="primary">Create</Button>
        </form>
      </Card>
      <Card title="Tenants">
        <Table
          rows={tenants.data}
          columns={[
            { key: "n", header: "Name", render: (t) => t.name },
            { key: "s", header: "Slug", render: (t) => <span className="mono">{t.slug}</span> },
            { key: "c", header: "Currency", render: (t) => t.default_currency },
            { key: "a", header: "Status", render: (t) => (t.is_active ? <Badge tone="success">active</Badge> : <Badge>inactive</Badge>) },
          ]}
        />
      </Card>
    </div>
  );
}
