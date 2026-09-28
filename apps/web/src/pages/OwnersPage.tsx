import { P, type Owner } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import {
  Button,
  Card,
  clean,
  Field,
  Input,
  KV,
  Modal,
  PageHeader,
  Select,
  StatusBadge,
  Table,
  TextArea,
  useAction,
  useForm,
} from "../components/ui";
import { api } from "../lib/api";
import { Can } from "../lib/auth";

const OWNER_TYPES = ["individual", "organization", "trust", "huf", "government", "other"] as const;
const READINESS = ["unknown", "not_interested", "considering", "ready_to_sell"] as const;
const CONTACT_KINDS = ["phone", "email", "whatsapp", "address", "other"] as const;

export function OwnersPage() {
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const list = useQuery({ queryKey: ["owners", q], queryFn: () => api.owners.list({ q, limit: 100 }) });

  return (
    <div className="stack">
      <PageHeader
        title="Owners"
        actions={
          <>
            <Input placeholder="Search name, code, contact…" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 280 }} />
            <Can p={P.OWNER_WRITE}>
              <Button variant="primary" onClick={() => setCreating(true)}>
                New owner
              </Button>
            </Can>
          </>
        }
      />
      <Card>
        <Table
          rows={list.data?.items}
          onRowClick={(o) => setOpenId(o.id)}
          columns={[
            { key: "code", header: "Code", render: (o) => o.code },
            { key: "name", header: "Name", render: (o) => <div>{o.full_name}{o.local_name && <div className="muted small">{o.local_name}</div>}</div> },
            { key: "type", header: "Type", render: (o) => o.owner_type },
            { key: "ver", header: "Identity", render: (o) => <StatusBadge status={o.verification_status} /> },
            { key: "ready", header: "Readiness", render: (o) => <StatusBadge status={o.readiness} /> },
            { key: "contact", header: "Primary contact", render: (o) => (o.contacts.find((c) => c.is_primary) ?? o.contacts[0])?.value ?? "—" },
          ]}
        />
      </Card>
      {creating && <OwnerForm onClose={() => setCreating(false)} />}
      {openId && <OwnerDetail id={openId} onClose={() => setOpenId(null)} />}
    </div>
  );
}

export function OwnerForm({ owner, onClose, onCreated }: { owner?: Owner; onClose: () => void; onCreated?: (o: Owner) => void }) {
  const [v, set] = useForm({
    full_name: owner?.full_name ?? "",
    local_name: owner?.local_name ?? "",
    relation_name: owner?.relation_name ?? "",
    owner_type: owner?.owner_type ?? "individual",
    readiness: owner?.readiness ?? "unknown",
    date_of_birth: owner?.date_of_birth ?? "",
    notes: owner?.notes ?? "",
    phone: "",
  });
  const save = useAction(
    async () => {
      const { phone, ...rest } = v;
      if (owner) return api.owners.update(owner.id, clean(rest));
      return api.owners.create({ ...clean(rest), contacts: phone ? [{ kind: "phone", value: phone, is_primary: true }] : [] });
    },
    { invalidate: [["owners"]], success: owner ? "Owner updated" : "Owner created", onSuccess: (o) => { onCreated?.(o); onClose(); } },
  );
  return (
    <Modal title={owner ? "Edit owner" : "New owner"} onClose={onClose}>
      <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate(undefined); }}>
        <Field label="Full name"><Input required value={v.full_name} onChange={set("full_name")} /></Field>
        <div className="grid grid-2">
          <Field label="Name in local script"><Input value={v.local_name} onChange={set("local_name")} /></Field>
          <Field label="Father's / spouse's name"><Input value={v.relation_name} onChange={set("relation_name")} /></Field>
          <Field label="Owner type"><Select value={v.owner_type} onChange={set("owner_type")} options={OWNER_TYPES} /></Field>
          <Field label="Readiness to sell"><Select value={v.readiness} onChange={set("readiness")} options={READINESS} /></Field>
          <Field label="Date of birth"><Input type="date" value={v.date_of_birth} onChange={set("date_of_birth")} /></Field>
          {!owner && <Field label="Phone"><Input value={v.phone} onChange={set("phone")} /></Field>}
        </div>
        <Field label="Notes"><TextArea value={v.notes} onChange={set("notes")} /></Field>
        <div className="row"><Button variant="primary" disabled={save.isPending}>Save</Button></div>
      </form>
    </Modal>
  );
}

function OwnerDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const owner = useQuery({ queryKey: ["owners", "detail", id], queryFn: () => api.owners.get(id) });
  const props = useQuery({ queryKey: ["properties", "by-owner", id], queryFn: () => api.properties.list({ owner_id: id, limit: 100 }) });
  const [editing, setEditing] = useState(false);
  const [contact, setContact] = useForm({ kind: "phone", value: "", label: "" });
  const inv = [["owners"]];
  const verify = useAction((status: string) => api.owners.verify(id, status, window.prompt("Verification note (optional)") ?? undefined), { invalidate: inv });
  const addContact = useAction(() => api.owners.addContact(id, clean(contact)), { invalidate: inv });
  const removeContact = useAction((cid: string) => api.owners.removeContact(id, cid), { invalidate: inv });
  const o = owner.data;
  if (!o) return null;
  return (
    <Modal title={`${o.code} · ${o.full_name}`} onClose={onClose} wide>
      <div className="stack">
        <div className="row">
          <Can p={P.OWNER_WRITE}><Button onClick={() => setEditing(true)}>Edit</Button></Can>
          <Can p={P.OWNER_VERIFY}>
            <Button onClick={() => verify.mutate("verified")}>Mark identity verified</Button>
            <Button variant="danger" onClick={() => verify.mutate("rejected")}>Reject identity</Button>
          </Can>
        </div>
        <KV
          items={[
            ["Local name", o.local_name],
            ["Relation", o.relation_name],
            ["Type", o.owner_type],
            ["Identity verification", <StatusBadge status={o.verification_status} />],
            ["Verification note", o.verification_note],
            ["Readiness", <StatusBadge status={o.readiness} />],
            ["Notes", o.notes],
          ]}
        />
        <Card title="Contacts">
          <Table
            rows={o.contacts}
            empty="No contacts."
            columns={[
              { key: "k", header: "Kind", render: (c) => c.kind },
              { key: "v", header: "Value", render: (c) => c.value },
              { key: "l", header: "Label", render: (c) => c.label ?? "" },
              { key: "x", header: "", render: (c) => <Can p={P.OWNER_WRITE}><Button size="sm" variant="danger" onClick={() => removeContact.mutate(c.id)}>Remove</Button></Can> },
            ]}
          />
          <Can p={P.OWNER_WRITE}>
            <form className="row" style={{ marginTop: 8 }} onSubmit={(e) => { e.preventDefault(); addContact.mutate(undefined); }}>
              <Select value={contact.kind} onChange={setContact("kind")} options={CONTACT_KINDS} style={{ width: 120 }} />
              <Input required placeholder="Value" value={contact.value} onChange={setContact("value")} style={{ width: 220 }} />
              <Input placeholder="Label" value={contact.label} onChange={setContact("label")} style={{ width: 140 }} />
              <Button>Add contact</Button>
            </form>
          </Can>
        </Card>
        <Card title="Properties (current ownership)">
          <Table
            rows={props.data?.items}
            empty="Not linked to any property."
            columns={[
              { key: "c", header: "Code", render: (p) => <Link to={`/properties/${p.id}`}>{p.code}</Link> },
              { key: "n", header: "Name", render: (p) => p.name },
              { key: "s", header: "Status", render: (p) => <StatusBadge status={p.status} /> },
            ]}
          />
        </Card>
      </div>
      {editing && <OwnerForm owner={o} onClose={() => setEditing(false)} />}
    </Modal>
  );
}
