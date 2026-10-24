import type {
  AlertLifecycle,
  AlertRow,
  ApplicationSummary,
  AuditEvent,
  CaseDetail,
  ComplianceBatch,
  DocumentRow,
  EvcCommittee,
  EvcQueue,
  EvcVisit,
  FullReport,
  Institution,
  OfficerDashboard,
  RehearsalReport,
  SessionUser,
  Undertaking,
  UploadResult,
  WorkflowRoute,
} from "./types";

const BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ??
  "http://localhost:8000/api/v1";

const TOKEN_KEY = "sih26262.token";
const USER_KEY = "sih26262.user";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
  }
}

export function storedToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function storedUser(): SessionUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as SessionUser;
  } catch {
    return null;
  }
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

/** Fired when the API rejects the stored token (expired, revoked, reseeded database). */
export const SESSION_EXPIRED_EVENT = "sih26262:session-expired";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = storedToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${BASE}${path}`, { ...init, headers });
  const text = await response.text();
  const body = text ? (JSON.parse(text) as unknown) : null;

  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : response.statusText;
    const code =
      body && typeof body === "object" && "code" in body
        ? String((body as { code: unknown }).code)
        : undefined;
    // A rejected *stored token* means the session cannot be used any more.
    // Drop it and let the app fall back to the sign-in screen instead of
    // showing an empty case list. A 401 on the login request itself has no
    // token attached — that is a wrong email/password, not an expired
    // session, and saying "your session ended" there would confuse people.
    if (response.status === 401 && token) {
      clearSession();
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
    throw new ApiError(detail, response.status, code);
  }
  return body as T;
}

export async function login(email: string, password: string): Promise<SessionUser> {
  const result = await request<{
    access_token: string;
    token_type: string;
    user: SessionUser;
  }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  localStorage.setItem(TOKEN_KEY, result.access_token);
  localStorage.setItem(USER_KEY, JSON.stringify(result.user));
  return result.user;
}

export const api = {
  applications: () => request<ApplicationSummary[]>("/applications"),
  application: (id: string) => request<CaseDetail>(`/applications/${id}`),
  institutions: () => request<Institution[]>("/institutions"),
  routes: () => request<WorkflowRoute[]>("/workflow/routes"),
  createApplication: (payload: {
    institution_id: string;
    category: string;
    route_key: string;
    cycle: string;
    cycle_end: string | null;
  }) =>
    request<ApplicationSummary>("/applications", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  documents: (id: string) =>
    request<DocumentRow[]>(`/applications/${id}/documents`),
  uploadDocument: (id: string, docType: string, file: File) => {
    const form = new FormData();
    form.set("doc_type", docType);
    form.set("file", file);
    return request<UploadResult>(`/applications/${id}/documents`, {
      method: "POST",
      body: form,
    });
  },
  /**
   * Fetch a document's bytes and hand them to the user. Needs the auth header,
   * so it cannot be a plain <a href>; we fetch, then trigger a real download.
   */
  downloadDocument: async (
    id: string,
    documentId: string,
    fileName: string,
  ) => {
    const headers = new Headers();
    const token = storedToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(
      `${BASE}/applications/${id}/documents/${documentId}/content`,
      { headers },
    );
    if (!response.ok) {
      throw new ApiError(
        `Could not fetch the file (${response.status})`,
        response.status,
      );
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = fileName || "document";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  },

  /** Open a document in a new tab (returns an object URL the caller revokes). */
  openDocument: async (id: string, documentId: string) => {
    const headers = new Headers();
    const token = storedToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(
      `${BASE}/applications/${id}/documents/${documentId}/content`,
      { headers },
    );
    if (!response.ok) {
      throw new ApiError(
        `Could not fetch the file (${response.status})`,
        response.status,
      );
    }
    const blob = await response.blob();
    return URL.createObjectURL(blob);
  },
  verifyField: (
    id: string,
    documentId: string,
    fieldId: string,
    verificationStatus: "verified" | "rejected" | "unverified",
  ) =>
    request<{ field_id: string; verification_status: string }>(
      `/applications/${id}/documents/${documentId}/fields/${fieldId}/verify`,
      {
        method: "POST",
        body: JSON.stringify({ verification_status: verificationStatus }),
      },
    ),
  undertakings: (id: string) =>
    request<Undertaking[]>(`/applications/${id}/undertakings`),
  submitUndertaking: (id: string, undertakingId: string, evidenceNote: string) =>
    request<Undertaking>(
      `/applications/${id}/undertakings/${undertakingId}/submit`,
      {
        method: "POST",
        body: JSON.stringify({ evidence_note: evidenceNote }),
      },
    ),
  verifyUndertaking: (id: string, undertakingId: string) =>
    request<Undertaking>(
      `/applications/${id}/undertakings/${undertakingId}/verify`,
      { method: "POST" },
    ),
  /** An officer imposes a follow-up condition on the college. */
  createUndertaking: (
    id: string,
    payload: {
      title: string;
      condition_text?: string;
      evidence_required?: string;
      due_at: string;
    },
  ) =>
    request<Undertaking>(`/applications/${id}/undertakings`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  /** An officer lets a condition go, with the reason recorded. */
  waiveUndertaking: (id: string, undertakingId: string, reason: string) =>
    request<Undertaking>(
      `/applications/${id}/undertakings/${undertakingId}/waive`,
      {
        method: "POST",
        body: JSON.stringify({ reason }),
      },
    ),
  compliance: (id: string) => request<ComplianceBatch>(`/applications/${id}/compliance`),
  evaluate: (id: string) =>
    request<ComplianceBatch>(`/applications/${id}/compliance/evaluate`, { method: "POST" }),
  rehearse: (id: string, overrides: Record<string, unknown>) =>
    request<RehearsalReport>(`/applications/${id}/rehearsals`, {
      method: "POST",
      body: JSON.stringify({ overrides }),
    }),
  transition: (id: string, action: string, reason: string) =>
    request<{
      accepted: boolean;
      from_state: string;
      to_state: string;
      reasons: string[];
      notes?: string[];
      transition_id?: string;
    }>(`/applications/${id}/transitions`, {
      method: "POST",
      body: JSON.stringify({ action, reason }),
    }),
  /** Undo the last step on a case. The undo is itself a recorded step. */
  revert: (id: string, reason: string) =>
    request<{
      accepted: boolean;
      action: string;
      from_state: string;
      to_state: string;
      reasons: string[];
      notes: string[];
    }>(`/applications/${id}/revert`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  audit: (id: string) =>
    request<{ application_id: string; note: string; events: AuditEvent[] }>(
      `/applications/${id}/audit`,
    ),
  verifyAudit: () =>
    request<{ ok: boolean; checked: number; first_broken_seq: number | null; reason: string }>(
      "/audit/verify",
    ),
  dashboard: () => request<OfficerDashboard>("/officer/dashboard"),
  alerts: () =>
    request<{ simulated: boolean; note: string; alerts: AlertRow[] }>("/alerts"),
  /** "I have seen this reminder" — idempotent, recorded in the case history. */
  ackAlert: (alertId: string) =>
    request<AlertLifecycle>(`/alerts/${alertId}/ack`, { method: "POST" }),
  /** "This is dealt with" — always requires a short explanation. */
  closeAlert: (alertId: string, reason: string) =>
    request<AlertLifecycle>(`/alerts/${alertId}/close`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  // --- Reports (all sections, one round trip) ---
  reports: () => request<FullReport>("/reports"),

  // --- Expert Visit Committee scheduling ---
  evcCommittees: () => request<EvcCommittee[]>("/evc/committees"),
  evcQueue: () => request<EvcQueue>("/evc/queue"),
  evcVisits: (id: string) => request<EvcVisit[]>(`/applications/${id}/evc/visits`),
  scheduleEvcVisit: (
    id: string,
    payload: {
      scheduled_date: string;
      venue?: string;
      committee_id?: string | null;
      notes?: string;
    },
  ) =>
    request<EvcVisit>(`/applications/${id}/evc/visits`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

export { BASE as API_BASE };
