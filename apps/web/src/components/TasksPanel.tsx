import { P, PRIORITIES, TASK_STATUSES, type Task } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../lib/api";
import { Can, useCan } from "../lib/auth";
import { Button, Card, clean, DateText, Field, Input, Modal, Select, StatusBadge, Table, TextArea, useAction, useForm, type Column } from "./ui";

export function useUsers() {
  return useQuery({ queryKey: ["tenant-users"], queryFn: api.tenant.users, staleTime: 5 * 60_000 });
}

export function userName(users: { id: string; display_name: string | null; email: string | null }[] | undefined, id: string | null | undefined) {
  if (!id) return "—";
  const u = users?.find((x) => x.id === id);
  return u ? u.display_name ?? u.email ?? id : "…";
}

export function TaskForm({ link, task, onClose }: { link?: { property_id?: string; deal_id?: string; site_visit_id?: string }; task?: Task; onClose: () => void }) {
  const users = useUsers();
  const [v, set] = useForm({
    title: task?.title ?? "",
    description: task?.description ?? "",
    priority: task?.priority ?? "medium",
    status: task?.status ?? "open",
    due_date: task?.due_date ?? "",
    assignee_id: task?.assignee_id ?? "",
  });
  const save = useAction(
    () => {
      const { status, ...rest } = v;
      if (task) return api.tasks.update(task.id, { ...clean(rest), status });
      if (link?.site_visit_id) return api.siteVisits.followUp(link.site_visit_id, clean(rest));
      return api.tasks.create({ ...clean(rest), ...link });
    },
    { invalidate: [["tasks"], ["control-center"], ["site-visits"]], success: task ? "Task updated" : "Task created", onSuccess: onClose },
  );
  return (
    <Modal title={task ? "Edit task" : "New task"} onClose={onClose}>
      <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate(undefined); }}>
        <Field label="Title"><Input required value={v.title} onChange={set("title")} /></Field>
        <Field label="Description"><TextArea value={v.description} onChange={set("description")} /></Field>
        <div className="grid grid-2">
          <Field label="Priority"><Select value={v.priority} onChange={set("priority")} options={PRIORITIES} /></Field>
          {task && <Field label="Status"><Select value={v.status} onChange={set("status")} options={TASK_STATUSES} /></Field>}
          <Field label="Due date"><Input type="date" value={v.due_date} onChange={set("due_date")} /></Field>
          <Field label="Assignee">
            <Select value={v.assignee_id} onChange={set("assignee_id")} placeholder="Unassigned" options={(users.data ?? []).map((u) => ({ value: u.id, label: u.display_name ?? u.email ?? u.id }))} />
          </Field>
        </div>
        <div className="row"><Button variant="primary" disabled={save.isPending}>Save</Button></div>
      </form>
    </Modal>
  );
}

export function taskColumns(users: ReturnType<typeof useUsers>["data"], onDone?: (t: Task) => void): Column<Task>[] {
  return [
    { key: "t", header: "Task", render: (t) => <div>{t.title}{t.description && <div className="muted small">{t.description}</div>}</div> },
    { key: "s", header: "Status", render: (t) => <StatusBadge status={t.status} /> },
    { key: "p", header: "Priority", render: (t) => <StatusBadge status={t.priority} /> },
    { key: "a", header: "Assignee", render: (t) => userName(users, t.assignee_id) },
    {
      key: "d",
      header: "Due",
      render: (t) => {
        const overdue = t.due_date && new Date(t.due_date) < new Date(new Date().toDateString()) && !["done", "cancelled"].includes(t.status);
        return <span className={overdue ? "error-text" : ""}><DateText value={t.due_date} /></span>;
      },
    },
    ...(onDone
      ? [{ key: "x", header: "", render: (t: Task) => (t.status !== "done" && t.status !== "cancelled" ? <Button size="sm" onClick={(e) => { e.stopPropagation(); onDone(t); }}>Done</Button> : null) }]
      : []),
  ];
}

export function TasksPanel({ link }: { link: { property_id?: string; deal_id?: string; site_visit_id?: string } }) {
  const allowed = useCan();
  const users = useUsers();
  const [editing, setEditing] = useState<Task | "new" | null>(null);
  const [showClosed, setShowClosed] = useState(false);
  const tasks = useQuery({
    queryKey: ["tasks", link, showClosed],
    queryFn: () => api.tasks.list({ ...link, status: showClosed ? undefined : ["open", "in_progress", "blocked"], limit: 200 }),
  });
  const done = useAction((t: Task) => api.tasks.update(t.id, { status: "done" }), { invalidate: [["tasks"], ["control-center"]] });
  return (
    <Card
      title="Tasks"
      actions={
        <>
          <label className="row small"><input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} /> Show closed</label>
          <Can p={P.TASK_WRITE}><Button variant="primary" onClick={() => setEditing("new")}>New task</Button></Can>
        </>
      }
    >
      <Table
        rows={tasks.data?.items}
        empty="No tasks."
        onRowClick={allowed(P.TASK_WRITE) ? (t) => setEditing(t) : undefined}
        columns={taskColumns(users.data, allowed(P.TASK_WRITE) ? (t) => done.mutate(t) : undefined)}
      />
      {editing && <TaskForm link={link} task={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
    </Card>
  );
}
