/**
 * Money is carried as decimal strings end-to-end (the API serializes Decimal as string).
 * These helpers never convert to binary floating point.
 */

const MONEY_RE = /^-?\d+(\.\d{1,2})?$/;

export function isMoney(value: string): boolean {
  return MONEY_RE.test(value.trim());
}

/** Parses user input like "12,50,000.5" into a canonical "1250000.50" string, or null. */
export function parseMoneyInput(input: string): string | null {
  const cleaned = input.replace(/[,\s₹]/g, "");
  if (!isMoney(cleaned)) return null;
  const [whole, frac = ""] = cleaned.split(".");
  return `${BigInt(whole ?? "0").toString()}.${frac.padEnd(2, "0")}`;
}

function toMinor(value: string): bigint {
  const [whole = "0", frac = ""] = value.split(".");
  const negative = whole.startsWith("-");
  const minor = BigInt(whole.replace("-", "")) * 100n + BigInt(frac.padEnd(2, "0").slice(0, 2) || "0");
  return negative ? -minor : minor;
}

function fromMinor(minor: bigint): string {
  const negative = minor < 0n;
  const abs = negative ? -minor : minor;
  const whole = abs / 100n;
  const frac = (abs % 100n).toString().padStart(2, "0");
  return `${negative ? "-" : ""}${whole}.${frac}`;
}

export function addMoney(...values: (string | null | undefined)[]): string {
  return fromMinor(values.reduce<bigint>((acc, v) => acc + (v ? toMinor(v) : 0n), 0n));
}

export function subtractMoney(a: string, b: string): string {
  return fromMinor(toMinor(a) - toMinor(b));
}

function groupIndian(digits: string): string {
  if (digits.length <= 3) return digits;
  const last3 = digits.slice(-3);
  const rest = digits.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return `${rest},${last3}`;
}

function groupWestern(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

const SYMBOLS: Record<string, string> = { INR: "₹", USD: "$", EUR: "€", GBP: "£" };

export function formatMoney(value: string | null | undefined, currency = "INR", opts: { decimals?: boolean } = {}): string {
  if (value === null || value === undefined || value === "") return "—";
  const [wholeRaw = "0", frac = "00"] = value.split(".");
  const negative = wholeRaw.startsWith("-");
  const digits = wholeRaw.replace("-", "");
  const grouped = currency === "INR" ? groupIndian(digits) : groupWestern(digits);
  const symbol = SYMBOLS[currency] ?? `${currency} `;
  const decimals = opts.decimals ?? true;
  return `${negative ? "-" : ""}${symbol}${grouped}${decimals ? "." + frac.padEnd(2, "0").slice(0, 2) : ""}`;
}

/** Compact Indian notation (lakh / crore) for dashboards, computed without floats. */
export function formatMoneyCompact(value: string | null | undefined, currency = "INR"): string {
  if (!value) return "—";
  if (currency !== "INR") return formatMoney(value, currency, { decimals: false });
  const minor = toMinor(value);
  const abs = minor < 0n ? -minor : minor;
  const sign = minor < 0n ? "-" : "";
  const crore = 10_000_000n * 100n;
  const lakh = 100_000n * 100n;
  const scaled = (unit: bigint, suffix: string) => {
    const hundredths = (abs * 100n) / unit;
    return `${sign}₹${hundredths / 100n}.${(hundredths % 100n).toString().padStart(2, "0")} ${suffix}`;
  };
  if (abs >= crore) return scaled(crore, "Cr");
  if (abs >= lakh) return scaled(lakh, "L");
  return formatMoney(value, currency, { decimals: false });
}
