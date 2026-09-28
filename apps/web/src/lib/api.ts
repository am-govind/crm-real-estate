import { createApiClient } from "@landcrm/api-client";

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";
export const MAP_STYLE_URL =
  (import.meta.env.VITE_MAP_STYLE_URL as string | undefined) ?? "https://demotiles.maplibre.org/style.json";

const TENANT_KEY = "landcrm.tenant";

export function getTenantId(): string | null {
  return localStorage.getItem(TENANT_KEY);
}

export function setTenantId(id: string | null) {
  if (id) localStorage.setItem(TENANT_KEY, id);
  else localStorage.removeItem(TENANT_KEY);
}

let redirecting = false;

export const api = createApiClient({
  baseUrl: API_BASE_URL,
  mode: "cookie",
  getTenantId,
  onUnauthorized: () => {
    if (redirecting) return;
    redirecting = true;
    window.location.href = api.auth.loginUrl(window.location.href);
  },
});
