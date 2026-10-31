import { useEffect, useState, type FormEvent } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";

type Accounts = { accounts: { name: string; role: string }[]; default_password_hint: boolean };

export default function Login() {
  const { login } = useApp();
  const [username, setUsername] = useState("Anshul");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [accounts, setAccounts] = useState<Accounts | null>(null);

  useEffect(() => {
    api<Accounts>("/api/auth/demo-accounts").then(setAccounts).catch((e) => setError((e as Error).message));
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <section className="hidden flex-col justify-between border-r border-line bg-surface p-12 lg:flex">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-accent font-serif text-[17px] font-semibold text-white">L</div>
          <span className="font-serif text-xl font-semibold">Ledger</span>
        </div>
        <div className="max-w-md">
          <p className="label mb-3">Meeting-to-execution agent</p>
          <h1 className="font-serif text-[40px] font-semibold leading-[1.1] tracking-tight">Decisions made in meetings stop getting lost.</h1>
          <p className="mt-4 text-[15px] text-ink-soft">
            Speak or upload a meeting. Ledger extracts decisions, owners and deadlines with evidence, remembers what was decided before,
            flags when a meeting contradicts an earlier one, and posts tasks to your tracker only after a person approves them.
          </p>
          <ol className="mt-8 space-y-3 text-[13.5px] text-ink-soft">
            {["Dictate with Wispr Flow or upload TXT, DOCX, PDF", "Cross-meeting memory with full decision history", "Conflicts need human resolution — nothing is overwritten", "Approval-gated publishing, reminders, weekly digests"].map((t, i) => (
              <li key={t} className="flex gap-3"><span className="font-mono text-ink-faint">0{i + 1}</span>{t}</li>
            ))}
          </ol>
        </div>
        <p className="text-[12px] text-ink-muted">Product Space AI Hackathon · Problem statement 03</p>
      </section>

      <section className="flex items-center justify-center p-8">
        <form onSubmit={submit} className="w-full max-w-sm">
          <h2 className="font-serif text-2xl font-semibold">Sign in</h2>
          <p className="mt-1 text-ink-muted">Use a demo account. Managers review and approve; members see their own work.</p>
          {accounts && (
            <div className="mt-5 grid grid-cols-2 gap-2">
              {accounts.accounts.map((a) => (
                <button type="button" key={a.name} onClick={() => setUsername(a.name)}
                  className={`rounded-md border px-3 py-2 text-left transition ${username === a.name ? "border-accent bg-accent-tint" : "border-line bg-surface hover:border-line-strong"}`}>
                  <div className="text-[13px] font-medium">{a.name}</div>
                  <div className="font-mono text-[10px] uppercase text-ink-muted">{a.role}</div>
                </button>
              ))}
            </div>
          )}
          <label className="mt-5 block">
            <span className="mb-1 block text-[12px] font-medium text-ink-soft">Name or email</span>
            <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
          </label>
          <label className="mt-3 block">
            <span className="mb-1 block text-[12px] font-medium text-ink-soft">Password</span>
            <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required autoFocus />
          </label>
          {accounts?.default_password_hint && <p className="mt-2 text-[12px] text-ink-muted">Local demo password: <code className="font-mono">demo1234</code> (change DEMO_PASSWORD in backend/.env).</p>}
          {error && <p className="mt-3 rounded-md bg-danger-tint px-3 py-2 text-[13px] text-danger">{error}</p>}
          <button className="btn-primary mt-5 w-full py-2" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
      </section>
    </div>
  );
}
