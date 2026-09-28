import { formatMoneyCompact, P } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Card, DateText, Empty, PageHeader, Stat, StatusBadge, Table } from "../components/ui";
import { api } from "../lib/api";
import { useCan } from "../lib/auth";

export function DashboardPage() {
  const allowed = useCan();
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: api.reports.dashboard, enabled: allowed(P.REPORT_READ) });
  const myTasks = useQuery({ queryKey: ["tasks", "mine-open"], queryFn: () => api.tasks.list({ mine: true, status: ["open", "in_progress", "blocked"], limit: 10 }) });
  const visits = useQuery({
    queryKey: ["site-visits", "upcoming"],
    queryFn: () => api.siteVisits.list({ mine: true, status: ["scheduled"], starts_after: new Date().toISOString(), limit: 5 }),
    enabled: allowed(P.SITE_VISIT_READ),
  });

  if (!allowed(P.REPORT_READ)) return <PageHeader title="Welcome" subtitle="Use the navigation to get started." />;
  const d = dash.data;

  return (
    <div className="stack">
      <PageHeader title="Dashboard" />
      {d && (
        <>
          <div className="grid grid-4">
            <Stat label="Active deals" value={d.deals.active} hint={`${d.deals.won_this_month} won this month`} />
            <Stat label="Pipeline value" value={formatMoneyCompact(d.deals.pipeline_value)} tone="info" />
            <Stat label="Payments due (30 days)" value={d.payments.due_next_30_days} hint={formatMoneyCompact(d.payments.due_next_30_days_amount)} tone="warning" />
            <Stat label="Overdue payment milestones" value={d.payments.overdue_milestones} tone={d.payments.overdue_milestones ? "danger" : "success"} />
            <Stat label="Documents pending review" value={d.documents.pending_review} tone="warning" />
            <Stat label="Documents expiring (30 days)" value={d.documents.expiring_30_days} hint={`${d.documents.expired} already expired`} tone={d.documents.expired ? "danger" : "neutral"} />
            <Stat label="Boundaries awaiting review" value={d.geometry.awaiting_review} />
            <Stat label="Overdue tasks" value={d.tasks.overdue} tone={d.tasks.overdue ? "danger" : "success"} hint={`${d.tasks.mine_open} open tasks assigned to me`} />
          </div>
          <div className="grid grid-2">
            <Card title="Active deals by stage">
              {d.deals.by_stage.length === 0 ? (
                <Empty>No active deals.</Empty>
              ) : (
                <div className="stack">
                  {d.deals.by_stage.map((s) => (
                    <div key={s.stage} className="row" style={{ justifyContent: "space-between" }}>
                      <span className="row">
                        <span style={{ width: 10, height: 10, borderRadius: 2, background: s.color ?? "#94a3b8", display: "inline-block" }} />
                        {s.stage}
                      </span>
                      <strong>{s.count}</strong>
                    </div>
                  ))}
                </div>
              )}
            </Card>
            <Card title="Inventory and properties">
              <div className="grid grid-3">
                <Stat label="Properties" value={d.properties.total} />
                <Stat label="Approved sites" value={d.inventory.approved} tone="success" />
                <Stat label="Sites pending approval" value={d.inventory.pending_approval} tone="warning" />
              </div>
            </Card>
          </div>
        </>
      )}
      <div className="grid grid-2">
        <Card title="My open tasks" actions={<Link to="/tasks">All tasks</Link>}>
          <Table
            rows={myTasks.data?.items}
            empty="No open tasks."
            columns={[
              { key: "t", header: "Task", render: (t) => t.title },
              { key: "p", header: "Priority", render: (t) => <StatusBadge status={t.priority} /> },
              { key: "d", header: "Due", render: (t) => <DateText value={t.due_date} /> },
            ]}
          />
        </Card>
        <Card title="My upcoming site visits" actions={<Link to="/site-visits">All visits</Link>}>
          <Table
            rows={visits.data?.items}
            empty="No upcoming visits."
            columns={[
              { key: "t", header: "Visit", render: (v) => v.title },
              { key: "s", header: "When", render: (v) => <DateText value={v.scheduled_start} time /> },
            ]}
          />
        </Card>
      </div>
    </div>
  );
}
