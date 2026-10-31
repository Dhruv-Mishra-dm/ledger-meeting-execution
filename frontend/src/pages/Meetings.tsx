import { Link } from "react-router-dom";
import { Badge, Empty, ErrorBox, Loading, PageHeader, StatusBadge } from "../components/ui";
import { useApp, useData } from "../lib/app";
import { fmtDate, fmtDateTime, titleCase } from "../lib/format";
import type { MeetingBrief } from "../lib/types";

export default function Meetings() {
  const { projectId, project } = useApp();
  const { data, error, loading, reload } = useData<MeetingBrief[]>(projectId ? `/api/meetings?project_id=${projectId}` : null, [projectId]);
  return (
    <>
      <PageHeader eyebrow={project?.name} title="Meetings" subtitle="Every meeting is stored with its transcript, speakers and source, and is compared with what earlier meetings decided."
        actions={<Link to="/meetings/new" className="btn-primary">New meeting</Link>} />
      {error && <ErrorBox message={error} onRetry={reload} />}
      {!data && loading && <Loading />}
      {data && data.length === 0 && <Empty title="No meetings yet" action={<Link to="/meetings/new" className="btn-primary">Capture a meeting</Link>}>Dictate with Wispr Flow or upload a TXT, DOCX or PDF transcript.</Empty>}
      {data && data.length > 0 && (
        <div className="card overflow-hidden">
          <table className="w-full text-left">
            <thead className="border-b border-line bg-paper">
              <tr className="label">
                <th className="px-4 py-2.5 font-normal">Meeting</th>
                <th className="px-4 py-2.5 font-normal">Date</th>
                <th className="px-4 py-2.5 font-normal">Source</th>
                <th className="px-4 py-2.5 font-normal text-right">Decisions</th>
                <th className="px-4 py-2.5 font-normal text-right">Tasks</th>
                <th className="px-4 py-2.5 font-normal">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.map((m) => (
                <tr key={m.id} className="hover:bg-paper">
                  <td className="px-4 py-3">
                    <Link to={`/meetings/${m.id}`} className="font-medium hover:underline">{m.title}</Link>
                    <div className="text-[12px] text-ink-muted">{m.participants.join(", ") || "No speakers identified"}</div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">{fmtDate(m.meeting_date)}</td>
                  <td className="px-4 py-3 text-[12.5px]">
                    {titleCase(m.source_type)}
                    <div className="font-mono text-[11px] text-ink-muted">{m.source_filename ?? (m.dictated_by ? `by ${m.dictated_by}` : "")} · {fmtDateTime(m.uploaded_at)}</div>
                  </td>
                  <td className="px-4 py-3 text-right font-mono">{m.decisions ?? 0}</td>
                  <td className="px-4 py-3 text-right font-mono">{m.actions ?? 0}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1"><StatusBadge status={m.status} />{!!m.open_conflicts && <Badge tone="danger">{m.open_conflicts} conflict{m.open_conflicts > 1 ? "s" : ""}</Badge>}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
