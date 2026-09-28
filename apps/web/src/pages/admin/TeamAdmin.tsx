import { humanize } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Badge, Button, Card, DateText, Field, Input, Modal, Table, TextArea, useAction } from "../../components/ui";
import { api } from "../../lib/api";

function useRoles() {
  return useQuery({ queryKey: ["roles"], queryFn: api.tenant.roles });
}

function RolePicker({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const roles = useRoles();
  return (
    <div className="row">
      {(roles.data ?? []).map((r) => (
        <label key={r.key} className="row small" title={r.description ?? undefined}>
          <input type="checkbox" checked={value.includes(r.key)} onChange={(e) => onChange(e.target.checked ? [...value, r.key] : value.filter((k) => k !== r.key))} />
          {r.name}
        </label>
      ))}
    </div>
  );
}

export function MembersAdmin() {
  const members = useQuery({ queryKey: ["members"], queryFn: api.tenant.members });
  const [editing, setEditing] = useState<{ id: string; role_keys: string[]; title: string; name: string } | null>(null);
  const toggle = useAction(({ id, is_active }: { id: string; is_active: boolean }) => api.tenant.updateMember(id, { is_active }), { invalidate: [["members"], ["tenant-users"]] });
  const save = useAction(() => api.tenant.updateMember(editing!.id, { role_keys: editing!.role_keys, title: editing!.title || null }), {
    invalidate: [["members"]],
    success: "Member updated",
    onSuccess: () => setEditing(null),
  });
  return (
    <Card title="Members">
      <Table
        rows={members.data}
        columns={[
          { key: "n", header: "Name", render: (m) => <div>{m.user.display_name ?? "—"}<div className="muted small">{m.user.email}</div></div> },
          { key: "t", header: "Title", render: (m) => m.title ?? "" },
          { key: "r", header: "Roles", render: (m) => <div className="row">{m.role_keys.map((k) => <Badge key={k}>{humanize(k)}</Badge>)}</div> },
          { key: "s", header: "Status", render: (m) => (m.is_active ? <Badge tone="success">active</Badge> : <Badge tone="danger">deactivated</Badge>) },
          {
            key: "x",
            header: "",
            render: (m) => (
              <div className="row">
                <Button size="sm" onClick={() => setEditing({ id: m.membership_id, role_keys: m.role_keys, title: m.title ?? "", name: m.user.display_name ?? m.user.email ?? "" })}>Edit</Button>
                <Button size="sm" variant={m.is_active ? "danger" : "default"} onClick={() => toggle.mutate({ id: m.membership_id, is_active: !m.is_active })}>{m.is_active ? "Deactivate" : "Reactivate"}</Button>
              </div>
            ),
          },
        ]}
      />
      {editing && (
        <Modal title={`Edit ${editing.name}`} onClose={() => setEditing(null)}>
          <div className="stack">
            <Field label="Title"><Input value={editing.title} onChange={(e) => setEditing({ ...editing, title: e.target.value })} /></Field>
            <Field label="Roles"><RolePicker value={editing.role_keys} onChange={(role_keys) => setEditing({ ...editing, role_keys })} /></Field>
            <div className="row"><Button variant="primary" disabled={!editing.role_keys.length} onClick={() => save.mutate(undefined)}>Save</Button></div>
          </div>
        </Modal>
      )}
    </Card>
  );
}

export function InvitationsAdmin() {
  const invitations = useQuery({ queryKey: ["invitations"], queryFn: api.tenant.invitations });
  const [email, setEmail] = useState("");
  const [roles, setRoles] = useState<string[]>([]);
  const invite = useAction(() => api.tenant.invite(email, roles), { invalidate: [["invitations"]], success: "Invitation created", onSuccess: () => { setEmail(""); setRoles([]); } });
  return (
    <div className="stack">
      <Card title="Invite someone">
        <form className="stack" onSubmit={(e) => { e.preventDefault(); invite.mutate(undefined); }}>
          <Field label="Email" hint="They join automatically the first time they sign in with this verified email."><Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <Field label="Roles"><RolePicker value={roles} onChange={setRoles} /></Field>
          <div className="row"><Button variant="primary" disabled={!roles.length || invite.isPending}>Invite</Button></div>
        </form>
      </Card>
      <Card title="Invitations">
        <Table
          rows={invitations.data}
          empty="No invitations."
          columns={[
            { key: "e", header: "Email", render: (i) => i.email },
            { key: "r", header: "Roles", render: (i) => i.role_keys.map(humanize).join(", ") },
            { key: "c", header: "Invited", render: (i) => <DateText value={i.created_at} /> },
            { key: "a", header: "Accepted", render: (i) => (i.accepted_at ? <DateText value={i.accepted_at} /> : <Badge tone="warning">pending</Badge>) },
          ]}
        />
      </Card>
    </div>
  );
}

export function RolesAdmin() {
  const roles = useRoles();
  const permissions = useQuery({ queryKey: ["all-permissions"], queryFn: api.permissions });
  const [editing, setEditing] = useState<{ id?: string; key: string; name: string; description: string; permissions: string[]; builtin: boolean } | null>(null);
  const save = useAction(
    () => {
      const body = { key: editing!.key, name: editing!.name, description: editing!.description || null, permissions: editing!.permissions };
      return editing!.id ? api.tenant.updateRole(editing!.id, body) : api.tenant.createRole(body);
    },
    { invalidate: [["roles"], ["me"]], success: "Role saved", onSuccess: () => setEditing(null) },
  );
  const groups = new Map<string, string[]>();
  for (const p of permissions.data ?? []) {
    const g = p.split(".")[0]!;
    groups.set(g, [...(groups.get(g) ?? []), p]);
  }
  return (
    <Card title="Roles" actions={<Button variant="primary" onClick={() => setEditing({ key: "", name: "", description: "", permissions: [], builtin: false })}>New role</Button>}>
      <Table
        rows={roles.data}
        onRowClick={(r) => setEditing({ id: r.id, key: r.key, name: r.name, description: r.description ?? "", permissions: r.permissions, builtin: r.is_builtin })}
        columns={[
          { key: "n", header: "Role", render: (r) => <div>{r.name} {r.is_builtin && <Badge>built-in</Badge>}<div className="muted small">{r.description}</div></div> },
          { key: "k", header: "Key", render: (r) => <span className="mono small">{r.key}</span> },
          { key: "p", header: "Permissions", render: (r) => r.permissions.length },
        ]}
      />
      {editing && (
        <Modal title={editing.id ? `Edit ${editing.name}` : "New role"} onClose={() => setEditing(null)} wide>
          <div className="stack">
            <div className="grid grid-2">
              <Field label="Key"><Input disabled={!!editing.id} value={editing.key} onChange={(e) => setEditing({ ...editing, key: e.target.value })} placeholder="e.g. field_agent" /></Field>
              <Field label="Name"><Input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} /></Field>
            </div>
            <Field label="Description"><TextArea value={editing.description} onChange={(e) => setEditing({ ...editing, description: e.target.value })} /></Field>
            <div className="grid grid-3">
              {[...groups.entries()].map(([g, perms]) => (
                <Card key={g} title={humanize(g)}>
                  {perms.map((p) => (
                    <label key={p} className="row small">
                      <input type="checkbox" checked={editing.permissions.includes(p)} onChange={(e) => setEditing({ ...editing, permissions: e.target.checked ? [...editing.permissions, p] : editing.permissions.filter((x) => x !== p) })} />
                      <span className="mono">{p}</span>
                    </label>
                  ))}
                </Card>
              ))}
            </div>
            <div className="row"><Button variant="primary" disabled={!editing.key || !editing.name || save.isPending} onClick={() => save.mutate(undefined)}>Save</Button></div>
          </div>
        </Modal>
      )}
    </Card>
  );
}
