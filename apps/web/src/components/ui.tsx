import { ApiError } from "@landcrm/api-client";
import { formatMoney, humanize } from "@landcrm/domain";
import { statusTone, tones, type Tone } from "@landcrm/ui";
import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

// ---- Toasts & actions ----

interface Toast {
  id: number;
  kind: "error" | "success";
  message: string;
}

const ToastContext = createContext<(kind: Toast["kind"], message: string) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((kind: Toast["kind"], message: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`}>
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Something went wrong";
}

/** Mutation that reports errors as toasts and invalidates the given query keys on success. */
export function useAction<TArgs, TResult>(
  fn: (args: TArgs) => Promise<TResult>,
  opts: { invalidate?: QueryKey[]; success?: string; onSuccess?: (r: TResult) => void } = {},
) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: fn,
    onSuccess: (r) => {
      opts.invalidate?.forEach((key) => qc.invalidateQueries({ queryKey: key }));
      if (opts.success) toast("success", opts.success);
      opts.onSuccess?.(r);
    },
    onError: (e) => toast("error", errorMessage(e)),
  });
}

// ---- Primitives ----

export function Button({
  variant = "default",
  size,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "default" | "primary" | "danger" | "ghost"; size?: "sm" }) {
  return <button {...props} className={`btn btn-${variant} ${size === "sm" ? "btn-sm" : ""} ${props.className ?? ""}`} />;
}

export function Badge({ tone, children }: { tone?: Tone; children: ReactNode }) {
  const t = tones[tone ?? "neutral"];
  return (
    <span className="badge" style={{ background: t.bg, color: t.fg }}>
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string | null | undefined }) {
  return <Badge tone={statusTone(status)}>{humanize(status)}</Badge>;
}

export function Card({ title, actions, children }: { title?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="card-header">
          <h3>{title}</h3>
          <div className="row">{actions}</div>
        </header>
      )}
      <div className="card-body">{children}</div>
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <div className="muted">{subtitle}</div>}
      </div>
      <div className="row">{actions}</div>
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`input ${props.className ?? ""}`} />;
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea rows={3} {...props} className={`input ${props.className ?? ""}`} />;
}

export function Select({
  options,
  placeholder,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & {
  options: readonly (string | { value: string; label: string })[];
  placeholder?: string;
}) {
  return (
    <select {...props} className={`input ${props.className ?? ""}`}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((o) =>
        typeof o === "string" ? (
          <option key={o} value={o}>
            {humanize(o)}
          </option>
        ) : (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ),
      )}
    </select>
  );
}

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className={`modal ${wide ? "modal-wide" : ""}`} onMouseDown={(e) => e.stopPropagation()}>
        <header className="card-header">
          <h3>{title}</h3>
          <Button variant="ghost" onClick={onClose} aria-label="Close">
            ✕
          </Button>
        </header>
        <div className="card-body">{children}</div>
      </div>
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: readonly { key: T; label: string }[]; value: T; onChange: (t: T) => void }) {
  return (
    <div className="tabs">
      {tabs.map((t) => (
        <button key={t.key} className={`tab ${t.key === value ? "tab-active" : ""}`} onClick={() => onChange(t.key)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  align?: "right";
}

export function Table<T>({ rows, columns, onRowClick, empty = "Nothing here yet." }: {
  rows: T[] | undefined;
  columns: Column<T>[];
  onRowClick?: (row: T) => void;
  empty?: string;
}) {
  if (!rows) return <div className="muted pad">Loading…</div>;
  if (rows.length === 0) return <Empty>{empty}</Empty>;
  return (
    <table className="table">
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c.key} style={{ textAlign: c.align ?? "left" }}>
              {c.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} onClick={onRowClick ? () => onRowClick(r) : undefined} className={onRowClick ? "clickable" : ""}>
            {columns.map((c) => (
              <td key={c.key} style={{ textAlign: c.align ?? "left" }}>
                {c.render(r)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Stat({ label, value, tone, hint }: { label: string; value: ReactNode; tone?: Tone; hint?: ReactNode }) {
  return (
    <div className="stat" style={tone ? { borderLeftColor: tones[tone].fg } : undefined}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint && <div className="muted small">{hint}</div>}
    </div>
  );
}

export function KV({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="kv">
      {items.map(([k, v]) => (
        <div key={k} className="kv-row">
          <dt>{k}</dt>
          <dd>{v ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

export function MoneyText({ value, currency }: { value: string | null | undefined; currency?: string }) {
  return <span className="mono">{formatMoney(value, currency)}</span>;
}

export function DateText({ value, time }: { value: string | null | undefined; time?: boolean }) {
  if (!value) return <span className="muted">—</span>;
  const d = new Date(value);
  return <span>{time ? d.toLocaleString("en-IN") : d.toLocaleDateString("en-IN")}</span>;
}

/** Minimal form state helper: returns [values, setField, reset]. */
export function useForm<T extends Record<string, unknown>>(initial: T) {
  const [values, setValues] = useState<T>(initial);
  const set = useCallback(<K extends keyof T>(key: K) => (e: { target: { value: string } } | T[K]) => {
    const value = e && typeof e === "object" && "target" in (e as object) ? (e as { target: { value: string } }).target.value : e;
    setValues((v) => ({ ...v, [key]: value }));
  }, []);
  return [values, set, setValues] as const;
}

/** Converts empty strings to undefined so optional API fields are omitted. */
export function clean<T extends Record<string, unknown>>(values: T): Partial<T> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(values)) if (v !== "" && v !== undefined) out[k] = v;
  return out as Partial<T>;
}

/** Prompts for a reason; returns null if cancelled or too short. */
export function askReason(message: string): string | null {
  const r = window.prompt(message);
  if (r === null) return null;
  if (r.trim().length < 3) {
    window.alert("A reason of at least 3 characters is required.");
    return null;
  }
  return r.trim();
}
