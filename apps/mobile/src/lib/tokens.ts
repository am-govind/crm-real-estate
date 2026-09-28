import * as AuthSession from "expo-auth-session";
import * as SecureStore from "expo-secure-store";

import { DEV_AUTH_EMAIL, OIDC_CLIENT_ID, OIDC_ISSUER } from "./config";

export interface Tokens {
  accessToken: string;
  refreshToken?: string;
  idToken?: string;
  /** Epoch milliseconds. */
  expiresAt?: number;
}

const TOKENS_KEY = "landcrm.tokens";
const TENANT_KEY = "landcrm.tenant";

let tokens: Tokens | null = null;
let tenantId: string | null = null;
let refreshing: Promise<Tokens | null> | null = null;
let discoveryPromise: Promise<AuthSession.DiscoveryDocument> | null = null;
const signedOutListeners = new Set<() => void>();

export function getDiscovery() {
  discoveryPromise ??= AuthSession.fetchDiscoveryAsync(OIDC_ISSUER).catch((err) => {
    discoveryPromise = null;
    throw err;
  });
  return discoveryPromise;
}

export async function loadSession() {
  const [rawTokens, rawTenant] = await Promise.all([SecureStore.getItemAsync(TOKENS_KEY), SecureStore.getItemAsync(TENANT_KEY)]);
  tokens = rawTokens ? (JSON.parse(rawTokens) as Tokens) : null;
  tenantId = rawTenant;
  return tokens;
}

export async function saveTokens(next: Tokens) {
  tokens = next;
  await SecureStore.setItemAsync(TOKENS_KEY, JSON.stringify(next));
}

export function fromTokenResponse(r: AuthSession.TokenResponse, previous?: Tokens | null): Tokens {
  return {
    accessToken: r.accessToken,
    refreshToken: r.refreshToken ?? previous?.refreshToken,
    idToken: r.idToken ?? previous?.idToken,
    expiresAt: r.expiresIn ? (r.issuedAt ?? Date.now() / 1000) * 1000 + r.expiresIn * 1000 : undefined,
  };
}

export function currentTokens() {
  return tokens;
}

export function getTenantId() {
  return tenantId;
}

export async function setTenantId(id: string | null) {
  tenantId = id;
  if (id) await SecureStore.setItemAsync(TENANT_KEY, id);
  else await SecureStore.deleteItemAsync(TENANT_KEY);
}

async function refresh(current: Tokens): Promise<Tokens | null> {
  if (!current.refreshToken) return null;
  try {
    const discovery = await getDiscovery();
    const res = await AuthSession.refreshAsync({ clientId: OIDC_CLIENT_ID, refreshToken: current.refreshToken }, discovery);
    const next = fromTokenResponse(res, current);
    await saveTokens(next);
    return next;
  } catch {
    return null;
  }
}

/** Returns a valid access token, refreshing it shortly before expiry. */
export async function getAccessToken(): Promise<string | null> {
  if (!tokens) return null;
  if (DEV_AUTH_EMAIL || !tokens.expiresAt || tokens.expiresAt - 60_000 > Date.now()) return tokens.accessToken;
  refreshing ??= refresh(tokens).finally(() => {
    refreshing = null;
  });
  const next = await refreshing;
  if (!next) {
    notifySignedOut();
    return null;
  }
  return next.accessToken;
}

export async function clearSession() {
  const previous = tokens;
  tokens = null;
  tenantId = null;
  await Promise.all([SecureStore.deleteItemAsync(TOKENS_KEY), SecureStore.deleteItemAsync(TENANT_KEY)]);
  if (previous?.refreshToken && !DEV_AUTH_EMAIL) {
    try {
      const discovery = await getDiscovery();
      if (discovery.revocationEndpoint) {
        await AuthSession.revokeAsync({ clientId: OIDC_CLIENT_ID, token: previous.refreshToken, tokenTypeHint: AuthSession.TokenTypeHint.RefreshToken }, discovery);
      }
    } catch {
      // Revocation is best effort; local credentials are already gone.
    }
  }
}

export function onSignedOut(listener: () => void) {
  signedOutListeners.add(listener);
  return () => {
    signedOutListeners.delete(listener);
  };
}

export function notifySignedOut() {
  signedOutListeners.forEach((l) => l());
}
