import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Badge, Card, Empty, ErrorBox, Field, Loading, PageHeader, StatusBadge } from "../components/ui";
import { post } from "../lib/api";
import { useAction, useApp, useData } from "../lib/app";
import { fmtDate, fmtDateTime, titleCase } from "../lib/format";
import type { AuditEntry, User } from "../lib/types";

// ------------------------------------------------------------------ weekly digest

type DigestItem = { id: number; title: string; status: string; deadline: string | null; meeting: string; external_url: string | null; completed_at: string | null };
type DigestData = {
  person: { id: number; name: string }; week_start: string; week_end: string; as_of: string; summary: string;
  completed: DigestItem[]; pending: DigestItem[]; upcoming: DigestItem[]; overdue: DigestItem[]; awaiting_approval: DigestItem[];
  decisions: { id: number; statement: string; status: string; meeting: string; date: string }[];
  conflicts: { id: number; category: string; explanation: string; status: string }[]; source: string;
};

export function Digest() {
  const { projectId, project, user, isReviewer } = useApp();
  const { data: people } = useData<User[]>(projectId ? `/api/projects/${projectId}/people` : null, [projectId]);
  const [personId, setPersonId] = useState<number | null>(null);
  const [week, setWeek] = useState("");
  useEffect(() => {
    if (!people?.length) return;
    setPersonId((cur) => cur ?? (isReviewer ? people.find((p) => p.role === "member")?.id ?? people[0].id : user!.id));
  }, [people, isReviewer, user]);
  const { data, error, loading, reload } = useData<DigestData>(personId && projectId ? `/api/digest/${personId}?project_id=${projectId}${week ? `&week_start=${week}` : ""}` : null, [personId, projectId, week]);
  const list = (title: string, items: DigestItem[], empty: string, tone?: string) => (
    <Card title={<span className="flex items-center gap-2">{title}<Badge tone={tone ?? "neutral"}>{items.length}</Badge></span>} padded={false}>
      {items.length === 0 ? <p className="px-4 py-3 text-ink-muted">{empty}</p> : (
        <ul className="divide-y divide-line">{items.map((a) => (
          <li key={a.id} className="flex items-baseline justify-between gap-3 px-4 py-2">
            <div className="min-w-0"><div className="truncate font-medium">{a.title}</div><div className="font-mono text-[11px] text-ink-muted">{a.meeting}</div></div>
            <div className="shrink-0 text-right text-[12.5px]">{a.completed_at ? `done ${fmtDate(a.completed_at.slice(0, 10), false)}` : a.deadline ? `due ${fmtDate(a.deadline, false)}` : "no deadline"}{a.external_url && <div><a className="link text-[11px]" href={a.external_url} target="_blank" rel="noreferrer">tracker ↗</a></div>}</div>
          </li>
        ))}</ul>
      )}
    </Card>
  );
  return (
    <>
      <PageHeader eyebrow={project?.name} title="Weekly digest" subtitle="A per-person summary built only from stored tasks, decisions and conflicts — generated on demand, and every Monday at 08:00."
        actions={<>
          {isReviewer ? (
            <select className="input w-48" value={personId ?? ""} onChange={(e) => setPersonId(Number(e.target.value))}>
              {people?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          ) : <span className="text-ink-muted">Your digest</span>}
          <input type="date" className="input w-44" title="Any day in the week" value={week} onChange={(e) => setWeek(e.target.value)} />
        </>} />
      {error && <ErrorBox message={error} onRetry={reload} />}
      {!data && loading && <Loading />}
      {data && (
        <div className="space-y-6">
          <article className="card px-6 py-5">
            <div className="label">Week of {fmtDate(data.week_start)} – {fmtDate(data.week_end)} · for {data.person.name}</div>
            <p className="mt-2 font-serif text-[20px] leading-snug">{data.summary}</p>
            <p className="mt-2 text-[12px] text-ink-muted">{data.source} As of {fmtDate(data.as_of)}. Email delivery is not configured; this is the in-app digest.</p>
          </article>
          <div className="grid gap-4 md:grid-cols-2">
            {list("Overdue", data.overdue, "Nothing overdue.", data.overdue.length ? "danger" : undefined)}
            {list("Due in the next 7 days", data.upcoming, "Nothing due this week.")}
            {list("Open tasks", data.pending, "No open tasks.")}
            {list("Completed this week", data.completed, "No tasks marked complete this week.", "ok")}
          </div>
          {data.awaiting_approval.length > 0 && list("Extracted, awaiting approval", data.awaiting_approval, "", "info")}
          <div className="grid gap-4 md:grid-cols-2">
            <Card title="Relevant decisions" padded={false}>
              {data.decisions.length === 0 ? <p className="px-4 py-3 text-ink-muted">No decisions involving this person in this period.</p> : (
                <ul className="divide-y divide-line">{data.decisions.map((d) => <li key={d.id} className="px-4 py-2"><div className="flex items-center gap-2"><span className={d.status === "superseded" ? "text-ink-muted line-through" : "font-medium"}>{d.statement}</span><StatusBadge status={d.status} /></div><div className="font-mono text-[11px] text-ink-muted">{d.meeting} · {fmtDate(d.date)}</div></li>)}</ul>
              )}
            </Card>
            <Card title="Unresolved conflicts" padded={false}>
              {data.conflicts.length === 0 ? <p className="px-4 py-3 text-ink-muted">None.</p> : (
                <ul className="divide-y divide-line">{data.conflicts.map((c) => <li key={c.id} className="px-4 py-2 text-[13px]"><Link to={`/conflicts/${c.id}`} className="link">#{c.id} {titleCase(c.category)}</Link><div className="text-ink-muted">{c.explanation}</div></li>)}</ul>
              )}
            </Card>
          </div>
        </div>
      )}
    </>
  );
}

// ------------------------------------------------------------------ projects

export function Projects() {
  const { projects, projectId, setProjectId, refreshProjects, isReviewer } = useApp();
  const { run, busy } = useAction();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const p = await run("create", () => post<{ id: number }>("/api/projects", { name, description }), "Project created");
    if (p) {
      await refreshProjects();
      setProjectId(p.id);
      setName("");
      setDescription("");
    }
  };
  return (
    <>
      <PageHeader title="Projects" subtitle="Each project has its own decision memory. Decisions in one project are never compared with another's." />
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-3">
          {projects.length === 0 && <Empty title="No projects">Create one to start capturing meetings.</Empty>}
          {projects.map((p) => (
            <div key={p.id} className={`card flex items-center justify-between gap-4 px-5 py-4 ${p.id === projectId ? "border-accent" : ""}`}>
              <div className="min-w-0">
                <div className="font-serif text-lg font-semibold">{p.name}</div>
                <div className="text-ink-muted">{p.description || "No description"}</div>
                <div className="mt-1 font-mono text-[11px] text-ink-muted">{p.meetings} meetings · {p.people} people · created {fmtDate(p.created_at.slice(0, 10))}</div>
              </div>
              {p.id === projectId ? <Badge tone="accent">Current</Badge> : <button className="btn-secondary" onClick={() => setProjectId(p.id)}>Switch</button>}
            </div>
          ))}
        </div>
        {isReviewer && (
          <form onSubmit={submit} className="card h-fit space-y-3 p-4">
            <div className="text-[13px] font-semibold">New project</div>
            <Field label="Name"><input className="input" value={name} onChange={(e) => setName(e.target.value)} required minLength={2} maxLength={120} /></Field>
            <Field label="Description"><textarea className="input" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
            <button className="btn-primary w-full" disabled={!!busy}>Create project</button>
          </form>
        )}
      </div>
    </>
  );
}

// ------------------------------------------------------------------ integrations

type Integrations = { active: { provider: string; label: string; is_external: boolean; configured: boolean; status: string; detail: string | null; workspace: string | null; last_checked_at: string | null } };

export function IntegrationsPage() {
  const { isReviewer, refreshStatus, status } = useApp();
  const { data, error, loading, reload } = useData<Integrations>("/api/integrations");
  const { run, busy } = useAction();
  const [result, setResult] = useState<{ ok: boolean; detail: string } | null>(null);
  const a = data?.active;
  return (
    <>
      <PageHeader title="Integrations" subtitle="Where approved tasks are published, and which AI engine processes meetings. Credentials live only in the backend's .env file and are never sent to the browser." />
      {error && <ErrorBox message={error} onRetry={reload} />}
      {!data && loading && <Loading />}
      {a && (
        <div className="space-y-6">
          <Card title="Task tracker">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2"><span className="font-serif text-xl font-semibold">{a.label}</span><Badge tone={a.is_external ? (a.status === "connected" ? "ok" : a.status === "error" ? "danger" : "info") : "warn"}>{a.is_external ? titleCase(a.status) : "Simulated"}</Badge></div>
                <p className="mt-1 max-w-2xl text-ink-soft">{a.is_external ? <>Approved tasks become GitHub issues in <b>{a.workspace ?? "the configured repository"}</b>, labelled with owner and due date, with a hidden marker that prevents duplicates.</> : <>The demo tracker records tasks inside Ledger only. It is labelled “simulated” everywhere and never claims an external task exists. Configure GitHub Issues below for real publishing.</>}</p>
                {a.last_checked_at && <p className="mt-1 font-mono text-[11px] text-ink-muted">Last checked {fmtDateTime(a.last_checked_at)}: {a.detail}</p>}
              </div>
              {isReviewer && <button className="btn-secondary" disabled={!!busy} onClick={() => run("check", () => post<{ ok: boolean; detail: string }>("/api/integrations/check"), (r) => (r.ok ? "Connection verified" : `Check failed: ${r.detail}`)).then((r) => { if (r) setResult(r); refreshStatus(); reload(); })}>Test connection</button>}
            </div>
            {result && <p className={`mt-3 rounded px-3 py-2 text-[13px] ${result.ok ? "bg-ok-tint text-ok" : "bg-danger-tint text-danger"}`}>{result.detail}</p>}
          </Card>
          <Card title="Set up GitHub Issues (about 3 minutes)">
            <ol className="list-decimal space-y-2 pl-5 text-ink-soft">
              <li>Create or pick a GitHub repository for the team's tasks, with Issues enabled.</li>
              <li>Go to GitHub → Settings → Developer settings → Fine-grained personal access tokens → <b>Generate new token</b>. Select only that repository and give <b>Issues: Read and write</b>.</li>
              <li>Open <code className="font-mono">backend/.env</code> and set:
                <pre className="mt-1 rounded bg-paper p-3 font-mono text-[12px] text-ink">TRACKER_PROVIDER=github{"\n"}GITHUB_TOKEN=github_pat_…{"\n"}GITHUB_REPO=your-name/your-repo{"\n"}# optional: map meeting names to GitHub logins{"\n"}GITHUB_ASSIGNEES=Rahul:rahul-gh,Priya:priya-gh</pre>
              </li>
              <li>Restart the backend, then press <b>Test connection</b> here.</li>
            </ol>
          </Card>
          <Card title="AI engine">
            <div className="flex items-center gap-2"><span className="font-serif text-xl font-semibold">{status?.ai.is_real_ai ? status.ai.model : "Demo rules engine"}</span><Badge tone={status?.ai.is_real_ai ? "ok" : "warn"}>{status?.ai.is_real_ai ? "Real AI" : "Demo mode"}</Badge></div>
            <p className="mt-1 max-w-2xl text-ink-soft">{status?.ai.label}. {status?.ai.is_real_ai ? "Every model response is schema-validated and checked against the transcript; invented owners and dates are removed." : "Set AI_PROVIDER=openai with AI_BASE_URL, AI_API_KEY and AI_MODEL in backend/.env to use Gemini or any OpenAI-compatible model."}</p>
          </Card>
        </div>
      )}
    </>
  );
}

// ------------------------------------------------------------------ audit

export function Audit() {
  const { projectId, project } = useApp();
  const [type, setType] = useState("");
  const { data, error, loading, reload } = useData<AuditEntry[]>(projectId ? `/api/audit?project_id=${projectId}${type ? `&item_type=${type}` : ""}` : null, [projectId, type]);
  return (
    <>
      <PageHeader eyebrow={project?.name} title="Audit history" subtitle="Every upload, extraction, approval, rejection, edit, conflict resolution and publication — who, when, and the state change."
        actions={<select className="input w-48" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">All events</option>{["meeting", "decision", "action", "conflict", "publication", "system"].map((t) => <option key={t} value={t}>{titleCase(t)}</option>)}
        </select>} />
      {error && <ErrorBox message={error} onRetry={reload} />}
      {!data && loading && <Loading />}
      {data && data.length === 0 && <Empty title="No events yet" />}
      {data && data.length > 0 && (
        <div className="card overflow-hidden">
          <table className="w-full text-left text-[13px]">
            <thead className="border-b border-line bg-paper"><tr className="label">
              <th className="px-4 py-2.5 font-normal">When</th><th className="px-4 py-2.5 font-normal">Who</th><th className="px-4 py-2.5 font-normal">Event</th><th className="px-4 py-2.5 font-normal">Change</th><th className="px-4 py-2.5 font-normal">Comment / details</th>
            </tr></thead>
            <tbody className="divide-y divide-line">
              {data.map((e) => (
                <tr key={e.id} className="align-top">
                  <td className="whitespace-nowrap px-4 py-2 font-mono text-[11px] text-ink-muted">{fmtDateTime(e.created_at)}</td>
                  <td className="px-4 py-2 font-medium">{e.actor}</td>
                  <td className="px-4 py-2">{titleCase(e.item_type)}{e.item_id ? ` #${e.item_id}` : ""} · {titleCase(e.action)}</td>
                  <td className="whitespace-nowrap px-4 py-2 font-mono text-[11px]">{e.previous_state || e.new_state ? `${e.previous_state ?? "—"} → ${e.new_state ?? "—"}` : ""}</td>
                  <td className="max-w-[360px] px-4 py-2 text-ink-soft">{e.comment && <div>“{e.comment}”</div>}{Object.keys(e.details ?? {}).length > 0 && <div className="truncate font-mono text-[11px] text-ink-muted" title={JSON.stringify(e.details)}>{JSON.stringify(e.details)}</div>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
