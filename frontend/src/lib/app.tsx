import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, getToken, post, setToken, setUnauthorizedHandler } from "./api";
import type { Project, SystemStatus, User } from "./types";

// ------------------------------------------------------------------ toasts
type Toast = { id: number; tone: "ok" | "error" | "info"; text: string };
const ToastCtx = createContext<(tone: Toast["tone"], text: string) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const next = useRef(1);
  const push = useCallback((tone: Toast["tone"], text: string) => {
    const id = next.current++;
    setItems((xs) => [...xs, { id, tone, text }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), tone === "error" ? 7000 : 4000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex w-[360px] flex-col gap-2" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`card px-4 py-3 text-[13px] border-l-4 ${t.tone === "error" ? "border-l-danger" : t.tone === "ok" ? "border-l-ok" : "border-l-info"}`}>
            {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

// ------------------------------------------------------------------ app state
interface AppState {
  user: User | null;
  booting: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  projects: Project[];
  projectId: number | null;
  project: Project | null;
  setProjectId: (id: number) => void;
  refreshProjects: () => Promise<void>;
  status: SystemStatus | null;
  refreshStatus: () => Promise<void>;
  isReviewer: boolean;
  today: string;
  version: number;
  bump: () => void; // signal data-changing actions so badges/counters refresh
}

const AppCtx = createContext<AppState | null>(null);
export function useApp(): AppState {
  const v = useContext(AppCtx);
  if (!v) throw new Error("useApp outside provider");
  return v;
}

const PROJECT_KEY = "mte.project";

export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [booting, setBooting] = useState(true);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setPid] = useState<number | null>(() => {
    try {
      const v = localStorage.getItem(PROJECT_KEY);
      return v ? Number(v) : null;
    } catch {
      return null;
    }
  });
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [version, setVersion] = useState(0);

  const refreshProjects = useCallback(async () => {
    const ps = await api<Project[]>("/api/projects");
    setProjects(ps);
    setPid((cur) => (cur && ps.some((p) => p.id === cur) ? cur : ps[ps.length - 1]?.id ?? null));
  }, []);
  const refreshStatus = useCallback(async () => setStatus(await api<SystemStatus>("/api/system/status")), []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setToken(null);
      setUser(null);
    });
    if (!getToken()) {
      setBooting(false);
      return;
    }
    api<User>("/api/auth/me")
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setBooting(false));
  }, []);

  useEffect(() => {
    if (!user) return;
    refreshProjects().catch(() => {});
    refreshStatus().catch(() => {});
  }, [user, refreshProjects, refreshStatus]);

  const setProjectId = (id: number) => {
    setPid(id);
    try {
      localStorage.setItem(PROJECT_KEY, String(id));
    } catch {
      /* ignore */
    }
  };

  const value = useMemo<AppState>(() => ({
    user,
    booting,
    login: async (username, password) => {
      const r = await post<{ token: string; user: User }>("/api/auth/login", { username, password });
      setToken(r.token);
      setUser(r.user);
    },
    logout: async () => {
      try {
        await post("/api/auth/logout");
      } catch {
        /* already signed out */
      }
      setToken(null);
      setUser(null);
    },
    projects,
    projectId,
    project: projects.find((p) => p.id === projectId) ?? null,
    setProjectId,
    refreshProjects,
    status,
    refreshStatus,
    isReviewer: user?.role === "admin" || user?.role === "manager",
    today: status?.clock.now.slice(0, 10) ?? new Date().toISOString().slice(0, 10),
    version,
    bump: () => setVersion((v) => v + 1),
  }), [user, booting, projects, projectId, status, refreshProjects, refreshStatus, version]);

  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}

// ------------------------------------------------------------------ data hook
export function useData<T>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { version } = useApp();
  const load = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try {
      setData(await api<T>(path));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, version, ...deps]);
  useEffect(() => {
    load();
  }, [load]);
  return { data, error, loading, reload: load, setData };
}

/** Runs a mutating request with a busy flag, a toast on error, and a refresh signal on success. */
export function useAction() {
  const toast = useToast();
  const { bump } = useApp();
  const [busy, setBusy] = useState<string | null>(null);
  const run = useCallback(
    async <T,>(key: string, fn: () => Promise<T>, success?: string | ((r: T) => string)): Promise<T | undefined> => {
      setBusy(key);
      try {
        const r = await fn();
        if (success) toast("ok", typeof success === "function" ? success(r) : success);
        bump();
        return r;
      } catch (e) {
        toast("error", (e as Error).message);
        return undefined;
      } finally {
        setBusy(null);
      }
    },
    [toast, bump],
  );
  return { busy, run };
}
