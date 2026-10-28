const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

// Column-name heuristics. A count of loans is never money, even if its name says "disbursed".
const COUNT_HINT = /(^|_)(count|cnt|num|number|no|loans|emis|customers|accounts|branches|borrowers|records|cases)(_|$)/i;
const MONEY_HINT = /(amount|book|outstanding|principal|disburs|volume|income|collateral_value|ticket|overdue|sanctioned|aum|exposure|value|balance|(^|_)emi(_|$))/i;
// Unit suffix only: "disbursed_crore", "ticket_in_lakh". Not thresholds like "income_less_than_1lakh".
const CRORE_HINT = /(^|_)(in_)?(crore|crores|cr)$/i;
const LAKH_HINT = /(^|_)(in_)?(lakh|lakhs|lac|lacs)$/i;
// "loans_above_10_crore" is a threshold, not a unit
const THRESHOLD_HINT = /\d_?(crore|crores|cr|lakh|lakhs|lac|lacs)$/i;
const PCT_HINT = /(pct|percent|share|ratio|rate)/i;
const TIME_HINT = /(date|month|year|quarter|fy|vintage|period)/i;

const ACRONYMS: Record<string, string> = {
  npa: "NPA", gnpa: "GNPA", emi: "EMI", fy: "FY", ltv: "LTV", cibil: "CIBIL", dpd: "DPD", sma: "SMA",
  sma2: "SMA-2", id: "ID", dsa: "DSA", foir: "FOIR", aum: "AUM", pct: "%", ntc: "NTC", mom: "MoM",
};

export function humanizeColumn(col: string): string {
  const words = col.split("_").filter(Boolean).map((w) => ACRONYMS[w.toLowerCase()] ?? w.toLowerCase());
  const s = words.join(" ").replace(/ %/g, " %");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Indian grouping: 12,34,56,789 */
export function formatNumber(v: number): string {
  return inr.format(v);
}

/** Short Indian units for axes and tiles: ₹4,512 Cr, ₹38.6 L */
export function compactINR(v: number, money: boolean): string {
  const abs = Math.abs(v);
  const prefix = money ? "₹" : "";
  if (abs >= 1e7) return `${prefix}${inr.format(+(v / 1e7).toFixed(abs >= 1e9 ? 0 : 1))} Cr`;
  if (abs >= 1e5) return `${prefix}${inr.format(+(v / 1e5).toFixed(1))} L`;
  return `${prefix}${inr.format(+v.toFixed(2))}`;
}

function hasCroreUnit(col: string): boolean {
  return CRORE_HINT.test(col) && !THRESHOLD_HINT.test(col);
}

function hasLakhUnit(col: string): boolean {
  return LAKH_HINT.test(col) && !THRESHOLD_HINT.test(col);
}

export function isCountColumn(col: string): boolean {
  return COUNT_HINT.test(col) && !hasCroreUnit(col) && !hasLakhUnit(col);
}

/** Money in plain rupees (not already converted to crore/lakh, not a count or a %) */
export function isMoneyColumn(col: string): boolean {
  return (
    MONEY_HINT.test(col) &&
    !isCountColumn(col) &&
    !PCT_HINT.test(col) &&
    !hasCroreUnit(col) &&
    !hasLakhUnit(col)
  );
}

export function isCroreColumn(col: string): boolean {
  return hasCroreUnit(col) && !isPctColumn(col);
}

export function isLakhColumn(col: string): boolean {
  return hasLakhUnit(col) && !isPctColumn(col);
}

export function isPctColumn(col: string): boolean {
  return /(pct|percent)/i.test(col);
}

export function isTimeColumn(col: string): boolean {
  return TIME_HINT.test(col);
}

export function formatCell(v: unknown, col: string): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "number") {
    if (isTimeColumn(col) && Number.isInteger(v) && v > 1900 && v < 2100) return String(v);
    if (isPctColumn(col)) return `${formatNumber(v)}%`;
    if (isCountColumn(col)) return formatNumber(v);
    if (isCroreColumn(col)) return `₹${formatNumber(v)} Cr`;
    if (isLakhColumn(col)) return `₹${formatNumber(v)} L`;
    if (isMoneyColumn(col)) return `₹${formatNumber(v)}`;
    return formatNumber(v);
  }
  if (typeof v === "string" && /^\d{4}-\d{2}-01$/.test(v) && /month/i.test(col)) {
    const d = new Date(v + "T00:00:00");
    return d.toLocaleDateString("en-IN", { month: "short", year: "numeric" });
  }
  return String(v);
}

export function toCSV(columns: string[], rows: unknown[][]): string {
  const esc = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [columns.map(esc).join(","), ...rows.map((r) => r.map(esc).join(","))].join("\n");
}
