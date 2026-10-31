import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ConflictCard } from "../components/review";
import { Empty, ErrorBox, Loading, PageHeader } from "../components/ui";
import { useApp, useData } from "../lib/app";
import type { AuditEntry, Conflict } from "../lib/types";
import { fmtDateTime, titleCase } from "../lib/format";

export default function Conflicts() {
  const { projectId, project } = useApp();
  const [filter, setFilter] = useState<"unresolved" | "all">("unresolved");
  const { data, error, loading, reload } = useData<Conflict[]>(projectId ? `/api/conflicts?project_id=${projectId}${filter === "unresolved" ? "&status=unresolved" : ""}` : null, [projectId, filter]);
  return (
    <>
      <PageHeader eyebrow={project?.name} title="Conflict review"
        subtitle="When a meeting contradicts what the project already decided, it lands here. A person decides; the system never overwrites a decision on its own."
        actions={<div className="inline-flex rounded-md border border-line-strong bg-surface p-0.5">
          {(["unresolved", "all"] as const).map((f) => <button key={f} onClick={() => setFilter(f)} className={`rounded px-3 py-1.5 text-[13px] ${filter === f ? "bg-accent text-white" : "text-ink-soft"}`}>{f === "unresolved" ? "Needs attention" : "All, incl. resolved"}</button>)}
        </div>} />
      {error && <ErrorBox message={error} onRetry={reload} />}
      {!data && loading && <Loading />}
      {data && data.length === 0 && (
        <Empty title={filter === "unresolved" ? "No open conflicts" : "No conflicts recorded"}>
          {filter === "unresolved" ? "Every meeting so far is consistent with the project's memory, or its conflicts were resolved." : "Conflicts appear when a later meeting contradicts an earlier decision or task."}
        </Empty>
      )}
      <div className="space-y-4">{data?.map((c) => <div key={c.id}><ConflictCard c={c} /><Link to={`/conflicts/${c.id}`} className="link mt-1 inline-block text-[12px]">Details and history →</Link></div>)}</div>
    </>
  );
}

export function ConflictDetail() {
  const { id } = useParams();
  const { projectId } = useApp();
  const { data, error, loading, reload } = useData<Conflict>(`/api/conflicts/${id}`, [id]);
  const { data: log } = useData<AuditEntry[]>(projectId ? `/api/audit?project_id=${projectId}&item_type=conflict&item_id=${id}` : null, [id, projectId]);
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return loading ? <Loading /> : null;
  return (
    <>
      <PageHeader eyebrow="Conflict review" title={`Conflict #${data.id}`} subtitle={<Link className="link" to="/conflicts">← All conflicts</Link>} />
      <ConflictCard c={data} />
      <section className="card mt-6">
        <div className="border-b border-line px-4 py-3 text-[13px] font-semibold">Resolution history</div>
        <ul className="divide-y divide-line">
          {!log?.length && <li className="px-4 py-3 text-ink-muted">No actions recorded yet.</li>}
          {log?.map((e) => (
            <li key={e.id} className="flex flex-wrap items-baseline gap-3 px-4 py-2.5 text-[13px]">
              <span className="font-mono text-[11px] text-ink-muted">{fmtDateTime(e.created_at)}</span>
              <b>{e.actor}</b> {titleCase(e.action)} <span className="text-ink-muted">{e.previous_state} → {e.new_state}</span>
              {e.comment && <span className="text-ink-soft">“{e.comment}”</span>}
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
