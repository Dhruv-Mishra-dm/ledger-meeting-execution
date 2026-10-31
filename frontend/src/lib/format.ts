const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-11-08" -> "Nov 8, 2026". Date-only strings are formatted without timezone conversion. */
export function fmtDate(iso: string | null | undefined, withYear = true): string {
  if (!iso) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const s = `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}`;
  return withYear ? `${s}, ${m[1]}` : s;
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** Whole days from `today` to `iso` (negative = past). Both are date-only strings. */
export function daysUntil(iso: string, today: string): number {
  const a = Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10));
  const b = Date.UTC(+today.slice(0, 4), +today.slice(5, 7) - 1, +today.slice(8, 10));
  return Math.round((a - b) / 86_400_000);
}

export function dueLabel(iso: string | null, today: string): { text: string; tone: "danger" | "warn" | "muted" | "ok" } {
  if (!iso) return { text: "No deadline", tone: "muted" };
  const d = daysUntil(iso, today);
  if (d < 0) return { text: `${-d}d overdue`, tone: "danger" };
  if (d === 0) return { text: "Due today", tone: "warn" };
  if (d === 1) return { text: "Due tomorrow", tone: "warn" };
  return { text: `In ${d} days`, tone: "muted" };
}

export function displayValue(value: string | null, kind: string): string {
  if (!value) return "—";
  return kind === "date" ? fmtDate(value) : value;
}

export const CATEGORY_LABEL: Record<string, string> = {
  contradiction: "Direct contradiction",
  deadline_change: "Changed deadline",
  ownership: "Conflicting ownership",
  resource: "Resource conflict",
  scope: "Scope change",
  commitment: "Incompatible commitment",
};

export function pct(n: number): string {
  return `${Math.round(n * 100)}%`;
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
