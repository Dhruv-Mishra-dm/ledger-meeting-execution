export type Role = "admin" | "manager" | "member";
export interface User { id: number; name: string; email: string | null; role: Role; can_login: boolean }
export interface Project { id: number; name: string; description: string; created_at: string; meetings: number; people: number }

export interface Segment { idx: number; speaker: string | null; timestamp: string | null; text: string }
export interface MeetingBrief {
  id: number; project_id: number; title: string; meeting_date: string; source_type: string; source_filename: string | null;
  source_bytes: number; status: "uploaded" | "processing" | "processed" | "failed"; process_error: string | null; ai_mode: string | null;
  uploaded_at: string; processed_at: string | null; dictated_by: string | null; participants: string[]; segment_count: number;
  decisions?: number; actions?: number; open_conflicts?: number;
}
export interface Meeting extends MeetingBrief {
  segments: Segment[];
  participant_details: { name: string; user_id: number | null; source: string }[];
}

export type DecisionStatus = "proposed" | "under_review" | "confirmed" | "superseded" | "rejected";
export interface Decision {
  id: number; project_id: number; meeting_id: number; meeting_title: string; meeting_date: string; topic: string; statement: string;
  value: string | null; value_kind: string; previous_value: string | null; speaker: string | null; evidence_idx: number[];
  evidence_excerpt: string; confidence: number; origin: string; status: DecisionStatus; supersedes_id: number | null;
  superseded_by_id: number | null; related_decision_id: number | null; notes: string | null; reviewed_at: string | null; created_at: string;
  evidence_segments?: Segment[];
}

export interface Publication {
  state: "publishing" | "published" | "failed"; provider: string; external_id: string | null; external_url: string | null;
  attempts: number; last_error: string | null; is_external: boolean; published_at: string | null;
}
export type ActionStatus = "proposed" | "approved" | "rejected" | "superseded" | "done";
export interface Action {
  id: number; project_id: number; meeting_id: number; meeting_title: string; meeting_date: string; decision_id: number | null; title: string;
  description: string; owner_name: string | null; owner_user_id: number | null; owner_origin: string; deadline: string | null;
  deadline_raw: string | null; deadline_origin: string; dependencies: string[]; speaker: string | null; evidence_idx: number[];
  evidence_excerpt: string; confidence: number; status: ActionStatus; completed_at: string | null; reviewed_at: string | null;
  publication: Publication | null; evidence_segments?: Segment[];
}

export interface Conflict {
  id: number; project_id: number; meeting_id: number; category: string; explanation: string; confidence: number; recommended_action: string;
  detected_by: string; status: "open" | "needs_review" | "accepted_new" | "kept_previous" | "compatible"; resolution_comment: string | null;
  resolved_at: string | null; created_at: string; resolved_by: User | null; kind: "decision" | "action";
  previous: (Decision & Partial<Action>) | (Action & Partial<Decision>); current: (Decision & Partial<Action>) | (Action & Partial<Decision>);
}

export interface Reminder { id: number; action_id: number; user_id: number | null; owner_name: string | null; kind: string; due_date: string; status: string; created_at: string; action: Action }
export interface Notification { id: number; user_id: number | null; kind: string; title: string; body: string; link: string | null; created_at: string; read_at: string | null }
export interface AuditEntry { id: number; project_id: number | null; item_type: string; item_id: number | null; action: string; actor: string; previous_state: string | null; new_state: string | null; comment: string | null; details: Record<string, unknown>; created_at: string }

export interface SystemStatus {
  ai: { provider: string; is_real_ai: boolean; model: string | null; configured: boolean; label: string };
  tracker: { provider: string; label: string; is_external: boolean; configured: boolean; status: string; detail: string | null; workspace: string | null; last_checked_at: string | null };
  clock: { now: string; override: string | null; timezone: string };
}

export interface MemoryGroup { topic: string; current: Decision | null; pending: Decision[]; history: Decision[]; open_conflicts: number; last_changed: string }
