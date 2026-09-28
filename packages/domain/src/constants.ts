export const PROPERTY_STATUS_COLORS: Record<string, string> = {
  prospect: "#6b7280",
  in_pipeline: "#2563eb",
  acquired: "#16a34a",
  dropped: "#dc2626",
  on_hold: "#d97706",
};

export const LAND_TYPES = ["agricultural", "non_agricultural", "residential", "commercial", "industrial", "mixed", "other"] as const;
export const PROPERTY_STATUSES = ["prospect", "in_pipeline", "acquired", "dropped", "on_hold"] as const;
export const ROAD_ACCESS = ["unknown", "none", "kaccha", "pakka", "highway_frontage"] as const;
export const TITLE_STATUSES = ["unknown", "under_review", "clear", "encumbered", "disputed"] as const;
export const OWNERSHIP_TYPES = ["sole", "joint", "co_owner", "legal_heir", "poa_holder", "lessee", "other"] as const;
export const DD_CATEGORIES = ["legal", "technical", "revenue", "survey"] as const;
export const DD_STATUSES = ["not_started", "in_progress", "clear", "issue_found", "waived"] as const;
export const TASK_STATUSES = ["open", "in_progress", "blocked", "done", "cancelled"] as const;
export const PRIORITIES = ["low", "medium", "high", "urgent"] as const;
export const MILESTONE_KINDS = ["token", "advance", "installment", "final", "other"] as const;
export const PAYMENT_MODES = ["bank_transfer", "cheque", "demand_draft", "upi", "cash", "other"] as const;
export const INVENTORY_PROPERTY_TYPES = ["land_plot", "apartment", "studio_flat", "commercial_unit"] as const;
export const INVENTORY_STATUSES = ["available", "reserved", "blocked", "sold", "under_acquisition", "not_for_sale"] as const;

export const DD_STATUS_TONE: Record<string, "neutral" | "info" | "success" | "danger" | "warning"> = {
  not_started: "neutral",
  in_progress: "info",
  clear: "success",
  issue_found: "danger",
  waived: "warning",
};

export function humanize(key: string | null | undefined): string {
  if (!key) return "—";
  return key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export const GEOMETRY_NOTICE =
  "Map-derived information is informational until approved by a qualified reviewer and does not by itself prove legal title.";
