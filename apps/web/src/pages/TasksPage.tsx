import { P, TASK_STATUSES, type Task } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { TaskForm, taskColumns, useUsers } from "../components/TasksPanel";
import { Button, Card, PageHeader, Select, Table, useAction } from "../components/ui";
import { api } from "../lib/api";
import { Can, useCan } from "../lib/auth";

export function TasksPage() {
  const allowed = useCan();
  const users = useUsers();
  const [f, setF] = useState({ status: "open", mine: true, overdue: false, assignee_id: "" });
  const [editing, setEditing] = useState<Task | "new" | null>(null);
  const query = {
    status: f.status ? [f.status] : undefined,
    mine: f.mine || undefined,
    overdue: f.overdue || undefined,
    assignee_id: !f.mine ? f.assignee_id : undefined,
    limit: 200,
  };
  const tasks = useQuery({ queryKey: ["tasks", "page", query], queryFn: () => api.tasks.list(query) });
  const done = useAction((t: Task) => api.tasks.update(t.id, { status: "done" }), { invalidate: [["tasks"]] });

  return (
    <div className="stack">
      <PageHeader title="Tasks" actions={<Can p={P.TASK_WRITE}><Button variant="primary" onClick={() => setEditing("new")}>New task</Button></Can>} />
      <Card>
        <div className="row" style={{ marginBottom: 12 }}>
          <Select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })} options={TASK_STATUSES} placeholder="Any status" style={{ width: 150 }} />
          <label className="row small"><input type="checkbox" checked={f.mine} onChange={(e) => setF({ ...f, mine: e.target.checked })} /> Assigned to me</label>
          {!f.mine && (
            <Select value={f.assignee_id} onChange={(e) => setF({ ...f, assignee_id: e.target.value })} placeholder="Any assignee" style={{ width: 200 }}
              options={(users.data ?? []).map((u) => ({ value: u.id, label: u.display_name ?? u.email ?? u.id }))} />
          )}
          <label className="row small"><input type="checkbox" checked={f.overdue} onChange={(e) => setF({ ...f, overdue: e.target.checked })} /> Overdue only</label>
        </div>
        <Table
          rows={tasks.data?.items}
          empty="No tasks match."
          onRowClick={allowed(P.TASK_WRITE) ? (t) => setEditing(t) : undefined}
          columns={[
            ...taskColumns(users.data, allowed(P.TASK_WRITE) ? (t) => done.mutate(t) : undefined),
            {
              key: "link",
              header: "Linked to",
              render: (t) =>
                t.deal_id ? <Link to={`/deals/${t.deal_id}`} onClick={(e) => e.stopPropagation()}>Deal</Link>
                : t.property_id ? <Link to={`/properties/${t.property_id}`} onClick={(e) => e.stopPropagation()}>Property</Link>
                : "—",
            },
          ]}
        />
      </Card>
      {editing && <TaskForm task={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}
