import { LAND_TYPES, type WorkflowActivation, type WorkflowTemplate } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Badge, Button, Card, DateText, Field, Input, Modal, Select, StatusBadge, Table, TextArea, useAction } from "../../components/ui";
import { api } from "../../lib/api";
import { useMe } from "../../lib/auth";

function LandTypePicker({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="row">
      {LAND_TYPES.map((t) => (
        <label key={t} className="row small">
          <input type="checkbox" checked={value.includes(t)} onChange={(e) => onChange(e.target.checked ? [...value, t] : value.filter((x) => x !== t))} />
          {t.replace(/_/g, " ")}
        </label>
      ))}
    </div>
  );
}

export function WorkflowAdmin() {
  const me = useMe();
  const templates = useQuery({ queryKey: ["workflow-templates"], queryFn: api.workflows.templates });
  const activations = useQuery({ queryKey: ["workflow-activations"], queryFn: api.workflows.activations });
  const [activating, setActivating] = useState(false);
  const [configuring, setConfiguring] = useState<WorkflowActivation | null>(null);
  const inv = [["workflow-activations"], ["pipeline"]];
  const toggle = useAction((a: WorkflowActivation) => api.workflows.updateActivation(a.id, { is_active: !a.is_active }), { invalidate: inv });
  const makeDefault = useAction((a: WorkflowActivation) => api.workflows.updateActivation(a.id, { is_default: true }), { invalidate: inv });
  const tName = (id: string) => templates.data?.find((t) => t.id === id)?.name ?? "Workflow";

  return (
    <div className="stack">
      <Card title="Active workflows" actions={<Button variant="primary" onClick={() => setActivating(true)}>Activate a workflow</Button>}>
        <div className="muted small" style={{ marginBottom: 8 }}>
          Workflows are published centrally and versioned. You can rename stages, change SLA targets and hide optional checklist items. Existing deals stay on the version they started with.
        </div>
        <Table
          rows={activations.data}
          empty="No workflow activated. Deals cannot be started until one is."
          columns={[
            { key: "n", header: "Workflow", render: (a) => <span>{tName(a.template_version.template_id)} v{a.template_version.version} {a.is_default && <Badge tone="info">default</Badge>}</span> },
            { key: "l", header: "Land types", render: (a) => (a.land_types.length ? a.land_types.join(", ") : "All") },
            { key: "s", header: "Stages", render: (a) => a.template_version.stages.length },
            { key: "st", header: "Status", render: (a) => (a.is_active ? <Badge tone="success">active</Badge> : <Badge>inactive</Badge>) },
            {
              key: "x",
              header: "",
              render: (a) => (
                <div className="row">
                  <Button size="sm" onClick={() => setConfiguring(a)}>Configure</Button>
                  {!a.is_default && a.is_active && <Button size="sm" onClick={() => makeDefault.mutate(a)}>Make default</Button>}
                  <Button size="sm" variant={a.is_active ? "danger" : "default"} onClick={() => toggle.mutate(a)}>{a.is_active ? "Deactivate" : "Reactivate"}</Button>
                </div>
              ),
            },
          ]}
        />
      </Card>
      {me.is_system_admin && <TemplateAuthoring templates={templates.data ?? []} />}
      {activating && <ActivateDialog templates={templates.data ?? []} onClose={() => setActivating(false)} />}
      {configuring && <ConfigureDialog activation={configuring} onClose={() => setConfiguring(null)} />}
    </div>
  );
}

function ActivateDialog({ templates, onClose }: { templates: WorkflowTemplate[]; onClose: () => void }) {
  const [versionId, setVersionId] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [landTypes, setLandTypes] = useState<string[]>([]);
  const options = templates.flatMap((t) => t.versions.filter((v) => v.status === "published").map((v) => ({ value: v.id, label: `${t.name} v${v.version}` })));
  const save = useAction(() => api.workflows.activate({ template_version_id: versionId, is_default: isDefault, land_types: landTypes, config: {} }), {
    invalidate: [["workflow-activations"]],
    success: "Workflow activated",
    onSuccess: onClose,
  });
  return (
    <Modal title="Activate workflow" onClose={onClose}>
      <div className="stack">
        <Field label="Published version"><Select value={versionId} onChange={(e) => setVersionId(e.target.value)} placeholder="Choose…" options={options} /></Field>
        <Field label="Use for land types" hint="Leave empty to allow all land types"><LandTypePicker value={landTypes} onChange={setLandTypes} /></Field>
        <label className="row"><input type="checkbox" checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} /> Make this the default workflow</label>
        <div className="row"><Button variant="primary" disabled={!versionId || save.isPending} onClick={() => save.mutate(undefined)}>Activate</Button></div>
      </div>
    </Modal>
  );
}

function ConfigureDialog({ activation, onClose }: { activation: WorkflowActivation; onClose: () => void }) {
  const cfg = activation.config;
  const [labels, setLabels] = useState<Record<string, string>>(cfg.stage_labels ?? {});
  const [slas, setSlas] = useState<Record<string, string>>(Object.fromEntries(Object.entries(cfg.sla_days ?? {}).map(([k, v]) => [k, String(v)])));
  const [hidden, setHidden] = useState<string[]>(cfg.hidden_optional_items ?? []);
  const [landTypes, setLandTypes] = useState<string[]>(activation.land_types);
  const save = useAction(
    () =>
      api.workflows.updateActivation(activation.id, {
        land_types: landTypes,
        config: {
          stage_labels: Object.fromEntries(Object.entries(labels).filter(([, v]) => v.trim())),
          sla_days: Object.fromEntries(Object.entries(slas).filter(([, v]) => v !== "").map(([k, v]) => [k, Number(v)])),
          hidden_optional_items: hidden,
        },
      }),
    { invalidate: [["workflow-activations"], ["pipeline"]], success: "Configuration saved", onSuccess: onClose },
  );
  return (
    <Modal title="Configure workflow" onClose={onClose} wide>
      <div className="stack">
        <Field label="Land types"><LandTypePicker value={landTypes} onChange={setLandTypes} /></Field>
        <Table
          rows={activation.template_version.stages}
          columns={[
            { key: "n", header: "Stage", render: (s) => <div>{s.name}<div className="muted small mono">{s.key}</div></div> },
            { key: "l", header: "Display label", render: (s) => <Input placeholder={s.name} value={labels[s.key] ?? ""} onChange={(e) => setLabels({ ...labels, [s.key]: e.target.value })} /> },
            { key: "sla", header: "SLA days", render: (s) => <Input type="number" min={0} placeholder={s.sla_days?.toString() ?? "—"} value={slas[s.key] ?? ""} onChange={(e) => setSlas({ ...slas, [s.key]: e.target.value })} style={{ width: 90 }} /> },
            {
              key: "c",
              header: "Optional checklist items (tick to hide)",
              render: (s) => {
                const optional = s.checklist.filter((c) => !c.is_required);
                if (!optional.length) return <span className="muted small">None optional</span>;
                return (
                  <div className="stack small">
                    {optional.map((c) => {
                      const ref = `${s.key}.${c.key}`;
                      return (
                        <label key={ref} className="row">
                          <input type="checkbox" checked={hidden.includes(ref)} onChange={(e) => setHidden(e.target.checked ? [...hidden, ref] : hidden.filter((h) => h !== ref))} />
                          {c.label}
                        </label>
                      );
                    })}
                  </div>
                );
              },
            },
          ]}
        />
        <div className="row"><Button variant="primary" disabled={save.isPending} onClick={() => save.mutate(undefined)}>Save</Button></div>
      </div>
    </Modal>
  );
}

const STAGE_EXAMPLE = JSON.stringify(
  [
    { key: "lead", name: "Lead", category: "lead", color: "#64748b", sla_days: 7, checklist: [{ key: "owner_contacted", label: "Owner contacted", is_required: true }] },
    { key: "closed", name: "Closed", category: "closing", is_terminal: true, is_skippable: false },
  ],
  null,
  2,
);

function TemplateAuthoring({ templates }: { templates: WorkflowTemplate[] }) {
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<{ templateId: string; versionId?: string; stages: string; notes: string } | null>(null);
  const [tpl, setTpl] = useState({ key: "", name: "", description: "" });
  const inv = [["workflow-templates"]];
  const createTemplate = useAction(() => api.workflows.admin.createTemplate({ ...tpl, description: tpl.description || undefined }), { invalidate: inv, success: "Template created", onSuccess: () => setCreating(false) });
  const saveDraft = useAction(
    () => {
      const body = { notes: draft!.notes || undefined, stages: JSON.parse(draft!.stages) };
      return draft!.versionId ? api.workflows.admin.updateDraft(draft!.versionId, body) : api.workflows.admin.createVersion(draft!.templateId, body);
    },
    { invalidate: inv, success: "Draft saved", onSuccess: () => setDraft(null) },
  );
  const publish = useAction(api.workflows.admin.publish, { invalidate: inv, success: "Published" });
  const retire = useAction(api.workflows.admin.retire, { invalidate: inv, success: "Retired" });

  async function openDraft(templateId: string, fromVersionId?: string, editVersionId?: string) {
    let stages = STAGE_EXAMPLE;
    const source = editVersionId ?? fromVersionId;
    if (source) {
      const v = await api.workflows.version(source);
      stages = JSON.stringify(
        v.stages.map((s) => ({
          key: s.key, name: s.name, description: s.description ?? undefined, category: s.category, color: s.color ?? undefined,
          is_terminal: s.is_terminal, is_skippable: s.is_skippable, sla_days: s.sla_days ?? undefined,
          checklist: s.checklist.map((c) => ({ key: c.key, label: c.label, is_required: c.is_required, document_class_key: c.document_class_key ?? undefined })),
        })),
        null,
        2,
      );
    }
    setDraft({ templateId, versionId: editVersionId, stages, notes: "" });
  }

  return (
    <Card title="Template publishing (system administrators)" actions={<Button onClick={() => setCreating(true)}>New template</Button>}>
      <div className="stack">
        {templates.map((t) => {
          const latestPublished = [...t.versions].filter((v) => v.status === "published").sort((a, b) => b.version - a.version)[0];
          return (
            <Card key={t.id} title={<span>{t.name} <span className="muted small mono">{t.key}</span></span>} actions={<Button size="sm" onClick={() => openDraft(t.id, latestPublished?.id)}>New version</Button>}>
              <Table
                rows={[...t.versions].sort((a, b) => b.version - a.version)}
                columns={[
                  { key: "v", header: "Version", render: (v) => `v${v.version}` },
                  { key: "s", header: "Status", render: (v) => <StatusBadge status={v.status} /> },
                  { key: "p", header: "Published", render: (v) => <DateText value={v.published_at} /> },
                  {
                    key: "x",
                    header: "",
                    render: (v) => (
                      <div className="row">
                        {v.status === "draft" && <Button size="sm" onClick={() => openDraft(t.id, undefined, v.id)}>Edit</Button>}
                        {v.status === "draft" && <Button size="sm" variant="primary" onClick={() => publish.mutate(v.id)}>Publish</Button>}
                        {v.status === "published" && <Button size="sm" variant="danger" onClick={() => retire.mutate(v.id)}>Retire</Button>}
                      </div>
                    ),
                  },
                ]}
              />
            </Card>
          );
        })}
      </div>
      {creating && (
        <Modal title="New workflow template" onClose={() => setCreating(false)}>
          <div className="stack">
            <Field label="Key"><Input value={tpl.key} onChange={(e) => setTpl({ ...tpl, key: e.target.value })} placeholder="e.g. agricultural_purchase" /></Field>
            <Field label="Name"><Input value={tpl.name} onChange={(e) => setTpl({ ...tpl, name: e.target.value })} /></Field>
            <Field label="Description"><TextArea value={tpl.description} onChange={(e) => setTpl({ ...tpl, description: e.target.value })} /></Field>
            <div className="row"><Button variant="primary" disabled={!tpl.key || !tpl.name} onClick={() => createTemplate.mutate(undefined)}>Create</Button></div>
          </div>
        </Modal>
      )}
      {draft && (
        <Modal title={draft.versionId ? "Edit draft version" : "New draft version"} onClose={() => setDraft(null)} wide>
          <div className="stack">
            <div className="muted small">Stages in order, as JSON. Published versions are immutable; publishing creates the next version number.</div>
            <TextArea rows={20} className="mono" value={draft.stages} onChange={(e) => setDraft({ ...draft, stages: e.target.value })} />
            <Field label="Release notes"><Input value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} /></Field>
            <div className="row"><Button variant="primary" disabled={saveDraft.isPending} onClick={() => saveDraft.mutate(undefined)}>Save draft</Button></div>
          </div>
        </Modal>
      )}
    </Card>
  );
}
