import { useQueryClient } from "@tanstack/react-query";

import { Button, Card } from "../components/ui";
import { setTenantId } from "../lib/api";
import { useMe } from "../lib/auth";

export function NoTenantPage() {
  const me = useMe();
  const qc = useQueryClient();
  return (
    <div className="center">
      <div style={{ width: 420 }}>
        <Card title="Choose a workspace">
          {me.memberships.length === 0 ? (
            <p className="muted">
              You are signed in as {me.email} but are not a member of any organisation yet. Ask an administrator to invite you.
            </p>
          ) : (
            <div className="stack">
              {me.memberships.map((m) => (
                <Button
                  key={m.tenant_id}
                  onClick={() => {
                    setTenantId(m.tenant_id);
                    qc.invalidateQueries();
                  }}
                >
                  {m.tenant_name}
                </Button>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
