import type { ApiErrorBody } from "@landcrm/domain";

export type Query = Record<string, string | number | boolean | null | undefined | (string | number)[]>;

export interface ClientOptions {
  baseUrl: string;
  /** "cookie": web BFF session (HTTP-only cookie + CSRF header). "bearer": mobile access tokens. */
  mode: "cookie" | "bearer";
  getAccessToken?: () => Promise<string | null>;
  getTenantId?: () => string | null;
  onUnauthorized?: () => void;
  fetchImpl?: typeof fetch;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

export function buildQuery(q?: Query): string {
  if (!q) return "";
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((item) => params.append(k, String(item)));
    else params.append(k, String(v));
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

export class Http {
  constructor(private opts: ClientOptions) {}

  get baseUrl() {
    return this.opts.baseUrl.replace(/\/$/, "");
  }

  async headers(extra: Record<string, string> = {}): Promise<Record<string, string>> {
    const h: Record<string, string> = { Accept: "application/json", ...extra };
    const tenant = this.opts.getTenantId?.();
    if (tenant) h["X-Tenant-Id"] = tenant;
    if (this.opts.mode === "cookie") {
      h["X-Requested-With"] = "landcrm";
    } else {
      const token = await this.opts.getAccessToken?.();
      if (token) h.Authorization = `Bearer ${token}`;
    }
    return h;
  }

  async request<T>(method: string, path: string, init: { query?: Query; body?: unknown; form?: FormData } = {}): Promise<T> {
    const url = `${this.baseUrl}${path}${buildQuery(init.query)}`;
    const headers = await this.headers(init.body !== undefined ? { "Content-Type": "application/json" } : {});
    const f = this.opts.fetchImpl ?? fetch;
    const res = await f(url, {
      method,
      headers,
      credentials: this.opts.mode === "cookie" ? "include" : "omit",
      body: init.form ?? (init.body !== undefined ? JSON.stringify(init.body) : undefined),
    });
    if (res.status === 401) this.opts.onUnauthorized?.();
    if (!res.ok) {
      let body: Partial<ApiErrorBody> | undefined;
      try {
        body = await res.json();
      } catch {
        body = undefined;
      }
      const detail = (body as { detail?: unknown } | undefined)?.detail;
      throw new ApiError(
        res.status,
        body?.error?.code ?? (res.status === 422 ? "validation_failed" : "http_error"),
        body?.error?.message ?? (Array.isArray(detail) ? detail.map((d: { msg?: string }) => d.msg).join("; ") : res.statusText),
        body?.error?.details ?? (detail ? { detail } : {}),
      );
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  get<T>(path: string, query?: Query) {
    return this.request<T>("GET", path, { query });
  }
  post<T>(path: string, body?: unknown, query?: Query) {
    return this.request<T>("POST", path, { body: body ?? {}, query });
  }
  put<T>(path: string, body: unknown) {
    return this.request<T>("PUT", path, { body });
  }
  patch<T>(path: string, body: unknown) {
    return this.request<T>("PATCH", path, { body });
  }
  del<T = void>(path: string) {
    return this.request<T>("DELETE", path);
  }
  upload<T>(path: string, form: FormData) {
    return this.request<T>("POST", path, { form });
  }

  /** Absolute URL for plain links. Cookie clients can open it directly; bearer clients must fetch with headers. */
  url(path: string, query?: Query) {
    return `${this.baseUrl}${path}${buildQuery(query)}`;
  }

  /** Like url() but carries the selected tenant, since a browser link cannot send the X-Tenant-Id header. */
  downloadUrl(path: string) {
    return this.url(path, { _tenant: this.opts.getTenantId?.() ?? undefined });
  }
}
