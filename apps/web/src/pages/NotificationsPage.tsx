import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { Button, Card, DateText, PageHeader, Table, useAction } from "../components/ui";
import { api } from "../lib/api";

export function NotificationsPage() {
  const navigate = useNavigate();
  const list = useQuery({ queryKey: ["notifications", "all"], queryFn: () => api.notifications.list({ limit: 100 }) });
  const read = useAction(api.notifications.read, { invalidate: [["notifications"]] });
  const readAll = useAction(() => api.notifications.readAll(), { invalidate: [["notifications"]] });

  return (
    <div className="stack">
      <PageHeader title="Notifications" actions={<Button onClick={() => readAll.mutate(undefined)}>Mark all read</Button>} />
      <Card>
        <Table
          rows={list.data?.items}
          empty="No notifications."
          onRowClick={(n) => {
            if (!n.read_at) read.mutate(n.id);
            if (n.link) navigate(n.link);
          }}
          columns={[
            { key: "t", header: "", render: (n) => (n.read_at ? "" : "●") },
            { key: "title", header: "Notification", render: (n) => <div><strong>{n.title}</strong><div className="muted small">{n.body}</div></div> },
            { key: "when", header: "When", render: (n) => <DateText value={n.created_at} time /> },
          ]}
        />
      </Card>
    </div>
  );
}
