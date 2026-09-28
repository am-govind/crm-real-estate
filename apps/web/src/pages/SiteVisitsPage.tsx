import { P } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { TasksPanel, userName, useUsers } from "../components/TasksPanel";
import { VisitForm } from "../components/VisitsPanel";
import {
  Button,
  Card,
  DateText,
  Input,
  KV,
  Modal,
  PageHeader,
  Select,
  StatusBadge,
  Table,
  TextArea,
  useAction,
  useToast,
} from "../components/ui";
import { api } from "../lib/api";
import { Can, useCan } from "../lib/auth";

const VISIT_STATUSES = ["scheduled", "in_progress", "completed", "cancelled", "missed"] as const;

export function SiteVisitsPage() {
  const [status, setStatus] = useState("");
  const [mine, setMine] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [newFor, setNewFor] = useState<string | null>(null);
  const props = useQuery({ queryKey: ["properties", "picker"], queryFn: () => api.properties.list({ limit: 500 }), enabled: newFor !== null });
  const visits = useQuery({
    queryKey: ["site-visits", "list", status, mine],
    queryFn: () => api.siteVisits.list({ status: status ? [status] : undefined, mine: mine || undefined, limit: 200 }),
  });

  return (
    <div className="stack">
      <PageHeader
        title="Site visits"
        actions={
          <>
            <Select value={status} onChange={(e) => setStatus(e.target.value)} options={VISIT_STATUSES} placeholder="Any status" />
            <label className="row small"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> Mine</label>
            <Can p={P.SITE_VISIT_WRITE}><Button variant="primary" onClick={() => setNewFor("")}>Schedule visit</Button></Can>
          </>
        }
      />
      <Card>
        <Table
          rows={visits.data?.items}
          onRowClick={(v) => setOpenId(v.id)}
          columns={[
            { key: "t", header: "Visit", render: (v) => v.title },
            { key: "w", header: "Scheduled", render: (v) => <DateText value={v.scheduled_start} time /> },
            { key: "s", header: "Status", render: (v) => <StatusBadge status={v.status} /> },
            { key: "a", header: "Attendees", render: (v) => v.attendees.length },
            { key: "o", header: "Outcome", render: (v) => v.outcome ?? "" },
          ]}
        />
      </Card>
      {newFor === "" && (
        <Modal title="Choose property" onClose={() => setNewFor(null)}>
          <Select
            placeholder="Choose property…"
            value=""
            onChange={(e) => setNewFor(e.target.value)}
            options={(props.data?.items ?? []).map((p) => ({ value: p.id, label: `${p.code} · ${p.name}` }))}
          />
        </Modal>
      )}
      {newFor && <VisitForm link={{ property_id: newFor }} onClose={() => setNewFor(null)} onCreated={setOpenId} />}
      {openId && <VisitDetailModal id={openId} onClose={() => setOpenId(null)} />}
    </div>
  );
}

function currentPosition(): Promise<{ latitude: number; longitude: number; accuracy_m: number }> {
  return new Promise((resolve, reject) =>
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ latitude: p.coords.latitude, longitude: p.coords.longitude, accuracy_m: p.coords.accuracy }),
      (e) => reject(new Error(`Location unavailable: ${e.message}`)),
      { enableHighAccuracy: true, timeout: 15_000 },
    ),
  );
}

export function VisitDetailModal({ id, onClose }: { id: string; onClose: () => void }) {
  const allowed = useCan();
  const toast = useToast();
  const users = useUsers();
  const visit = useQuery({ queryKey: ["site-visits", "detail", id], queryFn: () => api.siteVisits.get(id) });
  const [note, setNote] = useState("");
  const [caption, setCaption] = useState("");
  const inv = [["site-visits"], ["control-center"]];
  const checkIn = useAction(async () => api.siteVisits.checkIn(id, { ...(await currentPosition()), recorded_at: new Date().toISOString() }), { invalidate: inv, success: "Checked in" });
  const checkOut = useAction(async () => {
    const outcome = window.prompt("Visit outcome") ?? undefined;
    return api.siteVisits.checkOut(id, { ...(await currentPosition()), recorded_at: new Date().toISOString(), outcome });
  }, { invalidate: inv, success: "Checked out" });
  const addNote = useAction(async () => {
    const pos = await currentPosition().catch(() => null);
    return api.siteVisits.addNote(id, { body: note, latitude: pos?.latitude, longitude: pos?.longitude, recorded_at: new Date().toISOString() });
  }, { invalidate: inv, onSuccess: () => setNote("") });
  const upload = useAction(async (file: File) => {
    const pos = await currentPosition().catch(() => null);
    const form = new FormData();
    form.append("file", file);
    if (caption) form.append("caption", caption);
    if (pos) {
      form.append("latitude", String(pos.latitude));
      form.append("longitude", String(pos.longitude));
    }
    form.append("captured_at", new Date(file.lastModified).toISOString());
    return api.siteVisits.uploadMedia(id, form);
  }, { invalidate: inv, onSuccess: () => setCaption("") });
  const cancel = useAction(() => api.siteVisits.update(id, { status: "cancelled" }), { invalidate: inv });

  const v = visit.data;
  if (!v) return null;
  const canWrite = allowed(P.SITE_VISIT_WRITE);
  return (
    <Modal title={v.title} onClose={onClose} wide>
      <div className="stack">
        {v.conflicts.length > 0 && (
          <div className="warn">Overlaps with: {v.conflicts.map((c) => `${c.title} (${new Date(c.scheduled_start).toLocaleString("en-IN")})`).join(", ")}</div>
        )}
        {canWrite && (
          <div className="row">
            {v.status === "scheduled" && <Button variant="primary" onClick={() => checkIn.mutate(undefined)}>Check in here</Button>}
            {v.status === "in_progress" && <Button variant="primary" onClick={() => checkOut.mutate(undefined)}>Check out</Button>}
            {v.status === "scheduled" && <Button variant="danger" onClick={() => cancel.mutate(undefined)}>Cancel visit</Button>}
          </div>
        )}
        <KV
          items={[
            ["Status", <StatusBadge status={v.status} />],
            ["Property", v.property_id ? <Link to={`/properties/${v.property_id}`} onClick={onClose}>Open property</Link> : "—"],
            ["Deal", v.deal_id ? <Link to={`/deals/${v.deal_id}`} onClick={onClose}>Open deal</Link> : "—"],
            ["Scheduled", <span><DateText value={v.scheduled_start} time /> {v.scheduled_end && <>– <DateText value={v.scheduled_end} time /></>}</span>],
            ["Purpose", v.purpose],
            ["Meeting point", v.meeting_point],
            ["Check-in", v.check_in_at ? `${new Date(v.check_in_at).toLocaleString("en-IN")} at ${v.check_in_lat?.toFixed(5)}, ${v.check_in_lng?.toFixed(5)} (±${Math.round(v.check_in_accuracy_m ?? 0)} m)` : "—"],
            ["Check-out", v.check_out_at ? `${new Date(v.check_out_at).toLocaleString("en-IN")} at ${v.check_out_lat?.toFixed(5)}, ${v.check_out_lng?.toFixed(5)}` : "—"],
            ["Outcome", v.outcome],
            ["Attendees", v.attendees.map((a) => (a.user_id ? userName(users.data, a.user_id) : a.name) + ` (${a.role})`).join(", ") || "—"],
          ]}
        />
        <Card title="Notes">
          <div className="stack">
            {v.notes.map((n) => (
              <div key={n.id}>
                <div className="muted small">{userName(users.data, n.author_id)} · <DateText value={n.recorded_at} time /></div>
                <div>{n.body}</div>
              </div>
            ))}
            {v.notes.length === 0 && <span className="muted">No notes yet.</span>}
            {canWrite && (
              <form className="stack" onSubmit={(e) => { e.preventDefault(); if (note.trim()) addNote.mutate(undefined); }}>
                <TextArea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add a field note…" />
                <div className="row"><Button>Add note</Button></div>
              </form>
            )}
          </div>
        </Card>
        <Card title="Photos and media">
          <div className="row">
            {v.media.map((m) => (
              <a key={m.id} href={api.siteVisits.mediaUrl(v.id, m.id)} target="_blank" rel="noreferrer" title={m.caption ?? m.filename}>
                {m.kind === "photo" ? <img src={api.siteVisits.mediaUrl(v.id, m.id)} alt={m.caption ?? ""} style={{ width: 120, height: 90, objectFit: "cover", borderRadius: 6 }} /> : m.filename}
              </a>
            ))}
            {v.media.length === 0 && <span className="muted">No media.</span>}
          </div>
          {canWrite && (
            <div className="row" style={{ marginTop: 8 }}>
              <Input placeholder="Caption" value={caption} onChange={(e) => setCaption(e.target.value)} style={{ width: 240 }} />
              <input
                type="file"
                accept="image/*,video/*,audio/*"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) upload.mutate(f);
                  else toast("error", "No file chosen");
                  e.target.value = "";
                }}
              />
            </div>
          )}
        </Card>
        <TasksPanel link={{ site_visit_id: v.id }} />
      </div>
    </Modal>
  );
}
