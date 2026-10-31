import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { post } from "../lib/api";
import { useAction, useApp, useData } from "../lib/app";
import { fmtDate, fmtDateTime } from "../lib/format";
import type { Notification } from "../lib/types";

type Counts = { counts: { pending_approvals: number; open_conflicts: number; overdue: number } };

const NAV: { group: string; items: { to: string; label: string; badge?: "approvals" | "conflicts" | "overdue" }[] }[] = [
  { group: "Overview", items: [{ to: "/", label: "Dashboard" }] },
  { group: "Capture", items: [{ to: "/meetings/new", label: "New meeting" }, { to: "/meetings", label: "Meetings" }] },
  { group: "Memory", items: [{ to: "/memory", label: "Decision memory" }, { to: "/conflicts", label: "Conflicts", badge: "conflicts" }] },
  {
    group: "Execution",
    items: [
      { to: "/approvals", label: "Approval queue", badge: "approvals" },
      { to: "/actions", label: "Action items" },
      { to: "/reminders", label: "Reminders", badge: "overdue" },
      { to: "/digest", label: "Weekly digest" },
    ],
  },
  { group: "Workspace", items: [{ to: "/projects", label: "Projects" }, { to: "/integrations", label: "Integrations" }, { to: "/audit", label: "Audit history" }] },
];

export default function Layout() {
  const { user, logout, projects, projectId, setProjectId, status, version } = useApp();
  const loc = useLocation();
  const { data: dash } = useData<Counts>(projectId ? `/api/dashboard?project_id=${projectId}` : null, [projectId]);
  const counts = dash?.counts;
  const badge = (k?: string) => {
    if (!counts || !k) return null;
    const n = k === "approvals" ? counts.pending_approvals : k === "conflicts" ? counts.open_conflicts : counts.overdue;
    if (!n) return null;
    return <span className={`ml-auto rounded px-1.5 font-mono text-[11px] ${k === "approvals" ? "bg-info-tint text-info" : "bg-danger-tint text-danger"}`}>{n}</span>;
  };
  void version;

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-[244px] shrink-0 flex-col border-r border-line bg-surface">
        <div className="flex items-center gap-2.5 border-b border-line px-5 py-4">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-accent font-serif text-[15px] font-semibold text-white">L</div>
          <div className="leading-tight">
            <div className="font-serif text-[17px] font-semibold">Ledger</div>
            <div className="text-[11px] text-ink-muted">Meeting-to-execution</div>
          </div>
        </div>
        <div className="border-b border-line px-4 py-3">
          <label className="label mb-1 block" htmlFor="project">Project</label>
          <select id="project" className="input py-1.5 text-[13px]" value={projectId ?? ""} onChange={(e) => setProjectId(Number(e.target.value))}>
            {projects.length === 0 && <option value="">No projects</option>}
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <nav className="flex-1 overflow-y-auto px-3 py-3">
          {NAV.map((g) => (
            <div key={g.group} className="mb-3">
              <div className="label px-2 pb-1">{g.group}</div>
              {g.items.map((it) => (
                <NavLink key={it.to} to={it.to} end={it.to === "/" || it.to === "/meetings"}
                  className={({ isActive }) => `flex items-center rounded-md px-2 py-1.5 text-[13.5px] transition ${isActive ? "bg-accent-tint font-medium text-accent" : "text-ink-soft hover:bg-ink/5 hover:text-ink"}`}>
                  {it.label}
                  {badge(it.badge)}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="space-y-2 border-t border-line px-4 py-3 text-[12px]">
          {status && (
            <>
              <ModeLine ok={status.ai.is_real_ai} label="AI" value={status.ai.is_real_ai ? status.ai.model ?? "Real AI" : "Demo engine"} title={status.ai.label} />
              <ModeLine ok={status.tracker.is_external && status.tracker.configured} label="Tracker" value={status.tracker.is_external ? status.tracker.label : "Simulated"} title={status.tracker.label} />
            </>
          )}
          <div className="flex items-center justify-between pt-1">
            <div className="min-w-0">
              <div className="truncate font-medium text-ink">{user?.name}</div>
              <div className="font-mono text-[10px] uppercase text-ink-muted">{user?.role}</div>
            </div>
            <button className="btn-ghost px-2 text-[12px]" onClick={logout}>Sign out</button>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="mx-auto w-full max-w-[1180px] flex-1 px-8 py-7">
          {projects.length === 0 && loc.pathname !== "/projects" ? <NoProjects /> : <Outlet />}
        </main>
      </div>
    </div>
  );
}

function ModeLine({ ok, label, value, title }: { ok: boolean; label: string; value: string; title: string }) {
  return (
    <div className="flex items-center gap-2" title={title}>
      <span className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-ok" : "bg-warn"}`} />
      <span className="label w-14">{label}</span>
      <span className="truncate text-ink-soft">{value}</span>
    </div>
  );
}

function TopBar() {
  const { status, isReviewer, refreshStatus } = useApp();
  const { run, busy } = useAction();
  const override = status?.clock.override;
  return (
    <div className="sticky top-0 z-20 border-b border-line bg-paper/90 backdrop-blur">
      {override && (
        <div className="flex items-center justify-center gap-3 bg-warn-tint px-4 py-1.5 text-[12.5px] text-warn">
          <span><b>Demo clock active:</b> the app is treating today as {fmtDate(override.slice(0, 10))}. Reminders and digests use this date.</span>
          {isReviewer && (
            <button className="underline underline-offset-2" disabled={busy === "clock"}
              onClick={() => run("clock", () => post("/api/system/clock", { date: null }).then(refreshStatus), "Back to real time")}>
              Return to real time
            </button>
          )}
        </div>
      )}
      <div className="flex h-12 items-center justify-end gap-3 px-8">
        {status && !status.ai.is_real_ai && (
          <span className="rounded border border-warn/30 bg-warn-tint px-2 py-0.5 text-[12px] text-warn" title={status.ai.label}>
            Demo mode: rule-based extraction, not an LLM
          </span>
        )}
        <Bell />
      </div>
    </div>
  );
}

function Bell() {
  const [open, setOpen] = useState(false);
  const { data, reload } = useData<{ unread: number; items: Notification[] }>("/api/notifications");
  const nav = useNavigate();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const t = setInterval(reload, 30_000);
    return () => clearInterval(t);
  }, [reload]);
  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const openItem = async (n: Notification) => {
    if (!n.read_at) await post(`/api/notifications/${n.id}/read`).catch(() => {});
    setOpen(false);
    reload();
    if (n.link) nav(n.link);
  };
  return (
    <div className="relative" ref={ref}>
      <button className="btn-secondary relative" onClick={() => setOpen((o) => !o)} aria-label="Notifications">
        Notifications
        {!!data?.unread && <span className="rounded bg-danger px-1.5 font-mono text-[11px] text-white">{data.unread}</span>}
      </button>
      {open && (
        <div className="card absolute right-0 top-10 z-30 w-[380px] overflow-hidden">
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <span className="text-[13px] font-semibold">Notifications</span>
            {!!data?.unread && <button className="link text-[12px]" onClick={() => post("/api/notifications/read-all").then(reload)}>Mark all read</button>}
          </div>
          <div className="max-h-[380px] overflow-y-auto">
            {!data?.items.length && <div className="px-4 py-6 text-center text-ink-muted">No notifications yet. Reminders appear here when deadlines approach.</div>}
            {data?.items.map((n) => (
              <button key={n.id} onClick={() => openItem(n)} className={`block w-full border-b border-line px-4 py-2.5 text-left hover:bg-paper ${n.read_at ? "" : "bg-info-tint/40"}`}>
                <div className="text-[13px] font-medium">{n.title}</div>
                <div className="text-[12px] text-ink-muted">{n.body}</div>
                <div className="mt-0.5 font-mono text-[10px] text-ink-faint">{fmtDateTime(n.created_at)}</div>
              </button>
            ))}
          </div>
          <Link to="/reminders" onClick={() => setOpen(false)} className="block px-4 py-2 text-center text-[12px] link">All reminders →</Link>
        </div>
      )}
    </div>
  );
}

function NoProjects() {
  return (
    <div className="card mx-auto mt-10 max-w-lg p-8 text-center">
      <h1 className="font-serif text-2xl font-semibold">You are not in any project yet</h1>
      <p className="mt-2 text-ink-muted">Ask a manager to add you, or create one if you are a manager.</p>
      <Link className="btn-primary mt-4" to="/projects">Go to projects</Link>
    </div>
  );
}
