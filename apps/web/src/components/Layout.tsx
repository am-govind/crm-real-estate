import { P } from "@landcrm/domain";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router-dom";

import { api, setTenantId } from "../lib/api";
import { useCan, useMe } from "../lib/auth";
import { Badge, Button } from "./ui";

export function Layout() {
  const me = useMe();
  const allowed = useCan();
  const qc = useQueryClient();
  const unread = useQuery({
    queryKey: ["notifications", "unread"],
    queryFn: () => api.notifications.list({ unread_only: true, limit: 1 }),
    refetchInterval: 60_000,
  });

  const nav: { to: string; label: string; show: boolean }[] = [
    { to: "/", label: "Dashboard", show: allowed(P.REPORT_READ) },
    { to: "/deals", label: "Deals", show: allowed(P.DEAL_READ) },
    { to: "/properties", label: "Properties", show: allowed(P.PROPERTY_READ) },
    { to: "/owners", label: "Owners", show: allowed(P.OWNER_READ) },
    { to: "/map", label: "Map", show: allowed(P.PROPERTY_READ) },
    { to: "/inventory", label: "Inventory", show: allowed(P.INVENTORY_READ) },
    { to: "/site-visits", label: "Site visits", show: allowed(P.SITE_VISIT_READ) },
    { to: "/tasks", label: "Tasks", show: allowed(P.TASK_READ) },
  ];
  const isAdmin = [P.USER_MANAGE, P.ROLE_MANAGE, P.WORKFLOW_CONFIGURE, P.DOCUMENT_CONFIGURE, P.SCORING_CONFIGURE, P.AUDIT_READ].some(allowed);

  async function logout() {
    const { end_session_url } = await api.auth.logout();
    window.location.href = end_session_url ?? "/";
  }

  return (
    <div className="app">
      <nav className="sidebar">
        <div className="brand">Land Deal CRM</div>
        {nav
          .filter((n) => n.show)
          .map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"}>
              {n.label}
            </NavLink>
          ))}
        <NavLink to="/notifications">
          Notifications
          {!!unread.data?.total && <Badge tone="danger">{unread.data.total}</Badge>}
        </NavLink>
        {isAdmin && <NavLink to="/admin">Administration</NavLink>}
        <div className="spacer" />
        {me.memberships.length > 1 && (
          <select
            className="input"
            value={me.tenant_id ?? ""}
            onChange={(e) => {
              setTenantId(e.target.value);
              qc.invalidateQueries();
            }}
          >
            {me.memberships.map((m) => (
              <option key={m.tenant_id} value={m.tenant_id}>
                {m.tenant_name}
              </option>
            ))}
          </select>
        )}
        <div className="small" style={{ padding: "8px 10px" }}>
          {me.display_name ?? me.email}
        </div>
        <Button variant="ghost" style={{ color: "#cbd5e1", textAlign: "left" }} onClick={logout}>
          Sign out
        </Button>
      </nav>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
