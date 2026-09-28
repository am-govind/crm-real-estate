import { P, type Permission } from "@landcrm/domain";
import { useSearchParams } from "react-router-dom";

import { PageHeader, Tabs } from "../../components/ui";
import { useCan, useMe } from "../../lib/auth";
import { AuditAdmin, DocumentAdmin, GeographyAdmin, ScoringAdmin, SettingsAdmin, TenantsAdmin } from "./ConfigAdmin";
import { InvitationsAdmin, MembersAdmin, RolesAdmin } from "./TeamAdmin";
import { WorkflowAdmin } from "./WorkflowAdmin";

const SECTIONS: { key: string; label: string; p?: Permission; systemAdmin?: boolean }[] = [
  { key: "members", label: "Members", p: P.USER_MANAGE },
  { key: "invitations", label: "Invitations", p: P.USER_MANAGE },
  { key: "roles", label: "Roles", p: P.ROLE_MANAGE },
  { key: "workflows", label: "Workflows", p: P.WORKFLOW_CONFIGURE },
  { key: "documents", label: "Document rules", p: P.DOCUMENT_CONFIGURE },
  { key: "scoring", label: "Scoring", p: P.SCORING_CONFIGURE },
  { key: "geography", label: "Geography", p: P.GEOGRAPHY_MANAGE },
  { key: "settings", label: "Settings", p: P.TENANT_MANAGE },
  { key: "audit", label: "Audit log", p: P.AUDIT_READ },
  { key: "tenants", label: "Tenants", systemAdmin: true },
];

export function AdminPage() {
  const me = useMe();
  const allowed = useCan();
  const [params, setParams] = useSearchParams();
  const visible = SECTIONS.filter((s) => (s.systemAdmin ? me.is_system_admin : allowed(s.p!)));
  const tab = visible.find((s) => s.key === params.get("tab"))?.key ?? visible[0]?.key;
  if (!tab) return <PageHeader title="Administration" subtitle="You do not have access to any administration area." />;
  return (
    <div className="stack">
      <PageHeader title="Administration" />
      <Tabs tabs={visible} value={tab} onChange={(t) => setParams({ tab: t })} />
      {tab === "members" && <MembersAdmin />}
      {tab === "invitations" && <InvitationsAdmin />}
      {tab === "roles" && <RolesAdmin />}
      {tab === "workflows" && <WorkflowAdmin />}
      {tab === "documents" && <DocumentAdmin />}
      {tab === "scoring" && <ScoringAdmin />}
      {tab === "geography" && <GeographyAdmin />}
      {tab === "settings" && <SettingsAdmin />}
      {tab === "audit" && <AuditAdmin />}
      {tab === "tenants" && <TenantsAdmin />}
    </div>
  );
}
