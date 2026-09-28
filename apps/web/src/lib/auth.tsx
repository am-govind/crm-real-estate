import { can, type Me, type Permission } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, type ReactNode } from "react";

import { api } from "./api";

const MeContext = createContext<Me | null>(null);

export function MeProvider({ children }: { children: ReactNode }) {
  const { data, error, isLoading } = useQuery({ queryKey: ["me"], queryFn: api.me, retry: false });
  if (isLoading) return <div className="center muted">Loading…</div>;
  if (error || !data) return <div className="center muted">Redirecting to sign in…</div>;
  return <MeContext.Provider value={data}>{children}</MeContext.Provider>;
}

export function useMe(): Me {
  const me = useContext(MeContext);
  if (!me) throw new Error("useMe outside MeProvider");
  return me;
}

export function useCan() {
  const me = useMe();
  return (p: Permission) => can(me.permissions, me.is_system_admin, p);
}

export function Can({ p, children }: { p: Permission; children: ReactNode }) {
  return useCan()(p) ? <>{children}</> : null;
}
