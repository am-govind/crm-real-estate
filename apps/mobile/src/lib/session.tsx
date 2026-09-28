import type { Me } from "@landcrm/domain";
import { useQueryClient } from "@tanstack/react-query";
import * as AuthSession from "expo-auth-session";
import * as WebBrowser from "expo-web-browser";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api } from "./api";
import { DEV_AUTH_EMAIL, OIDC_CLIENT_ID, OIDC_SCOPES } from "./config";
import { closeStore, openStore, startBackgroundSync, syncNow } from "./offline";
import { registerForPush, unregisterPush } from "./push";
import { clearSession, currentTokens, fromTokenResponse, getDiscovery, getTenantId, loadSession, onSignedOut, saveTokens, setTenantId } from "./tokens";

WebBrowser.maybeCompleteAuthSession();

type Status = "loading" | "signedOut" | "chooseTenant" | "ready";

interface SessionValue {
  status: Status;
  me: Me | null;
  error: string | null;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
  chooseTenant: (tenantId: string) => Promise<void>;
  can: (permission: string) => boolean;
}

const SessionContext = createContext<SessionValue | null>(null);

export const redirectUri = AuthSession.makeRedirectUri({ scheme: "landcrm", path: "auth" });

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<Status>("loading");
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reset = useCallback(async () => {
    closeStore();
    queryClient.clear();
    await clearSession();
    setMe(null);
    setStatus("signedOut");
  }, [queryClient]);

  /** Resolve the user and tenant, then open that tenant's offline store. */
  const bootstrap = useCallback(async () => {
    try {
      let profile: Me;
      try {
        profile = await api.me();
      } catch (err) {
        // A stored tenant the user no longer belongs to is rejected; retry without it.
        if (!getTenantId()) throw err;
        await setTenantId(null);
        profile = await api.me();
      }
      if (!profile.tenant_id) {
        if (!profile.memberships.length) {
          setError("Your account is not a member of any organisation yet.");
          await reset();
          return;
        }
        setMe(profile);
        setStatus("chooseTenant");
        return;
      }
      await setTenantId(profile.tenant_id);
      setMe(profile);
      await openStore(profile.id, profile.tenant_id);
      setStatus("ready");
      void syncNow();
      void registerForPush().catch(() => undefined);
    } catch (err) {
      setError((err as Error).message);
      await reset();
    }
  }, [reset]);

  useEffect(() => {
    void (async () => {
      const tokens = await loadSession();
      if (tokens) await bootstrap();
      else setStatus("signedOut");
    })();
  }, [bootstrap]);

  useEffect(() => onSignedOut(() => void reset()), [reset]);

  useEffect(() => {
    if (status !== "ready") return;
    return startBackgroundSync();
  }, [status]);

  const signIn = useCallback(async () => {
    setError(null);
    try {
      if (DEV_AUTH_EMAIL) {
        await saveTokens({ accessToken: `dev:${DEV_AUTH_EMAIL}` });
      } else {
        const discovery = await getDiscovery();
        const request = new AuthSession.AuthRequest({ clientId: OIDC_CLIENT_ID, redirectUri, scopes: OIDC_SCOPES, usePKCE: true });
        const result = await request.promptAsync(discovery);
        if (result.type !== "success") return;
        const token = await AuthSession.exchangeCodeAsync(
          { clientId: OIDC_CLIENT_ID, code: result.params.code!, redirectUri, extraParams: { code_verifier: request.codeVerifier ?? "" } },
          discovery,
        );
        await saveTokens(fromTokenResponse(token));
      }
      setStatus("loading");
      await bootstrap();
    } catch (err) {
      setError((err as Error).message);
    }
  }, [bootstrap]);

  const signOut = useCallback(async () => {
    await unregisterPush().catch(() => undefined);
    const idToken = currentTokens()?.idToken;
    await reset();
    if (idToken && !DEV_AUTH_EMAIL) {
      const discovery = await getDiscovery().catch(() => null);
      if (discovery?.endSessionEndpoint) {
        const url = `${discovery.endSessionEndpoint}?client_id=${encodeURIComponent(OIDC_CLIENT_ID)}&id_token_hint=${encodeURIComponent(idToken)}&post_logout_redirect_uri=${encodeURIComponent(redirectUri)}`;
        await WebBrowser.openAuthSessionAsync(url, redirectUri).catch(() => undefined);
      }
    }
  }, [reset]);

  const chooseTenant = useCallback(
    async (tenantId: string) => {
      await setTenantId(tenantId);
      setStatus("loading");
      await bootstrap();
    },
    [bootstrap],
  );

  const value = useMemo<SessionValue>(
    () => ({ status, me, error, signIn, signOut, chooseTenant, can: (p) => !!me?.permissions.includes(p) }),
    [status, me, error, signIn, signOut, chooseTenant],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside SessionProvider");
  return ctx;
}
