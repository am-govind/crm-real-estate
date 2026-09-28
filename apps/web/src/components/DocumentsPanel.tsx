import { P, type CrmDocument } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../lib/api";
import { Can, useCan, useMe } from "../lib/auth";
import {
  askReason,
  Badge,
  Button,
  Card,
  DateText,
  Field,
  Input,
  KV,
  Modal,
  Select,
  StatusBadge,
  Table,
  TextArea,
  useAction,
} from "./ui";

type Scope = { property_id: string; deal_id?: undefined } | { deal_id: string; property_id?: undefined };

export function DocumentsPanel({ scope, landType }: { scope: Scope; landType?: string }) {
  const [uploading, setUploading] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const docs = useQuery({ queryKey: ["documents", scope], queryFn: () => api.documents.list({ ...scope, limit: 500 }) });
  const completeness = useQuery({ queryKey: ["documents", "completeness", scope], queryFn: () => api.documents.completeness(scope) });
  const c = completeness.data;

  return (
    <div className="stack">
      {c && c.required > 0 && (
        <Card title={`Required documents: ${c.label}`}>
          <div className="progress" style={{ marginBottom: 8 }}>
            <div style={{ width: `${c.percent}%` }} />
          </div>
          <div className="row">
            {c.items.map((i) => (
              <span key={i.class_key} title={i.has_expired ? "Expired" : undefined}>
                <StatusBadge status={i.status} /> {i.class_name}
                {i.has_expired && <Badge tone="danger">expired</Badge>}
              </span>
            ))}
          </div>
        </Card>
      )}
      <Card title="Documents" actions={<Can p={P.DOCUMENT_UPLOAD}><Button variant="primary" onClick={() => setUploading(true)}>Upload</Button></Can>}>
        <Table
          rows={docs.data?.items}
          empty="No documents uploaded."
          onRowClick={(d) => !d.is_redacted && setOpenId(d.id)}
          columns={[
            { key: "class", header: "Type", render: (d) => <div>{d.class_name}<div className="muted small">{d.category}</div></div> },
            { key: "title", header: "Title", render: (d) => (d.is_redacted ? <span className="muted">Restricted — request access</span> : d.title) },
            { key: "access", header: "Access", render: (d) => (d.is_sensitive ? <Badge tone="warning">{d.access_policy}</Badge> : d.access_policy) },
            { key: "v", header: "Version", render: (d) => `v${d.current_version_no}` },
            { key: "exp", header: "Expiry", render: (d) => <DateText value={d.expiry_date} /> },
            { key: "rev", header: "Review", render: (d) => <StatusBadge status={d.review_status} /> },
          ]}
        />
      </Card>
      {uploading && <UploadDocument scope={scope} landType={landType} onClose={() => setUploading(false)} />}
      {openId && <DocumentDetail id={openId} onClose={() => setOpenId(null)} />}
    </div>
  );
}

function UploadDocument({ scope, onClose, existing }: { scope?: Scope; landType?: string; onClose: () => void; existing?: CrmDocument }) {
  const allowed = useCan();
  const classes = useQuery({ queryKey: ["document-classes"], queryFn: api.documents.classes, enabled: !existing });
  const [file, setFile] = useState<File | null>(null);
  const [v, setV] = useState({ class_key: "", title: "", access_policy: "", expiry_date: "", reference_number: "", issued_on: "", description: "", note: "" });
  const target = scope?.deal_id ? "deal" : "property";
  const options = (classes.data ?? []).filter((c) => c.applies_to.includes(target) && (!c.is_sensitive || allowed(P.DOCUMENT_SENSITIVE_UPLOAD)));
  const cls = options.find((c) => c.key === v.class_key);

  const save = useAction(
    async () => {
      const form = new FormData();
      form.append("file", file!);
      if (existing) {
        if (v.note) form.append("note", v.note);
        return api.documents.addVersion(existing.id, form);
      }
      const fields: Record<string, string | undefined> = { ...v, ...scope };
      delete fields.note;
      for (const [k, val] of Object.entries(fields)) if (val) form.append(k, val);
      return api.documents.upload(form);
    },
    { invalidate: [["documents"], ["control-center"]], success: "Uploaded", onSuccess: onClose },
  );

  return (
    <Modal title={existing ? `New version of ${existing.title}` : "Upload document"} onClose={onClose}>
      <form className="stack" onSubmit={(e) => { e.preventDefault(); if (file) save.mutate(undefined); }}>
        {!existing && (
          <>
            <Field label="Document type">
              <Select required value={v.class_key} onChange={(e) => setV({ ...v, class_key: e.target.value })} placeholder="Choose…" options={options.map((c) => ({ value: c.key, label: `${c.name}${c.is_sensitive ? " (sensitive)" : ""}` }))} />
            </Field>
            <Field label="Title"><Input required value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} /></Field>
            <div className="grid grid-2">
              <Field label="Access" hint={cls ? `Default: ${cls.default_access_policy}` : undefined}>
                <Select value={v.access_policy} onChange={(e) => setV({ ...v, access_policy: e.target.value })} placeholder="Class default" options={["standard", "restricted", "confidential"]} />
              </Field>
              <Field label={cls?.requires_expiry ? "Expiry date (required)" : "Expiry date"}>
                <Input type="date" required={cls?.requires_expiry} value={v.expiry_date} onChange={(e) => setV({ ...v, expiry_date: e.target.value })} />
              </Field>
              <Field label="Reference number"><Input value={v.reference_number} onChange={(e) => setV({ ...v, reference_number: e.target.value })} /></Field>
              <Field label="Issued on"><Input type="date" value={v.issued_on} onChange={(e) => setV({ ...v, issued_on: e.target.value })} /></Field>
            </div>
            <Field label="Description"><TextArea value={v.description} onChange={(e) => setV({ ...v, description: e.target.value })} /></Field>
          </>
        )}
        {existing && <Field label="Version note"><Input value={v.note} onChange={(e) => setV({ ...v, note: e.target.value })} /></Field>}
        <Field label="File"><input type="file" required onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
        <div className="row"><Button variant="primary" disabled={!file || save.isPending}>Upload</Button></div>
      </form>
    </Modal>
  );
}

export function DocumentDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const me = useMe();
  const allowed = useCan();
  const [newVersion, setNewVersion] = useState(false);
  const doc = useQuery({ queryKey: ["documents", "detail", id], queryFn: () => api.documents.get(id) });
  const reviews = useQuery({ queryKey: ["documents", "reviews", id], queryFn: () => api.documents.reviews(id) });
  const grants = useQuery({ queryKey: ["documents", "grants", id], queryFn: () => api.documents.grants(id), enabled: allowed(P.DOCUMENT_GRANT) });
  const users = useQuery({ queryKey: ["tenant-users"], queryFn: api.tenant.users, enabled: allowed(P.DOCUMENT_GRANT) });
  const [grantUser, setGrantUser] = useState("");
  const inv = [["documents"], ["control-center"]];
  const review = useAction((decision: string) => {
    const note = decision === "approved" ? window.prompt("Review note (optional)") ?? undefined : askReason("Explain what is wrong");
    if (note === null) return Promise.resolve(null);
    return api.documents.review(id, decision, note);
  }, { invalidate: inv });
  const grant = useAction(() => {
    const reason = askReason("Why does this person need access?");
    return reason ? api.documents.grant(id, { user_id: grantUser, reason }) : Promise.resolve(null);
  }, { invalidate: inv });
  const revoke = useAction((userId: string) => api.documents.revoke(id, userId), { invalidate: inv });
  const d = doc.data;
  if (!d) return null;
  const latest = d.versions.find((x) => x.version_no === d.current_version_no);
  const canReview = allowed(P.DOCUMENT_REVIEW) && latest?.uploaded_by_id !== me.id;

  return (
    <Modal title={d.title ?? d.class_name} onClose={onClose} wide>
      <div className="stack">
        <div className="row">
          {latest && <a className="btn" href={api.documents.downloadUrl(d.id, latest.version_no)} target="_blank" rel="noreferrer">Download latest</a>}
          <Can p={P.DOCUMENT_UPLOAD}><Button onClick={() => setNewVersion(true)}>Upload new version</Button></Can>
          {canReview && d.review_status !== "approved" && (
            <>
              <Button variant="primary" onClick={() => review.mutate("approved")}>Approve</Button>
              <Button onClick={() => review.mutate("needs_changes")}>Needs changes</Button>
              <Button variant="danger" onClick={() => review.mutate("rejected")}>Reject</Button>
            </>
          )}
          {allowed(P.DOCUMENT_REVIEW) && !canReview && <span className="muted small">You uploaded the current version, so another reviewer must review it.</span>}
        </div>
        <KV
          items={[
            ["Type", `${d.class_name} (${d.category})`],
            ["Access", d.access_policy],
            ["Review", <StatusBadge status={d.review_status} />],
            ["Review note", d.review_note],
            ["Reference", d.reference_number],
            ["Issued on", <DateText value={d.issued_on} />],
            ["Expiry", <DateText value={d.expiry_date} />],
            ["Description", d.description],
          ]}
        />
        <Card title="Versions">
          <Table
            rows={[...d.versions].sort((a, b) => b.version_no - a.version_no)}
            columns={[
              { key: "v", header: "Version", render: (x) => `v${x.version_no}` },
              { key: "f", header: "File", render: (x) => <a href={api.documents.downloadUrl(d.id, x.version_no)} target="_blank" rel="noreferrer">{x.filename}</a> },
              { key: "s", header: "Size", render: (x) => `${Math.ceil(x.size_bytes / 1024)} KB` },
              { key: "h", header: "SHA-256", render: (x) => <span className="mono small" title={x.sha256}>{x.sha256.slice(0, 12)}…</span> },
              { key: "n", header: "Note", render: (x) => x.note ?? "" },
              { key: "u", header: "Uploaded", render: (x) => <DateText value={x.uploaded_at} time /> },
            ]}
          />
        </Card>
        <Card title="Review history">
          <Table
            rows={reviews.data}
            empty="Not reviewed yet."
            columns={[
              { key: "d", header: "Decision", render: (r) => <StatusBadge status={r.decision} /> },
              { key: "n", header: "Note", render: (r) => r.note ?? "" },
              { key: "w", header: "When", render: (r) => <DateText value={r.reviewed_at} time /> },
            ]}
          />
        </Card>
        {allowed(P.DOCUMENT_GRANT) && d.access_policy !== "standard" && (
          <Card title="Access grants">
            <Table
              rows={grants.data?.filter((g) => !g.revoked_at)}
              empty="No individual grants."
              columns={[
                { key: "u", header: "User", render: (g) => users.data?.find((u) => u.id === g.user_id)?.display_name ?? g.user_id },
                { key: "r", header: "Reason", render: (g) => g.reason },
                { key: "e", header: "Expires", render: (g) => <DateText value={g.expires_at} /> },
                { key: "x", header: "", render: (g) => <Button size="sm" variant="danger" onClick={() => revoke.mutate(g.user_id)}>Revoke</Button> },
              ]}
            />
            <div className="row" style={{ marginTop: 8 }}>
              <Select value={grantUser} onChange={(e) => setGrantUser(e.target.value)} placeholder="Choose user…" options={(users.data ?? []).map((u) => ({ value: u.id, label: u.display_name ?? u.email ?? u.id }))} style={{ width: 240 }} />
              <Button disabled={!grantUser} onClick={() => grant.mutate(undefined)}>Grant access</Button>
            </div>
          </Card>
        )}
      </div>
      {newVersion && <UploadDocument existing={d} onClose={() => setNewVersion(false)} />}
    </Modal>
  );
}
