/** Measurements are stored exactly as entered, with their unit. Conversions are display-only and labelled. */

export interface Measurement {
  value: string;
  unit: string;
}

export interface DerivedValue {
  value: string;
  unit: string;
  derived: true;
  formula: string;
  sources: Record<string, unknown>;
}

export const AREA_UNITS = [
  { key: "sqm", label: "sq m" },
  { key: "sqft", label: "sq ft" },
  { key: "sqyd", label: "sq yd" },
  { key: "acre", label: "acre" },
  { key: "hectare", label: "hectare" },
  { key: "guntha", label: "guntha" },
  { key: "cent", label: "cent" },
  { key: "are", label: "are" },
  { key: "bigha", label: "bigha (regional, not converted)" },
  { key: "biswa", label: "biswa (regional, not converted)" },
  { key: "kanal", label: "kanal (regional, not converted)" },
  { key: "marla", label: "marla (regional, not converted)" },
  { key: "kattha", label: "kattha (regional, not converted)" },
  { key: "ground", label: "ground (regional, not converted)" },
] as const;

export const LENGTH_UNITS = [
  { key: "m", label: "m" },
  { key: "ft", label: "ft" },
  { key: "yd", label: "yd" },
  { key: "km", label: "km" },
] as const;

export function formatMeasurement(m: Measurement | null | undefined): string {
  if (!m) return "—";
  return `${m.value} ${m.unit}`;
}

export function formatDerived(d: DerivedValue | string | null | undefined, unit = "m²"): string {
  if (d === null || d === undefined) return "—";
  const value = typeof d === "string" ? d : d.value;
  const [whole = "0"] = value.split(".");
  return `≈ ${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",")} ${unit} (derived)`;
}
