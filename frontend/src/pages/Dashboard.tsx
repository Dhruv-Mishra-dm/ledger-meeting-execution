import { Link } from "react-router-dom";
import { Badge, Card, ConflictStamp, Due, Empty, ErrorBox, Loading, PageHeader, Stat, StatusBadge, Value } from "../components/ui";
import { useApp, useData } from "../lib/app";
import { displayValue, fmtDate, titleCase } from "../lib/format";
import type { Action, Conflict, Decision, MeetingBrief } from "../lib/types";

type Dash = {
  as_of: string;
  counts: Record<string, number>;
  current_decisions: Decision[];
  recent_changes: { topic: string; from: Decision; to: Decision | null }[];
  open_conflicts: Conflict[];
  overdue: Action[];
  upcoming: Action[];
  my_tasks: Action[];
  recent_meetings: MeetingBrief[];
};

export default function Dashboard() {
  const { projectId, project, user, today } = useApp();
  const { data, error, loading, reload } = useData<Dash>(projectId ? `/api/dashboard?project_id=${projectId}` : null, [projectId]);
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return loading ? <Loading /> : null;
  const c = data.counts;

  return (
    <>
      <PageHeader
        eyebrow={project?.name}
        title={`Good to see you, ${user?.name}`}
        subtitle={`Status as of ${fmtDate(data.as_of)}. What was decided, what changed, and what needs a person.`}
        actions={<Link to="/meetings/new" className="btn-primary">Capture a meeting</Link>}
      />

      {c.meetings === 0 ? (
        <Empty title="No meetings yet" action={<Link to="/meetings/new" className="btn-primary">Dictate or upload the first meeting</Link>}>
          Start by dictating a meeting with Wispr Flow or uploading a transcript. Decisions you approve become this project's memory.
        </Empty>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <Stat label="Needs approval" value={c.pending_approvals} tone={c.pending_approvals ? "warn" : undefined} to="/approvals" hint="Decisions & tasks" />
            <Stat label="Open conflicts" value={c.open_conflicts} tone={c.open_conflicts ? "danger" : undefined} to="/conflicts" hint="Awaiting a human" />
            <Stat label="Overdue" value={c.overdue} tone={c.overdue ? "danger" : undefined} to="/reminders" hint="Approved tasks" />
            <Stat label="Due in 7 days" value={c.upcoming} to="/actions" />
            <Stat label="Confirmed decisions" value={c.confirmed} tone="ok" to="/memory" hint={`${c.meetings} meetings processed`} />
          </div>

          {data.open_conflicts.length > 0 && (
            <Card title="Conflicts that need attention" actions={<Link to="/conflicts" className="link text-[12px]">Review all →</Link>}>
              <ul className="divide-y divide-line">
                {data.open_conflicts.map((cf) => (
                  <li key={cf.id} className="flex items-start justify-between gap-4 py-3 first:pt-0 last:pb-0">
                    <div className="min-w-0">
                      <ConflictStamp category={cf.category} />
                      <p className="mt-2 text-ink-soft">{cf.explanation}</p>
                    </div>
                    <Link to={`/conflicts/${cf.id}`} className="btn-secondary shrink-0">Resolve</Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="What is decided" actions={<Link to="/memory" className="link text-[12px]">Decision memory →</Link>}>
              {data.current_decisions.length === 0 ? (
                <p className="text-ink-muted">No confirmed decisions yet. Approve extracted decisions to build memory.</p>
              ) : (
                <ul className="space-y-3">
                  {data.current_decisions.map((d) => (
                    <li key={d.id} className="flex items-baseline justify-between gap-3">
                      <div className="min-w-0">
                        <div className="label">{d.topic}</div>
                        <div className="truncate"><Value value={d.value} kind={d.value_kind} />{!d.value && d.statement}</div>
                      </div>
                      <span className="shrink-0 font-mono text-[11px] text-ink-muted">{d.meeting_title} · {fmtDate(d.meeting_date, false)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card title="What changed">
              {data.recent_changes.length === 0 ? (
                <p className="text-ink-muted">No decision has been superseded yet. When a later meeting changes a decision and a reviewer accepts it, it appears here.</p>
              ) : (
                <ul className="space-y-3">
                  {data.recent_changes.map((ch) => (
                    <li key={ch.from.id}>
                      <div className="label">{ch.topic}</div>
                      <div className="flex flex-wrap items-baseline gap-2">
                        <span className="text-ink-muted line-through decoration-danger/60">{displayValue(ch.from.value, ch.from.value_kind) || ch.from.statement}</span>
                        <span className="text-ink-faint">→</span>
                        <span className="font-semibold">{ch.to ? displayValue(ch.to.value, ch.to.value_kind) : "—"}</span>
                        {ch.to && <span className="font-mono text-[11px] text-ink-muted">{ch.to.meeting_title} · {fmtDate(ch.to.meeting_date, false)}</span>}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Who must do what" actions={<Link to="/actions" className="link text-[12px]">All tasks →</Link>} padded={false}>
              <TaskTable items={[...data.overdue, ...data.upcoming]} today={today} empty="Nothing due in the next 7 days." />
            </Card>
            <Card title="Recent meetings" actions={<Link to="/meetings" className="link text-[12px]">All meetings →</Link>} padded={false}>
              <ul className="divide-y divide-line">
                {data.recent_meetings.map((m) => (
                  <li key={m.id}>
                    <Link to={`/meetings/${m.id}`} className="flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-paper">
                      <div className="min-w-0">
                        <div className="truncate font-medium">{m.title}</div>
                        <div className="font-mono text-[11px] text-ink-muted">{fmtDate(m.meeting_date)} · {titleCase(m.source_type)} · {m.participants.length} people</div>
                      </div>
                      <StatusBadge status={m.status} />
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          </div>

          {data.my_tasks.length > 0 && (
            <Card title="My open tasks" padded={false}>
              <TaskTable items={data.my_tasks} today={today} empty="" />
            </Card>
          )}
        </div>
      )}
    </>
  );
}

function TaskTable({ items, today, empty }: { items: Action[]; today: string; empty: string }) {
  if (!items.length) return <p className="px-4 py-4 text-ink-muted">{empty}</p>;
  return (
    <table className="w-full text-left">
      <tbody className="divide-y divide-line">
        {items.map((a) => (
          <tr key={a.id}>
            <td className="px-4 py-2.5">
              <div className="font-medium">{a.title}</div>
              <div className="text-[12px] text-ink-muted">{a.owner_name ?? <Badge tone="warn">Unassigned</Badge>}</div>
            </td>
            <td className="px-4 py-2.5 text-right"><Due iso={a.deadline} today={today} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
