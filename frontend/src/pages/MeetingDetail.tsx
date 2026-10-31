import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ActionCard, ConflictCard, DecisionCard } from "../components/review";
import { Badge, Card, Empty, ErrorBox, Loading, PageHeader, StatusBadge } from "../components/ui";
import { post } from "../lib/api";
import { useAction, useApp, useData } from "../lib/app";
import { fmtDate, fmtDateTime, titleCase } from "../lib/format";
import type { Action, Conflict, Decision, Meeting } from "../lib/types";

type Review = { meeting: Meeting; decisions: Decision[]; actions: Action[]; conflicts: Conflict[]; ai_run: { provider: string; model: string | null; corrections: string[]; warnings: string[] } | null };

export default function MeetingDetail() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "transcript" ? "transcript" : "review";
  const { isReviewer, status } = useApp();
  const { data, error, loading, reload } = useData<Review>(`/api/meetings/${id}/review`, [id]);
  const { run, busy } = useAction();
  const [highlight, setHighlight] = useState<number[]>([]);

  const evidenceMap = useMemo(() => {
    const m = new Map<number, string[]>();
    data?.decisions.forEach((d) => d.evidence_idx.forEach((i) => m.set(i, [...(m.get(i) ?? []), `D${d.id}`])));
    data?.actions.forEach((a) => a.evidence_idx.forEach((i) => m.set(i, [...(m.get(i) ?? []), `A${a.id}`])));
    return m;
  }, [data]);

  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return loading ? <Loading /> : null;
  const m = data.meeting;
  const openConflicts = data.conflicts.filter((c) => c.status === "open" || c.status === "needs_review");
  const process = (engine: "default" | "demo") =>
    run("process", () => post<{ decisions: number; actions: number; conflicts: number }>(`/api/meetings/${m.id}/process`, { engine }),
      (r) => `Extracted ${r.decisions} decisions and ${r.actions} tasks; ${r.conflicts} conflict(s) with earlier meetings.`);

  return (
    <>
      <PageHeader
        eyebrow={`Meeting · ${fmtDate(m.meeting_date)}`}
        title={m.title}
        subtitle={<span className="flex flex-wrap items-center gap-2">
          <StatusBadge status={m.status} />
          <span>{titleCase(m.source_type)}{m.source_filename ? ` · ${m.source_filename}` : ""}{m.dictated_by ? ` · dictated by ${m.dictated_by}` : ""}</span>
          <span className="text-ink-faint">·</span><span>{m.participants.join(", ") || "no speakers identified"}</span>
        </span>}
        actions={<div className="inline-flex rounded-md border border-line-strong bg-surface p-0.5">
          {(["review", "transcript"] as const).map((t) => (
            <button key={t} onClick={() => setParams(t === "review" ? {} : { tab: t })} className={`rounded px-3 py-1.5 text-[13px] ${tab === t ? "bg-accent text-white" : "text-ink-soft"}`}>
              {t === "review" ? `Extraction (${data.decisions.length + data.actions.length})` : `Transcript (${m.segments.length})`}
            </button>
          ))}
        </div>}
      />

      {m.status !== "processed" && (
        <div className={`card mb-6 flex flex-wrap items-center justify-between gap-3 px-4 py-3 ${m.status === "failed" ? "border-danger/40 bg-danger-tint/30" : ""}`}>
          <div>
            {m.status === "failed" ? <><b className="text-danger">Processing failed.</b> {m.process_error} Nothing was stored, so it is safe to retry.</>
              : m.status === "processing" ? "Processing…" : "This transcript has been stored but not analysed yet."}
          </div>
          {isReviewer && m.status !== "processing" && (
            <div className="flex gap-2">
              <button className="btn-primary" disabled={!!busy} onClick={() => process("default")}>{busy ? "Processing…" : status?.ai.is_real_ai ? `Process with ${status.ai.model}` : "Process meeting"}</button>
              {m.status === "failed" && status?.ai.is_real_ai && (
                <button className="btn-secondary" disabled={!!busy} onClick={() => process("demo")} title="Uses the deterministic rules engine; results will be labelled demo-rules">Use demo engine instead</button>
              )}
            </div>
          )}
        </div>
      )}

      {tab === "transcript" ? (
        <div className="card">
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5 text-[12px] text-ink-muted">
            <span>Original transcript, as stored. Highlighted lines are evidence for extracted records.</span>
            <span className="font-mono">{m.source_bytes.toLocaleString()} bytes · uploaded {fmtDateTime(m.uploaded_at)}</span>
          </div>
          <ol className="divide-y divide-line">
            {m.segments.map((s) => {
              const refs = evidenceMap.get(s.idx);
              return (
                <li key={s.idx} id={`seg-${s.idx}`} className={`grid grid-cols-[150px_1fr_auto] gap-4 px-4 py-2.5 ${refs ? "bg-accent-tint/40" : ""} ${highlight.includes(s.idx) ? "ring-2 ring-inset ring-accent" : ""}`}>
                  <div className="text-[12px]">
                    <div className="font-medium text-ink">{s.speaker ?? <i className="text-ink-muted">Unattributed</i>}</div>
                    <div className="font-mono text-[11px] text-ink-muted">{s.timestamp ?? `#${s.idx + 1}`}</div>
                  </div>
                  <p className="font-serif text-[15.5px] leading-relaxed">{s.text}</p>
                  <div className="flex flex-col items-end gap-1">{refs?.map((r) => <Badge key={r} tone={r.startsWith("D") ? "accent" : "info"}>{r}</Badge>)}</div>
                </li>
              );
            })}
          </ol>
        </div>
      ) : m.status !== "processed" ? (
        <Empty title="No extraction yet">Process the meeting to extract decisions and action items.</Empty>
      ) : (
        <div className="space-y-6">
          {data.ai_run && (
            <div className="flex flex-wrap items-center gap-2 text-[12px] text-ink-muted">
              <Badge tone={data.ai_run.provider === "demo-rules" ? "warn" : "info"}>{data.ai_run.provider === "demo-rules" ? "Extracted by demo rules engine" : `Extracted by ${data.ai_run.model ?? data.ai_run.provider}`}</Badge>
              <span>Every record cites the transcript lines it came from. Inferred owners and dates are labelled.</span>
            </div>
          )}
          {data.ai_run && data.ai_run.corrections.length > 0 && (
            <Card title="Self-corrections understood">
              <ul className="list-disc space-y-1 pl-5 text-ink-soft">{data.ai_run.corrections.map((c) => <li key={c}>{c}</li>)}</ul>
            </Card>
          )}
          {data.ai_run && data.ai_run.warnings.length > 0 && (
            <div className="rounded-md border border-warn/30 bg-warn-tint px-4 py-2 text-[13px] text-warn">{data.ai_run.warnings.map((w) => <div key={w}>{w}</div>)}</div>
          )}
          {openConflicts.length > 0 && (
            <section>
              <h2 className="mb-2 font-serif text-xl font-semibold text-danger">Conflicts with earlier meetings ({openConflicts.length})</h2>
              <p className="mb-3 text-ink-muted">Memory says otherwise. These need a human decision before anything changes.</p>
              <div className="space-y-4">{openConflicts.map((c) => <ConflictCard key={c.id} c={c} />)}</div>
            </section>
          )}
          <section>
            <h2 className="mb-3 font-serif text-xl font-semibold">Decisions ({data.decisions.length})</h2>
            {data.decisions.length === 0 ? <p className="text-ink-muted">No decisions were found in this meeting.</p> : (
              <div className="space-y-3">{data.decisions.map((d) => <div key={d.id} onMouseEnter={() => setHighlight(d.evidence_idx)} onMouseLeave={() => setHighlight([])}><DecisionCard d={d} segments={m.segments} /></div>)}</div>
            )}
          </section>
          <section>
            <h2 className="mb-3 font-serif text-xl font-semibold">Action items ({data.actions.length})</h2>
            {data.actions.length === 0 ? <p className="text-ink-muted">No action items were found in this meeting.</p> : (
              <div className="space-y-3">{data.actions.map((a) => <ActionCard key={a.id} a={a} segments={m.segments} />)}</div>
            )}
          </section>
          {data.conflicts.length > openConflicts.length && (
            <section>
              <h2 className="mb-3 font-serif text-xl font-semibold">Resolved conflicts</h2>
              <div className="space-y-3">{data.conflicts.filter((c) => !openConflicts.includes(c)).map((c) => <ConflictCard key={c.id} c={c} compact />)}</div>
            </section>
          )}
          <p className="text-[12px] text-ink-muted">Need the source? <Link className="link" to="?tab=transcript">Open the transcript</Link>.</p>
        </div>
      )}
    </>
  );
}
