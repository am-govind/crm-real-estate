import { P } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../lib/api";
import { Can } from "../lib/auth";
import { useUsers } from "./TasksPanel";
import { Button, Card, DateText, Field, Input, Modal, StatusBadge, Table, TextArea, useAction } from "./ui";

export function VisitForm({ link, onClose, onCreated }: { link: { property_id?: string; deal_id?: string }; onClose: () => void; onCreated?: (id: string) => void }) {
  const users = useUsers();
  const [v, setV] = useState({ title: "", purpose: "", start: "", end: "", meeting_point: "" });
  const [attendees, setAttendees] = useState<string[]>([]);
  const [owners, setOwners] = useState("");
  const save = useAction(
    () =>
      api.siteVisits.create({
        ...link,
        title: v.title,
        purpose: v.purpose || undefined,
        meeting_point: v.meeting_point || undefined,
        scheduled_start: new Date(v.start).toISOString(),
        scheduled_end: v.end ? new Date(v.end).toISOString() : undefined,
        attendees: [
          ...attendees.map((user_id) => ({ user_id, is_assigned: true, role: "field_agent" })),
          ...owners.split(",").map((s) => s.trim()).filter(Boolean).map((name) => ({ name, role: "external" })),
        ],
      }),
    {
      invalidate: [["site-visits"], ["control-center"]],
      success: "Visit scheduled",
      onSuccess: (visit) => {
        if (visit.conflicts.length) window.alert(`Scheduled, but overlaps with: ${visit.conflicts.map((c) => c.title).join(", ")}`);
        onCreated?.(visit.id);
        onClose();
      },
    },
  );
  return (
    <Modal title="Schedule site visit" onClose={onClose}>
      <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate(undefined); }}>
        <Field label="Title"><Input required value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} /></Field>
        <Field label="Purpose"><TextArea value={v.purpose} onChange={(e) => setV({ ...v, purpose: e.target.value })} /></Field>
        <div className="grid grid-2">
          <Field label="Start"><Input type="datetime-local" required value={v.start} onChange={(e) => setV({ ...v, start: e.target.value })} /></Field>
          <Field label="End"><Input type="datetime-local" value={v.end} onChange={(e) => setV({ ...v, end: e.target.value })} /></Field>
        </div>
        <Field label="Meeting point"><Input value={v.meeting_point} onChange={(e) => setV({ ...v, meeting_point: e.target.value })} /></Field>
        <Field label="Assigned team members">
          <select className="input" multiple value={attendees} onChange={(e) => setAttendees(Array.from(e.target.selectedOptions, (o) => o.value))} style={{ height: 100 }}>
            {(users.data ?? []).map((u) => <option key={u.id} value={u.id}>{u.display_name ?? u.email}</option>)}
          </select>
        </Field>
        <Field label="Other attendees" hint="Comma-separated names (owners, brokers, surveyors)"><Input value={owners} onChange={(e) => setOwners(e.target.value)} /></Field>
        <div className="row"><Button variant="primary" disabled={save.isPending}>Schedule</Button></div>
      </form>
    </Modal>
  );
}

export function VisitsPanel({ link, onOpen }: { link: { property_id?: string; deal_id?: string }; onOpen: (id: string) => void }) {
  const [creating, setCreating] = useState(false);
  const visits = useQuery({ queryKey: ["site-visits", link], queryFn: () => api.siteVisits.list({ ...link, limit: 100 }) });
  return (
    <Card title="Site visits" actions={<Can p={P.SITE_VISIT_WRITE}><Button variant="primary" onClick={() => setCreating(true)}>Schedule visit</Button></Can>}>
      <Table
        rows={visits.data?.items}
        empty="No site visits."
        onRowClick={(v) => onOpen(v.id)}
        columns={[
          { key: "t", header: "Visit", render: (v) => v.title },
          { key: "w", header: "Scheduled", render: (v) => <DateText value={v.scheduled_start} time /> },
          { key: "s", header: "Status", render: (v) => <StatusBadge status={v.status} /> },
          { key: "c", header: "Checked in", render: (v) => <DateText value={v.check_in_at} time /> },
          { key: "o", header: "Outcome", render: (v) => v.outcome ?? "" },
        ]}
      />
      {creating && <VisitForm link={link} onClose={() => setCreating(false)} />}
    </Card>
  );
}
