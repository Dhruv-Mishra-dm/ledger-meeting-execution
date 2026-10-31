import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Empty, ErrorBox, Loading, PageHeader, StatusBadge } from "../components/ui";
import { useApp, useData } from "../lib/app";
import { displayValue, fmtDate, titleCase } from "../lib/format";
import type { MemoryGroup } from "../lib/types";

export default function Memory() {
  const { projectId, project } = useApp();
  const { data, error, loading, reload } = useData<MemoryGroup[]>(projectId ? `/api/decisions/memory?project_id=${projectId}` : null, [projectId]);
  const [q, setQ] = useState("");
  const groups = (data ?? []).filter((g) => !q || g.topic.includes(q.toLowerCase()) || g.history.some((d) => d.statement.toLowerCase().includes(q.toLowerCase())));

  return (
    <>
      <PageHeader eyebrow={project?.name} title="Decision memory"
        subtitle="What this project has decided, topic by topic, with every earlier version kept. New meetings are compared against the current state shown here."
        actions={<input className="input w-64" placeholder="Search topics or decisions" value={q} onChange={(e) => setQ(e.target.value)} />} />
      {error && <ErrorBox message={error} onRetry={reload} />}
      {!data && loading && <Loading />}
      {data && data.length === 0 && <Empty title="Memory is empty" action={<Link className="btn-primary" to="/meetings/new">Capture a meeting</Link>}>Decisions appear here as soon as a meeting is processed. Approved ones become the project's current state.</Empty>}
      <div className="space-y-4">
        {groups.map((g) => (
          <section key={g.topic} className="card">
            <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3">
              <h2 className="font-serif text-lg font-semibold">{titleCase(g.topic)}</h2>
              {g.open_conflicts > 0 && <Link to="/conflicts"><Badge tone="danger">{g.open_conflicts} open conflict</Badge></Link>}
              <span className="ml-auto font-mono text-[11px] text-ink-muted">{g.history.length} version{g.history.length > 1 ? "s" : ""} · last changed {fmtDate(g.last_changed)}</span>
            </div>
            <div className="grid gap-0 md:grid-cols-[260px_1fr]">
              <div className="border-b border-line px-5 py-4 md:border-b-0 md:border-r">
                <div className="label">Current state</div>
                {g.current ? (
                  <>
                    <div className="mt-1 font-serif text-[22px] font-semibold leading-tight">{g.current.value ? displayValue(g.current.value, g.current.value_kind) : g.current.statement}</div>
                    <div className="mt-1 text-[12px] text-ink-muted">Confirmed · {g.current.meeting_title}, {fmtDate(g.current.meeting_date)}</div>
                  </>
                ) : (
                  <div className="mt-1 text-ink-muted">Nothing confirmed yet{g.pending.length ? " — awaiting review" : ""}.</div>
                )}
              </div>
              <ol className="relative px-5 py-4">
                {g.history.map((d, i) => (
                  <li key={d.id} className="relative flex gap-4 pb-4 last:pb-0">
                    <div className="flex flex-col items-center">
                      <span className={`mt-1.5 h-2.5 w-2.5 rounded-full border-2 ${d.status === "confirmed" ? "border-ok bg-ok" : d.status === "superseded" || d.status === "rejected" ? "border-line-strong bg-surface" : "border-info bg-info-tint"}`} />
                      {i < g.history.length - 1 && <span className="mt-1 w-px flex-1 bg-line" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`font-medium ${d.status === "superseded" || d.status === "rejected" ? "text-ink-muted line-through decoration-1" : ""}`}>{d.statement}</span>
                        <StatusBadge status={d.status} />
                      </div>
                      <div className="mt-0.5 font-mono text-[11px] text-ink-muted">
                        <Link to={`/meetings/${d.meeting_id}`} className="hover:underline">{d.meeting_title}</Link> · {fmtDate(d.meeting_date)} · {d.speaker ?? "speaker not identified"} · #{d.id}
                        {d.superseded_by_id && ` · superseded by #${d.superseded_by_id}`}
                        {d.related_decision_id && ` · reaffirms #${d.related_decision_id}`}
                      </div>
                      <blockquote className="quote mt-1.5 text-[14px]">“{d.evidence_excerpt}”</blockquote>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
