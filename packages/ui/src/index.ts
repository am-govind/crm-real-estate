/** Shared design tokens. Web and mobile render their own components from these values. */

export const colors = {
  bg: "#f8fafc",
  surface: "#ffffff",
  surfaceMuted: "#f1f5f9",
  border: "#e2e8f0",
  text: "#0f172a",
  textMuted: "#64748b",
  primary: "#1d4ed8",
  primaryText: "#ffffff",
  success: "#16a34a",
  warning: "#d97706",
  danger: "#dc2626",
  info: "#0284c7",
  neutral: "#6b7280",
} as const;

export const tones = {
  neutral: { bg: "#f1f5f9", fg: "#334155" },
  info: { bg: "#e0f2fe", fg: "#075985" },
  success: { bg: "#dcfce7", fg: "#166534" },
  warning: { bg: "#fef3c7", fg: "#92400e" },
  danger: { bg: "#fee2e2", fg: "#991b1b" },
} as const;

export type Tone = keyof typeof tones;

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;
export const radius = { sm: 4, md: 8, lg: 12, pill: 999 } as const;
export const font = {
  family: "Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
  size: { xs: 12, sm: 13, md: 14, lg: 16, xl: 20, xxl: 24 },
  weight: { regular: "400", medium: "500", semibold: "600", bold: "700" },
} as const;

export function statusTone(status: string | null | undefined): Tone {
  switch (status) {
    case "approved":
    case "verified":
    case "clear":
    case "completed":
    case "done":
    case "paid":
    case "won":
    case "received":
    case "available":
      return "success";
    case "rejected":
    case "issue_found":
    case "lost":
    case "overdue":
    case "missing":
    case "disputed":
    case "failed":
      return "danger";
    case "pending":
    case "pending_review":
    case "pending_approval":
    case "needs_changes":
    case "submitted":
    case "bypassed":
    case "on_hold":
    case "partially_paid":
    case "waived":
    case "reserved":
      return "warning";
    case "active":
    case "in_progress":
    case "open":
    case "scheduled":
    case "recorded":
      return "info";
    default:
      return "neutral";
  }
}
