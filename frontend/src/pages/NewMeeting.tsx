import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Field, PageHeader } from "../components/ui";
import { api, post } from "../lib/api";
import { useApp, useToast } from "../lib/app";
import type { MeetingBrief } from "../lib/types";

type Mode = "voice" | "upload" | "paste";
const MAX_BYTES = 2 * 1024 * 1024;

const SAMPLE = `Okay, so quick sync on the portal. Um, Rahul will handle the database migration... actually, let's not use MongoDB anymore. We decided to move to PostgreSQL. He should finish it by Friday. Priya, can you update the API docs once the migration is done? And, uh, the production launch is still scheduled for November 22.`;

// Minimal typing for the optional browser speech API (Chrome/Edge).
type Recognition = { lang: string; continuous: boolean; interimResults: boolean; start: () => void; stop: () => void; onresult: ((e: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null; onend: (() => void) | null; onerror: ((e: { error: string }) => void) | null };

export default function NewMeeting() {
  const { projectId, project, user, today, isReviewer, bump } = useApp();
  const toast = useToast();
  const nav = useNavigate();
  const [mode, setMode] = useState<Mode>("voice");
  const [title, setTitle] = useState("");
  const [date, setDate] = useState(today);
  const [speaker, setSpeaker] = useState(user?.name ?? "");
  const [participants, setParticipants] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [processNow, setProcessNow] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const area = useRef<HTMLTextAreaElement>(null);

  useEffect(() => setDate(today), [today]);
  useEffect(() => {
    if (mode !== "upload") area.current?.focus();
  }, [mode]);

  const words = text.trim() ? text.trim().split(/\s+/).length : 0;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!projectId) return;
    setError(null);
    try {
      let m: MeetingBrief;
      setBusy("Saving transcript");
      if (mode === "upload") {
        if (!file) throw new Error("Choose a .txt, .docx or .pdf file.");
        if (file.size > MAX_BYTES) throw new Error("The file is larger than 2 MB.");
        if (file.size === 0) throw new Error("The file is empty.");
        const form = new FormData();
        form.append("project_id", String(projectId));
        form.append("file", file);
        form.append("title", title);
        if (date) form.append("meeting_date", date);
        form.append("participants", participants);
        m = await api<MeetingBrief>("/api/meetings/upload", { method: "POST", form });
      } else {
        if (!text.trim()) throw new Error(mode === "voice" ? "Dictate the meeting into the box first." : "Paste the transcript first.");
        m = await post<MeetingBrief>("/api/meetings/text", {
          project_id: projectId, title, meeting_date: date || null, text, source: mode === "voice" ? "dictation" : "paste",
          dictated_by: mode === "voice" ? speaker || null : null,
          participants: participants.split(",").map((p) => p.trim()).filter(Boolean),
        });
      }
      if (processNow && isReviewer) {
        setBusy("Extracting decisions and checking memory");
        try {
          const r = await post<{ decisions: number; actions: number; conflicts: number }>(`/api/meetings/${m.id}/process`, {});
          toast(r.conflicts ? "info" : "ok", `Extracted ${r.decisions} decisions and ${r.actions} tasks${r.conflicts ? ` — ${r.conflicts} conflict(s) with earlier meetings need review` : ""}.`);
        } catch (err) {
          toast("error", `Saved, but processing failed: ${(err as Error).message}`);
        }
      } else toast("ok", "Meeting saved.");
      bump();
      nav(`/meetings/${m.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <PageHeader eyebrow={project?.name} title="Capture a meeting" subtitle="Speak naturally — filler words, digressions and self-corrections are expected. Or upload an existing transcript." />
      <form onSubmit={submit} className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <div className="space-y-4">
          <div className="inline-flex rounded-md border border-line-strong bg-surface p-0.5" role="tablist">
            {([["voice", "Speak with Wispr Flow"], ["upload", "Upload file"], ["paste", "Paste transcript"]] as [Mode, string][]).map(([k, label]) => (
              <button key={k} type="button" role="tab" aria-selected={mode === k} onClick={() => setMode(k)}
                className={`rounded px-3 py-1.5 text-[13px] ${mode === k ? "bg-accent text-white" : "text-ink-soft hover:text-ink"}`}>{label}</button>
            ))}
          </div>

          {mode === "upload" ? (
            <label className="card flex cursor-pointer flex-col items-center justify-center border-dashed px-6 py-14 text-center hover:border-accent"
              onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); setFile(e.dataTransfer.files[0] ?? null); }}>
              <input type="file" accept=".txt,.md,.docx,.pdf" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              <span className="font-serif text-lg font-semibold">{file ? file.name : "Drop a transcript here or click to choose"}</span>
              <span className="mt-1 text-ink-muted">{file ? `${(file.size / 1024).toFixed(1)} KB` : "TXT, DOCX or text-based PDF · up to 2 MB · speaker labels like “Priya: …” or “[00:01:12] Priya: …” are preserved"}</span>
            </label>
          ) : (
            <div className="card overflow-hidden">
              {mode === "voice" && <VoiceHeader onSample={() => setText(SAMPLE)} onAppend={(t) => setText((x) => (x ? `${x} ${t}` : t))} />}
              <textarea ref={area} value={text} onChange={(e) => setText(e.target.value)} rows={14}
                placeholder={mode === "voice"
                  ? "Click here, press your Wispr Flow shortcut and talk through the meeting…\n\ne.g. “Rahul will handle the migration… actually, let's not use MongoDB anymore. We decided to move to PostgreSQL. He should finish it by Friday.”"
                  : "[00:00:05] Anshul: Let's get started.\n[00:00:21] Rahul: I'll complete the integration by November 5."}
                className="block w-full resize-y border-0 bg-surface px-4 py-3 font-serif text-[16px] leading-relaxed outline-none placeholder:font-sans placeholder:text-[14px] placeholder:text-ink-faint" />
              <div className="flex items-center justify-between border-t border-line px-4 py-2 font-mono text-[11px] text-ink-muted">
                <span>{words} words</span>
                {text && <button type="button" className="link" onClick={() => setText("")}>Clear</button>}
              </div>
            </div>
          )}
          {error && <p className="rounded-md bg-danger-tint px-3 py-2 text-danger">{error}</p>}
        </div>

        <aside className="space-y-4">
          <div className="card space-y-3 p-4">
            <Field label="Meeting title" hint="Optional for uploads with a “Meeting:” header line">
              <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Weekly product sync" maxLength={200} />
            </Field>
            <Field label="Meeting date" hint="Deadlines like “next Friday” are resolved from this date">
              <input className="input" type="date" value={date} onChange={(e) => setDate(e.target.value)} required={mode !== "upload"} />
            </Field>
            {mode === "voice" && (
              <Field label="Dictated by" hint="Unlabelled speech is attributed to this person">
                <input className="input" value={speaker} onChange={(e) => setSpeaker(e.target.value)} maxLength={80} />
              </Field>
            )}
            <Field label="Participants" hint="Optional, comma-separated. Helps match owners.">
              <input className="input" value={participants} onChange={(e) => setParticipants(e.target.value)} placeholder="Rahul, Priya, Karan" />
            </Field>
            {isReviewer ? (
              <label className="flex items-center gap-2 text-[13px]">
                <input type="checkbox" checked={processNow} onChange={(e) => setProcessNow(e.target.checked)} /> Extract and check memory right away
              </label>
            ) : (
              <p className="text-[12px] text-ink-muted">A manager will process and review this meeting.</p>
            )}
            <button className="btn-primary w-full py-2" disabled={!!busy}>{busy ? `${busy}…` : "Save meeting"}</button>
          </div>
          <div className="card p-4 text-[12.5px] text-ink-soft">
            <div className="label mb-2">Speaking tips</div>
            <ul className="list-disc space-y-1 pl-4">
              <li>Name owners: “Priya will…”, “Rahul is responsible for…”.</li>
              <li>Say deadlines out loud: “by November 12”, “next Friday”.</li>
              <li>Self-corrections are understood: “actually, let's not…”.</li>
              <li>Nothing is published until a manager approves it.</li>
            </ul>
          </div>
        </aside>
      </form>
    </>
  );
}

function VoiceHeader({ onSample, onAppend }: { onSample: () => void; onAppend: (t: string) => void }) {
  const [listening, setListening] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);
  const rec = useRef<Recognition | null>(null);
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;

  const toggle = () => {
    if (!Ctor) return;
    if (listening) {
      rec.current?.stop();
      return;
    }
    const r = new Ctor();
    r.lang = "en-IN";
    r.continuous = true;
    r.interimResults = false;
    r.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) onAppend(e.results[i][0].transcript.trim());
    };
    r.onend = () => setListening(false);
    r.onerror = (e) => {
      setMicError(e.error === "not-allowed" ? "Microphone permission was denied." : `Microphone error: ${e.error}`);
      setListening(false);
    };
    rec.current = r;
    setMicError(null);
    r.start();
    setListening(true);
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-accent-tint/50 px-4 py-2.5">
      <div className="text-[12.5px] text-ink-soft">
        <b className="text-accent">Voice-first:</b> click in the box and dictate with your <b>Wispr Flow</b> shortcut. Wispr types your speech here; Ledger structures it.
      </div>
      <div className="flex items-center gap-2">
        {Ctor && (
          <button type="button" className={listening ? "btn-danger" : "btn-ghost"} onClick={toggle} title="Optional fallback using the browser's speech recognition (Chrome/Edge)">
            {listening ? "Stop browser mic" : "Browser mic (optional)"}
          </button>
        )}
        <button type="button" className="btn-ghost" onClick={onSample} title="Insert an example of dictated speech">Insert sample</button>
      </div>
      {micError && <div className="w-full text-[12px] text-danger">{micError}</div>}
    </div>
  );
}
