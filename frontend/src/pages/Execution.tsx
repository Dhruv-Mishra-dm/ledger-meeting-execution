import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ActionCard, ConflictCard, DecisionCard, PublicationBadge } from "../components/review";
import { Badge, Card, Due, Empty, ErrorBox, Loading, OriginTag, PageHeader, StatusBadge } from "../components/ui";
import { post } from "../lib/api";
import { useAction, useApp, useData } from "../lib/app";
import { fmtDate, fmtDateTime } from "../lib/format";
import type { Action, Conflict, Decision, Reminder } from "../lib/types";

// ------------------------------------------------------------------ approval queue

type Queue = { decisions: Decision[]; actions: Action[]; ready_to_publish: Action[]; conflicts: Conflict[] };

export function Approvals() {
  const { projectId, project, isReviewer } = useApp();
  const { data, error, loading, reload } = useData<Queue>(projectId ? `/api/approvals/queue?project_id=${projectId}` : null, [projectId]);
  const total = data ? data.decisions.length + data.actions.length + data.ready_to_publish.length + data.conflicts.length : 0;
  return (
    <>
      <PageHeader eyebrow={project?.name} title="Approval queue"
        subtitle="Everything the AI extracted waits here until a person approves, edits or rejects it. Nothing reaches the tracker without approval — enforced by the server, not just this screen." />
      {!isReviewer && <p className="mb-4 rounded-md bg-info-tint px-4 py-2 text-[13px] text-info">You can view the queue. Only managers can approve, reject or publish.</p>}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {!data && loading && <Loading />}
      {data && total === 0 && <Empty title="All caught up">No decisions, tasks or conflicts are waiting for review.</Empty>}
      {data && total > 0 && (
        <div className="space-y-8">
          {data.conflicts.length > 0 && <QueueSection title="1 · Resolve conflicts first" hint="Conflicting decisions cannot be confirmed until resolved.">{data.conflicts.map((c) => <ConflictCard key={c.id} c={c} />)}</QueueSection>}
          {data.decisions.length > 0 && <QueueSection title="2 · Confirm decisions" hint="Confirmed decisions become the project's memory.">{data.decisions.map((d) => <DecisionCard key={d.id} d={d} showMeeting />)}</QueueSection>}
          {data.actions.length > 0 && <QueueSection title="3 · Approve tasks" hint="Check owner and deadline. Inferred values are labelled.">{data.actions.map((a) => <ActionCard key={a.id} a={a} showMeeting />)}</QueueSection>}
          {data.ready_to_publish.length > 0 && <QueueSection title="4 · Publish approved tasks" hint="Preview the exact payload before it is sent.">{data.ready_to_publish.map((a) => <ActionCard key={a.id} a={a} showMeeting />)}</QueueSection>}
        </div>
      )}
    </>
  );
}

function QueueSection({ title, hint, children }: { title: string; hint: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="font-serif text-xl font-semibold">{title}</h2>
      <p className="mb-3 text-ink-muted">{hint}</p>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

// ------------------------------------------------------------------ action items

const FILTERS: Record<string, string> = { open: "approved", review: "proposed", done: "done", all: "" };

export function Actions() {
  const { projectId, project, today, user } = useApp();
  const [params] = useSearchParams();
  const [filter, setFilter] = useState<keyof typeof FILTERS>("all");
  const [mine, setMine] = useState(false);
  const [selected, setSelected] = useState<number | null>(params.get("focus") ? Number(params.get("focus")) : null);
  const qs = `project_id=${projectId}${FILTERS[filter] ? `&status=${FILTERS[filter]}` : ""}${mine && user ? `&owner_id=${user.id}` : ""}`;
  const { data, error, loading, reload } = useData<Action[]>(projectId ? `/api/actions?${qs}` : null, [qs]);
  const current = data?.find((a) => a.id === selected);
  return (
    <>
      <PageHeader eyebrow={project?.name} title="Action items" subtitle="Every task extracted from meetings, with owner, deadline, source evidence and tracker status."
        actions={<>
          <label className="flex items-center gap-2 text-[13px]"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> Only mine</label>
          <div className="inline-flex rounded-md border border-line-strong bg-surface p-0.5">
            {Object.keys(FILTERS).map((f) => <button key={f} onClick={() => setFilter(f)} className={`rounded px-3 py-1.5 text-[13px] capitalize ${filter === f ? "bg-accent text-white" : "text-ink-soft"}`}>{f === "review" ? "Awaiting approval" : f}</button>)}
          </div>
        </>} />
      {error && <ErrorBox message={error} onRetry={reload} />}
      {!data && loading && <Loading />}
      {data && data.length === 0 && <Empty title="No tasks here">Tasks appear when meetings are processed.</Empty>}
      {data && data.length > 0 && (
        <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
          <div className="card overflow-hidden">
            <table className="w-full text-left">
              <thead className="border-b border-line bg-paper"><tr className="label">
                <th className="px-4 py-2.5 font-normal">Task</th><th className="px-4 py-2.5 font-normal">Owner</th><th className="px-4 py-2.5 font-normal">Due</th><th className="px-4 py-2.5 font-normal">Status</th>
              </tr></thead>
              <tbody className="divide-y divide-line">
                {data.map((a) => (
                  <tr key={a.id} onClick={() => setSelected(a.id)} className={`cursor-pointer hover:bg-paper ${selected === a.id ? "bg-accent-tint/50" : ""}`}>
                    <td className="px-4 py-2.5"><div className={`font-medium ${a.status === "superseded" || a.status === "rejected" ? "text-ink-muted line-through" : ""}`}>{a.title}</div><div className="font-mono text-[11px] text-ink-muted">{a.meeting_title} · {fmtDate(a.meeting_date, false)}</div></td>
                    <td className="px-4 py-2.5 text-[13px]">{a.owner_name ?? <span className="text-warn">Unassigned</span>}<div><OriginTag origin={a.owner_origin} kind="owner" /></div></td>
                    <td className="px-4 py-2.5 text-[13px]">{a.status === "done" ? <span className="text-ink-muted">{fmtDate(a.deadline)}</span> : <Due iso={a.deadline} today={today} />}</td>
                    <td className="px-4 py-2.5"><div className="flex flex-wrap gap-1"><StatusBadge status={a.status} /><PublicationBadge a={a} /></div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="lg:sticky lg:top-16 lg:self-start">{current ? <ActionCard a={current} showMeeting /> : <div className="card p-6 text-center text-ink-muted">Select a task to see its evidence and actions.</div>}</div>
        </div>
      )}
    </>
  );
}

// ------------------------------------------------------------------ reminders

type Rem = { as_of: string; reminders: Reminder[]; overdue: Action[]; due_soon: Action[] };
const KIND: Record<string, { label: string; tone: string }> = { due_24h: { label: "Due in 24h", tone: "warn" }, due_today: { label: "Due today", tone: "warn" }, overdue: { label: "Overdue", tone: "danger" } };

export function Reminders() {
  const { projectId, project, isReviewer, refreshStatus, status, today } = useApp();
  const { data, error, loading, reload } = useData<Rem>(projectId ? `/api/reminders?project_id=${projectId}` : null, [projectId]);
  const { run, busy } = useAction();
  const [day, setDay] = useState("");
  return (
    <>
      <PageHeader eyebrow={project?.name} title="Reminders"
        subtitle="Owners are reminded 24 hours before a deadline, on the due date, and when a task becomes overdue. Completed tasks get no more reminders. Records are stored, so a restart never duplicates them."
        actions={isReviewer && <button className="btn-secondary" disabled={!!busy} onClick={() => run("scan", () => post<{ created: number }>("/api/reminders/scan"), (r) => `${r.created} new reminder(s)`)}>Run reminder check now</button>} />
      {isReviewer && (
        <Card title="Demo clock" className="mb-6">
          <div className="flex flex-wrap items-end gap-3">
            <p className="max-w-xl text-[13px] text-ink-soft">The scenario's deadlines are in November 2026. Set the app's date to see reminders fire without waiting. A banner stays visible while this is active, and real time is used otherwise.</p>
            <input type="date" className="input w-44" value={day} onChange={(e) => setDay(e.target.value)} />
            <button className="btn-primary" disabled={!day || !!busy} onClick={() => run("clock", () => post("/api/system/clock", { date: day }).then(refreshStatus), `App date set to ${fmtDate(day)}`)}>Set app date</button>
            {status?.clock.override && <button className="btn-ghost" disabled={!!busy} onClick={() => run("clock", () => post("/api/system/clock", { date: null }).then(refreshStatus), "Back to real time")}>Use real time</button>}
          </div>
        </Card>
      )}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {!data && loading && <Loading />}
      {data && (
        <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
          <Card title={`Needs attention · as of ${fmtDate(data.as_of)}`} padded={false}>
            {data.overdue.length + data.due_soon.length === 0 ? <p className="px-4 py-4 text-ink-muted">Nothing overdue or due within a day.</p> : (
              <ul className="divide-y divide-line">
                {[...data.overdue, ...data.due_soon].map((a) => (
                  <li key={a.id} className="flex items-center justify-between gap-3 px-4 py-2.5">
                    <div><Link to={`/actions?focus=${a.id}`} className="font-medium hover:underline">{a.title}</Link><div className="text-[12px] text-ink-muted">{a.owner_name ?? "Unassigned"}</div></div>
                    <Due iso={a.deadline} today={today} />
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Reminder log" padded={false}>
            {data.reminders.length === 0 ? <p className="px-4 py-4 text-ink-muted">No reminders generated yet. They are created automatically every 5 minutes for approved tasks with deadlines.</p> : (
              <ul className="divide-y divide-line">
                {data.reminders.map((r) => (
                  <li key={r.id} className={`px-4 py-2.5 ${r.status === "dismissed" ? "opacity-60" : ""}`}>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={KIND[r.kind]?.tone}>{KIND[r.kind]?.label ?? r.kind}</Badge>
                      <span className="font-medium">{r.action.title}</span>
                      {r.status === "dismissed" && <Badge tone="muted">dismissed</Badge>}
                    </div>
                    <div className="mt-0.5 font-mono text-[11px] text-ink-muted">to {r.owner_name ?? "unassigned (managers)"} · due {fmtDate(r.due_date)} · created {fmtDateTime(r.created_at)}</div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
