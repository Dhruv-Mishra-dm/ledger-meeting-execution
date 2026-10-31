import { useEffect, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { CATEGORY_LABEL, displayValue, dueLabel, fmtDate, pct, titleCase } from "../lib/format";
import type { Segment } from "../lib/types";

export function PageHeader({ title, subtitle, actions, eyebrow }: { title: string; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: string }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4 border-b border-line pb-5">
      <div className="min-w-0">
        {eyebrow && <div className="label mb-1">{eyebrow}</div>}
        <h1 className="font-serif text-[28px] font-semibold leading-tight tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-ink-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

const TONES: Record<string, string> = {
  neutral: "bg-ink/5 text-ink-soft border-line",
  accent: "bg-accent-tint text-accent border-accent/20",
  danger: "bg-danger-tint text-danger border-danger/20",
  warn: "bg-warn-tint text-warn border-warn/20",
  ok: "bg-ok-tint text-ok border-ok/20",
  info: "bg-info-tint text-info border-info/20",
  muted: "bg-transparent text-ink-muted border-line",
};

export function Badge({ tone = "neutral", children, title }: { tone?: keyof typeof TONES | string; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 rounded border px-1.5 py-[1px] font-mono text-[11px] uppercase tracking-wide ${TONES[tone] ?? TONES.neutral}`}>
      {children}
    </span>
  );
}

const STATUS_TONE: Record<string, string> = {
  proposed: "info", under_review: "danger", confirmed: "ok", superseded: "muted", rejected: "muted",
  approved: "ok", done: "accent", open: "danger", needs_review: "warn", accepted_new: "ok", kept_previous: "neutral", compatible: "neutral",
  processed: "ok", processing: "info", uploaded: "neutral", failed: "danger", published: "ok", publishing: "info",
};
const STATUS_LABEL: Record<string, string> = { under_review: "Under review", accepted_new: "New accepted", kept_previous: "Previous kept", needs_review: "Needs review", done: "Completed" };

export function StatusBadge({ status }: { status: string }) {
  return <Badge tone={STATUS_TONE[status] ?? "neutral"}>{STATUS_LABEL[status] ?? titleCase(status)}</Badge>;
}

export function Confidence({ value }: { value: number }) {
  const tone = value >= 0.85 ? "bg-ok" : value >= 0.65 ? "bg-warn" : "bg-danger";
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-[11px] text-ink-muted" title="Extraction confidence">
      <span className="h-1.5 w-10 overflow-hidden rounded-full bg-line">
        <span className={`block h-full ${tone}`} style={{ width: pct(value) }} />
      </span>
      {pct(value)}
    </span>
  );
}

export function OriginTag({ origin, kind }: { origin: string; kind: "owner" | "deadline" | "decision" }) {
  if (origin === "explicit") return <span className="font-mono text-[10px] uppercase text-ok" title={`Stated explicitly in the transcript`}>explicit</span>;
  if (origin === "unassigned" || origin === "unspecified")
    return <span className="font-mono text-[10px] uppercase text-warn" title={`Not stated in the transcript — needs a human`}>{kind === "owner" ? "unassigned" : "unspecified"}</span>;
  return <span className="font-mono text-[10px] uppercase text-info" title="Interpreted by the system, not stated word for word">{origin}</span>;
}

export function Due({ iso, today }: { iso: string | null; today: string }) {
  const d = dueLabel(iso, today);
  const tone = d.tone === "danger" ? "text-danger" : d.tone === "warn" ? "text-warn" : "text-ink-muted";
  return (
    <span className="whitespace-nowrap">
      <span className="font-medium text-ink">{fmtDate(iso)}</span>
      {iso && <span className={`ml-1.5 font-mono text-[11px] ${tone}`}>{d.text}</span>}
    </span>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-ink-muted">
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-line-strong border-t-accent" />
      {label}
    </span>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex min-h-[160px] items-center justify-center">
      <Spinner label={label} />
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="card flex items-start justify-between gap-4 border-danger/30 bg-danger-tint/40 px-4 py-3 text-danger">
      <span>{message}</span>
      {onRetry && <button className="btn-secondary" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="card flex flex-col items-center justify-center px-6 py-12 text-center">
      <div className="font-serif text-lg font-semibold">{title}</div>
      {children && <p className="mt-1 max-w-md text-ink-muted">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Card({ title, actions, children, className = "", padded = true }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; padded?: boolean }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="text-[13px] font-semibold">{title}</h2>
          {actions}
        </div>
      )}
      <div className={padded ? "p-4" : ""}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, tone, to, hint }: { label: string; value: number | string; tone?: "danger" | "warn" | "ok"; to?: string; hint?: string }) {
  const color = tone === "danger" ? "text-danger" : tone === "warn" ? "text-warn" : tone === "ok" ? "text-ok" : "text-ink";
  const body = (
    <div className="card h-full px-4 py-3 transition hover:border-line-strong">
      <div className="label">{label}</div>
      <div className={`mt-1 font-serif text-[30px] font-semibold leading-none ${color}`}>{value}</div>
      {hint && <div className="mt-1 text-[12px] text-ink-muted">{hint}</div>}
    </div>
  );
  return to ? <Link to={to}>{body}</Link> : body;
}

export function Modal({ open, onClose, title, children, footer, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const fn = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", fn);
    return () => window.removeEventListener("keydown", fn);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-ink/30 p-4 pt-[8vh]" onMouseDown={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title} className={`card w-full ${wide ? "max-w-3xl" : "max-w-lg"}`} onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <h2 className="font-serif text-lg font-semibold">{title}</h2>
          <button className="btn-ghost px-2" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function Evidence({ excerpt, segments, meetingId, speaker }: { excerpt?: string; segments?: Segment[]; meetingId?: number; speaker?: string | null }) {
  const segs = segments && segments.length ? segments : null;
  return (
    <div className="space-y-1.5">
      {segs
        ? segs.map((s) => (
            <blockquote key={s.idx} className="quote">
              “{s.text}”
              <footer className="mt-0.5 font-sans font-mono text-[11px] not-italic text-ink-muted">
                {s.speaker ?? "Unattributed speaker"}
                {s.timestamp && ` · ${s.timestamp}`} · segment {s.idx + 1}
              </footer>
            </blockquote>
          ))
        : excerpt && (
            <blockquote className="quote">
              “{excerpt}”
              {speaker !== undefined && <footer className="mt-0.5 font-mono text-[11px] text-ink-muted">{speaker ?? "Unattributed speaker"}</footer>}
            </blockquote>
          )}
      {meetingId && <Link to={`/meetings/${meetingId}?tab=transcript`} className="link text-[12px]">View in transcript →</Link>}
    </div>
  );
}

export function ConflictStamp({ category }: { category: string }) {
  return (
    <span className="stamp inline-block select-none rounded-sm border-2 border-danger px-2 py-0.5 font-mono text-[12px] font-medium uppercase text-danger">
      Conflict · {CATEGORY_LABEL[category] ?? category}
    </span>
  );
}

export function Value({ value, kind }: { value: string | null; kind: string }) {
  return <span className="font-semibold">{displayValue(value, kind)}</span>;
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[12px] font-medium text-ink-soft">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[12px] text-ink-muted">{hint}</span>}
    </label>
  );
}

export function ProjectRequired({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
