import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, patch, post } from "../lib/api";
import { useAction, useApp } from "../lib/app";
import { CATEGORY_LABEL, displayValue, fmtDate, fmtDateTime, pct, titleCase } from "../lib/format";
import type { Action, Conflict, Decision, Segment } from "../lib/types";
import { Badge, Confidence, ConflictStamp, Due, Evidence, Field, Modal, OriginTag, StatusBadge } from "./ui";

const segsFor = (idx: number[], segments?: Segment[]) => (segments ? segments.filter((s) => idx.includes(s.idx)) : undefined);

// ------------------------------------------------------------------ decisions

export function DecisionCard({ d, segments, showMeeting }: { d: Decision; segments?: Segment[]; showMeeting?: boolean }) {
  const { isReviewer } = useApp();
  const { run, busy } = useAction();
  const [edit, setEdit] = useState(false);
  const [comment, setComment] = useState<null | "comment" | "reject">(null);
  const reviewable = d.status === "proposed" || d.status === "under_review";
  return (
    <article className={`card p-4 ${d.status === "under_review" ? "border-danger/40" : ""}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="label">Decision · {d.topic}</span>
        <StatusBadge status={d.status} />
        <Confidence value={d.confidence} />
        <span className="ml-auto font-mono text-[11px] text-ink-muted">#{d.id}{showMeeting && ` · ${d.meeting_title} · ${fmtDate(d.meeting_date)}`}</span>
      </div>
      <h3 className={`mt-2 font-serif text-[18px] font-semibold leading-snug ${d.status === "superseded" || d.status === "rejected" ? "text-ink-muted line-through decoration-1" : ""}`}>{d.statement}</h3>
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-ink-muted">
        {d.value && <span>Value: <b className="text-ink">{displayValue(d.value, d.value_kind)}</b></span>}
        {d.previous_value && <span>Changed from: <b className="text-ink">{displayValue(d.previous_value, d.value_kind)}</b> (said in this meeting)</span>}
        <span>Speaker: {d.speaker ?? <i>not identified</i>}</span>
        <span>Origin: <OriginTag origin={d.origin} kind="decision" /></span>
      </div>
      <div className="mt-3"><Evidence excerpt={d.evidence_excerpt} segments={segsFor(d.evidence_idx, segments)} speaker={d.speaker} meetingId={showMeeting ? d.meeting_id : undefined} /></div>
      {d.notes && <p className="mt-2 rounded bg-paper px-2.5 py-1.5 text-[12.5px] text-ink-soft">{d.notes}</p>}
      {(d.supersedes_id || d.superseded_by_id) && (
        <p className="mt-2 text-[12px] text-ink-muted">
          {d.supersedes_id && <>Supersedes decision #{d.supersedes_id}. </>}
          {d.superseded_by_id && <>Superseded by decision #{d.superseded_by_id}. </>}
          <Link className="link" to="/memory">See history</Link>
        </p>
      )}
      {isReviewer && reviewable && (
        <div className="mt-3 flex flex-wrap gap-2 border-t border-line pt-3">
          {d.status === "under_review" ? (
            <span className="text-[12.5px] text-danger">Conflicts with an earlier decision — resolve it on the <Link to="/conflicts" className="underline">conflict screen</Link> before confirming.</span>
          ) : (
            <button className="btn-primary" disabled={!!busy} onClick={() => run("approve", () => post(`/api/decisions/${d.id}/approve`), "Decision confirmed and added to memory")}>Approve</button>
          )}
          <button className="btn-secondary" onClick={() => setEdit(true)}>Edit</button>
          <button className="btn-danger" onClick={() => setComment("reject")}>Reject</button>
          <button className="btn-ghost ml-auto" onClick={() => setComment("comment")}>Comment</button>
        </div>
      )}
      {edit && <EditDecision d={d} onClose={() => setEdit(false)} />}
      {comment && (
        <CommentModal title={comment === "reject" ? "Reject decision" : "Comment on decision"} required={comment === "comment"}
          confirm={comment === "reject" ? "Reject" : "Add comment"} danger={comment === "reject"} onClose={() => setComment(null)}
          onSubmit={(c) => run("c", () => (comment === "reject" ? post(`/api/decisions/${d.id}/reject`, { comment: c || null }) : post(`/api/decisions/${d.id}/comment`, { comment: c })), comment === "reject" ? "Decision rejected" : "Comment added")} />
      )}
    </article>
  );
}

function EditDecision({ d, onClose }: { d: Decision; onClose: () => void }) {
  const { run, busy } = useAction();
  const [statement, setStatement] = useState(d.statement);
  const [topic, setTopic] = useState(d.topic);
  const [value, setValue] = useState(d.value ?? "");
  return (
    <Modal open onClose={onClose} title="Edit decision" footer={<>
      <button className="btn-secondary" onClick={onClose}>Cancel</button>
      <button className="btn-primary" disabled={!!busy} onClick={async () => { if (await run("e", () => patch(`/api/decisions/${d.id}`, { statement, topic, value: value || null }), "Decision updated")) onClose(); }}>Save</button>
    </>}>
      <div className="space-y-3">
        <Field label="Statement"><textarea className="input" rows={3} value={statement} onChange={(e) => setStatement(e.target.value)} /></Field>
        <Field label="Topic" hint="Decisions on the same topic are compared across meetings"><input className="input" value={topic} onChange={(e) => setTopic(e.target.value)} /></Field>
        <Field label="Value" hint={d.value_kind === "date" ? "ISO date, e.g. 2026-11-22" : "The chosen option"}><input className="input" value={value} onChange={(e) => setValue(e.target.value)} /></Field>
      </div>
    </Modal>
  );
}

// ------------------------------------------------------------------ actions

export function ActionCard({ a, segments, showMeeting }: { a: Action; segments?: Segment[]; showMeeting?: boolean }) {
  const { isReviewer, today, user } = useApp();
  const { run, busy } = useAction();
  const [modal, setModal] = useState<null | "edit" | "publish" | "reject" | "comment">(null);
  const pub = a.publication;
  const published = pub?.state === "published";
  const canComplete = a.status === "approved" && (isReviewer || a.owner_user_id === user?.id);
  return (
    <article className="card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="label">Action item</span>
        <StatusBadge status={a.status} />
        {pub && <PublicationBadge a={a} />}
        <Confidence value={a.confidence} />
        <span className="ml-auto font-mono text-[11px] text-ink-muted">#{a.id}{showMeeting && ` · ${a.meeting_title}`}</span>
      </div>
      <h3 className={`mt-2 text-[16px] font-semibold ${a.status === "superseded" || a.status === "rejected" ? "text-ink-muted line-through" : ""}`}>{a.title}</h3>
      <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-2 text-[13px] md:grid-cols-4">
        <div><dt className="label">Owner</dt><dd>{a.owner_name ?? <span className="text-warn">Unassigned</span>} <OriginTag origin={a.owner_origin} kind="owner" /></dd></div>
        <div><dt className="label">Deadline</dt><dd><Due iso={a.deadline} today={today} /> <OriginTag origin={a.deadline_origin} kind="deadline" />{a.deadline_raw && a.deadline_raw !== "set by reviewer" && <div className="font-mono text-[11px] text-ink-muted">said: “{a.deadline_raw}”</div>}</dd></div>
        <div><dt className="label">Depends on</dt><dd>{a.dependencies.length ? a.dependencies.join(", ") : <span className="text-ink-muted">—</span>}</dd></div>
        <div><dt className="label">Related decision</dt><dd>{a.decision_id ? <Link className="link" to="/memory">#{a.decision_id}</Link> : <span className="text-ink-muted">—</span>}</dd></div>
      </dl>
      <div className="mt-3"><Evidence excerpt={a.evidence_excerpt} segments={segsFor(a.evidence_idx, segments)} speaker={a.speaker} meetingId={showMeeting ? a.meeting_id : undefined} /></div>
      {a.description.includes("Notes:") && <p className="mt-2 rounded bg-paper px-2.5 py-1.5 text-[12.5px] text-ink-soft">{a.description.split("Notes:")[1].trim()}</p>}
      {pub?.state === "failed" && <p className="mt-2 rounded bg-danger-tint px-2.5 py-1.5 text-[12.5px] text-danger">Publishing failed (attempt {pub.attempts}): {pub.last_error} — the task was not created; retrying is safe.</p>}
      {published && pub?.external_url && (
        <p className="mt-2 text-[12.5px]">
          {pub.is_external ? <a className="link" href={pub.external_url} target="_blank" rel="noreferrer">Open in tracker ({pub.provider} #{pub.external_id}) ↗</a>
            : <span className="text-ink-muted">Recorded in the demo tracker as {pub.external_id} — simulated, not sent to an external service.</span>}
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2 border-t border-line pt-3">
        {isReviewer && a.status === "proposed" && <>
          <button className="btn-primary" disabled={!!busy} onClick={() => run("ap", () => post(`/api/actions/${a.id}/approve`), "Task approved — it can now be published")}>Approve</button>
          <button className="btn-secondary" onClick={() => setModal("edit")}>Edit</button>
          <button className="btn-danger" onClick={() => setModal("reject")}>Reject</button>
        </>}
        {isReviewer && a.status === "approved" && !published && <>
          <button className="btn-primary" disabled={!!busy || pub?.state === "publishing"} onClick={() => setModal("publish")}>{pub?.state === "failed" ? "Retry publishing" : "Publish to tracker"}</button>
          <button className="btn-secondary" onClick={() => setModal("edit")}>Edit</button>
        </>}
        {canComplete && <button className="btn-secondary" disabled={!!busy} onClick={() => run("done", () => post(`/api/actions/${a.id}/complete`), "Marked complete")}>Mark complete</button>}
        {!isReviewer && a.status === "proposed" && <span className="text-[12px] text-ink-muted">Awaiting manager approval.</span>}
        <button className="btn-ghost ml-auto" onClick={() => setModal("comment")}>Comment</button>
      </div>
      {modal === "edit" && <EditAction a={a} onClose={() => setModal(null)} />}
      {modal === "publish" && <PublishModal a={a} onClose={() => setModal(null)} />}
      {(modal === "reject" || modal === "comment") && (
        <CommentModal title={modal === "reject" ? "Reject action item" : "Comment on action item"} required={modal === "comment"} danger={modal === "reject"}
          confirm={modal === "reject" ? "Reject" : "Add comment"} onClose={() => setModal(null)}
          onSubmit={(c) => run("c", () => (modal === "reject" ? post(`/api/actions/${a.id}/reject`, { comment: c || null }) : post(`/api/actions/${a.id}/comment`, { comment: c })), modal === "reject" ? "Task rejected — it will not be published" : "Comment added")} />
      )}
    </article>
  );
}

export function PublicationBadge({ a }: { a: Action }) {
  const p = a.publication;
  if (!p) return null;
  if (p.state === "published") return <Badge tone={p.is_external ? "ok" : "neutral"} title={p.is_external ? "Created in the external tracker" : "Simulated demo tracker"}>{p.is_external ? `In ${p.provider}` : "Simulated"}</Badge>;
  if (p.state === "failed") return <Badge tone="danger">Publish failed</Badge>;
  return <Badge tone="info">Publishing</Badge>;
}

function EditAction({ a, onClose }: { a: Action; onClose: () => void }) {
  const { run, busy } = useAction();
  const [title, setTitle] = useState(a.title);
  const [owner, setOwner] = useState(a.owner_name ?? "");
  const [deadline, setDeadline] = useState(a.deadline ?? "");
  const [description, setDescription] = useState(a.description);
  return (
    <Modal open onClose={onClose} title="Edit action item" footer={<>
      <button className="btn-secondary" onClick={onClose}>Cancel</button>
      <button className="btn-primary" disabled={!!busy} onClick={async () => {
        if (await run("e", () => patch(`/api/actions/${a.id}`, { title, owner_name: owner || null, deadline: deadline || null, description }), "Task updated")) onClose();
      }}>Save</button>
    </>}>
      <div className="space-y-3">
        {a.status === "approved" && <p className="rounded bg-warn-tint px-3 py-2 text-[12.5px] text-warn">Editing an approved task returns it to the approval queue.</p>}
        <Field label="Title"><input className="input" value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Owner" hint="Leave empty for unassigned"><input className="input" value={owner} onChange={(e) => setOwner(e.target.value)} /></Field>
          <Field label="Deadline"><input className="input" type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} /></Field>
        </div>
        <Field label="Description"><textarea className="input" rows={4} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
      </div>
    </Modal>
  );
}

type Preview = { provider: string; repository: string | null; title: string; labels: string[]; assignees: string[]; is_external: boolean; configured: boolean; owner: string | null; deadline: string | null; description: string; source_meeting: string; related_decision: string | null };

function PublishModal({ a, onClose }: { a: Action; onClose: () => void }) {
  const { run, busy } = useAction();
  const [preview, setPreview] = useState<Preview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api<Preview>(`/api/actions/${a.id}/preview`).then(setPreview).catch((e) => setErr((e as Error).message));
  }, [a.id]);
  return (
    <Modal open wide onClose={onClose} title="Publish to tracker" footer={<>
      <button className="btn-secondary" onClick={onClose}>Cancel</button>
      <button className="btn-primary" disabled={!!busy || !preview?.configured} onClick={async () => {
        const r = await run("pub", () => post<{ message: string }>(`/api/actions/${a.id}/publish`), (x) => x.message);
        if (r) onClose();
      }}>{busy ? "Publishing…" : preview?.is_external ? `Create in ${preview.provider}` : "Record in demo tracker"}</button>
    </>}>
      {err && <p className="text-danger">{err}</p>}
      {!preview && !err && <p className="text-ink-muted">Preparing preview…</p>}
      {preview && (
        <div className="space-y-3">
          {!preview.is_external && (
            <p className="rounded bg-warn-tint px-3 py-2 text-[12.5px] text-warn">
              The demo tracker is active. This records a simulated task inside Ledger only — nothing is sent to an external service. Configure GitHub Issues on the Integrations screen for real publishing.
            </p>
          )}
          {!preview.configured && <p className="rounded bg-danger-tint px-3 py-2 text-danger">The tracker is not configured. See Integrations.</p>}
          <p className="text-ink-soft">This is exactly what will be sent{preview.repository ? <> to <b>{preview.repository}</b></> : null}:</p>
          <div className="rounded-md border border-line bg-paper p-3 font-mono text-[12px] leading-relaxed">
            <div><span className="text-ink-muted">title:</span> {preview.title}</div>
            <div><span className="text-ink-muted">owner:</span> {preview.owner ?? "Unassigned"}{preview.assignees.length ? ` (assignee @${preview.assignees[0]})` : ""}</div>
            <div><span className="text-ink-muted">due:</span> {preview.deadline ?? "not specified"}</div>
            <div><span className="text-ink-muted">labels:</span> {preview.labels.join(", ")}</div>
            <div><span className="text-ink-muted">source:</span> {preview.source_meeting}</div>
            {preview.related_decision && <div><span className="text-ink-muted">decision:</span> {preview.related_decision}</div>}
          </div>
          <p className="text-[12px] text-ink-muted">Publishing is idempotent: repeating it, or retrying after a failure, never creates a second task.</p>
        </div>
      )}
    </Modal>
  );
}

export function CommentModal({ title, onClose, onSubmit, required, confirm, danger }: { title: string; onClose: () => void; onSubmit: (c: string) => Promise<unknown>; required?: boolean; confirm: string; danger?: boolean }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <Modal open onClose={onClose} title={title} footer={<>
      <button className="btn-secondary" onClick={onClose}>Cancel</button>
      <button className={danger ? "btn-danger" : "btn-primary"} disabled={busy || (required && !text.trim())} onClick={async () => {
        setBusy(true);
        const r = await onSubmit(text.trim());
        setBusy(false);
        if (r !== undefined) onClose();
      }}>{confirm}</button>
    </>}>
      <Field label={required ? "Comment" : "Comment (optional)"} hint="Recorded in the audit history with your name and the time.">
        <textarea className="input" rows={4} value={text} onChange={(e) => setText(e.target.value)} autoFocus />
      </Field>
    </Modal>
  );
}

// ------------------------------------------------------------------ conflicts

type Resolution = "accept_new" | "keep_previous" | "compatible" | "needs_review";
const RESOLUTION_TEXT: Record<Resolution, string> = {
  accept_new: "Accept the new decision",
  keep_previous: "Keep the previous decision",
  compatible: "Mark as compatible",
  needs_review: "Request further review",
};

export function ConflictCard({ c, compact }: { c: Conflict; compact?: boolean }) {
  const { isReviewer } = useApp();
  const { run, busy } = useAction();
  const [comment, setComment] = useState("");
  const [result, setResult] = useState<{ notes: string[]; affected_actions: { id: number; title: string; owner: string | null }[] } | null>(null);
  const unresolved = c.status === "open" || c.status === "needs_review";
  const isDecision = c.kind === "decision";
  const resolve = (resolution: Resolution) =>
    run("r", () => post<{ notes: string[]; affected_actions: { id: number; title: string; owner: string | null }[] }>(`/api/conflicts/${c.id}/resolve`, { resolution, comment: comment || null }),
      `Recorded: ${RESOLUTION_TEXT[resolution].toLowerCase()}`).then((r) => r && setResult(r));

  return (
    <article className={`card overflow-hidden ${unresolved ? "border-danger/40" : ""}`}>
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3">
        {unresolved ? <ConflictStamp category={c.category} /> : <Badge tone="neutral">{CATEGORY_LABEL[c.category] ?? c.category}</Badge>}
        <StatusBadge status={c.status} />
        <span className="font-mono text-[11px] text-ink-muted">confidence {pct(c.confidence)} · detected by {c.detected_by === "ai" ? "AI" : "rules engine"} · {isDecision ? "decision" : "task"} conflict</span>
        <span className="ml-auto font-mono text-[11px] text-ink-muted">#{c.id}</span>
      </div>
      <div className="px-5 py-4">
        <p className="text-[15px] text-ink">{c.explanation}</p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Side label="Previously" item={c.previous} isDecision={isDecision} />
          <Side label="Now" item={c.current} isDecision={isDecision} highlight />
        </div>
        <div className="mt-4 rounded-md bg-paper px-3 py-2 text-[13px]"><span className="label mr-2">Recommended</span>{c.recommended_action}</div>

        {!compact && unresolved && isReviewer && (
          <div className="mt-4 border-t border-line pt-4">
            <Field label="Resolution comment" hint="Required for “Request further review”. Saved in the audit history.">
              <textarea className="input" rows={2} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="e.g. Confirmed with Rahul: load tests justify PostgreSQL." />
            </Field>
            <div className="mt-3 flex flex-wrap gap-2">
              <button className="btn-primary" disabled={!!busy} onClick={() => resolve("accept_new")}>{RESOLUTION_TEXT.accept_new}</button>
              <button className="btn-secondary" disabled={!!busy} onClick={() => resolve("keep_previous")}>{RESOLUTION_TEXT.keep_previous}</button>
              <button className="btn-secondary" disabled={!!busy} onClick={() => resolve("compatible")}>{RESOLUTION_TEXT.compatible}</button>
              <button className="btn-ghost" disabled={!!busy || !comment.trim()} onClick={() => resolve("needs_review")} title={comment.trim() ? "" : "Add a comment first"}>{RESOLUTION_TEXT.needs_review}</button>
            </div>
            <p className="mt-2 text-[12px] text-ink-muted">Nothing is deleted: accepting marks the earlier {isDecision ? "decision" : "task"} as superseded and keeps it in history.</p>
          </div>
        )}
        {!compact && unresolved && !isReviewer && <p className="mt-4 text-[12.5px] text-ink-muted">A manager must resolve this conflict.</p>}
        {!unresolved && (
          <p className="mt-4 text-[12.5px] text-ink-muted">
            Resolved{c.resolved_by ? ` by ${c.resolved_by.name}` : ""} {c.resolved_at ? fmtDateTime(c.resolved_at) : ""} — {titleCase(c.status)}
            {c.resolution_comment ? `: “${c.resolution_comment}”` : ""}
          </p>
        )}
        {c.status === "needs_review" && c.resolution_comment && <p className="mt-2 text-[12.5px] text-warn">Review requested: “{c.resolution_comment}”</p>}
        {result && (result.notes.length > 0 || result.affected_actions.length > 0) && (
          <div className="mt-3 rounded-md border border-warn/30 bg-warn-tint px-3 py-2 text-[13px] text-warn">
            {result.notes.map((n) => <div key={n}>{n}</div>)}
            {result.affected_actions.map((x) => <div key={x.id}>• #{x.id} {x.title} ({x.owner ?? "unassigned"}) — <Link className="underline" to="/actions">review task</Link></div>)}
          </div>
        )}
      </div>
    </article>
  );
}

function Side({ label, item, isDecision, highlight }: { label: string; item: Conflict["previous"]; isDecision: boolean; highlight?: boolean }) {
  return (
    <div className={`rounded-md border p-3 ${highlight ? "border-danger/30 bg-danger-tint/30" : "border-line bg-surface"}`}>
      <div className="flex items-center justify-between">
        <span className="label">{label}</span>
        <StatusBadge status={item.status} />
      </div>
      <div className="mt-1 font-mono text-[11px] text-ink-muted">
        <Link className="hover:underline" to={`/meetings/${item.meeting_id}`}>{item.meeting_title}</Link> · {fmtDate(item.meeting_date)}
      </div>
      {isDecision ? (
        <div className="mt-2">
          <div className="font-serif text-[16px] font-semibold">{(item as Decision).statement}</div>
          {(item as Decision).value && <div className="text-[13px] text-ink-muted">Value: <b className="text-ink">{displayValue((item as Decision).value, (item as Decision).value_kind)}</b></div>}
        </div>
      ) : (
        <div className="mt-2">
          <div className="text-[15px] font-semibold">{(item as Action).title}</div>
          <div className="text-[13px] text-ink-muted">Owner <b className="text-ink">{(item as Action).owner_name ?? "unassigned"}</b> · due <b className="text-ink">{fmtDate((item as Action).deadline)}</b></div>
        </div>
      )}
      <div className="mt-2"><Evidence excerpt={item.evidence_excerpt} segments={item.evidence_segments} /></div>
    </div>
  );
}
