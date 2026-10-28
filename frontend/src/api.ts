import type {
  AlertLifecycle,
  AlertRow,
  AppealRecord,
  AppealWindow,
  ApplicationSummary,
  AuditEvent,
  CaseDetail,
  ChecklistOut,
  ComplianceBatch,
  DeficiencyReport,
  DeficiencyRow,
  DemoClockMove,
  DemoClockStatus,
  DocCheck,
  DocCheckStaged,
  DocumentRow,
  EvcCommittee,
  EvcRegionCalendar,
  EvcReport,
  EvcQueue,
  EvcVisit,
  FullReport,
  Institution,
  OfficerDashboard,
  RehearsalReport,
  ReopeningRecord,
  RouteScoreboard,
  ScrutinyResultsView,
  SessionUser,
  ShcQueueRow,
  ExecutiveQueueRow,
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

async function download(path: string): Promise<Blob> {
  const headers = new Headers();
  const token = storedToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${BASE}${path}`, { headers });
  if (!response.ok) {
    const text = await response.text();
    let message = response.statusText;
    try {
      const body = JSON.parse(text) as { detail?: unknown };
      if (body.detail !== undefined) message = String(body.detail);
    } catch {
      // Keep the HTTP status text when the server did not return JSON.
    }
    if (response.status === 401 && token) {
      clearSession();
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
    throw new ApiError(message, response.status);
  }
  return response.blob();
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
  grantEligible: () => request<{ application_id: string; cycle: string; institution_id: string; eligible: boolean }[]>("/grant/eligible"),
  grantBatches: () => request<{ id: string; cycle: string; status: string; last_grant_date: string; calendar_source: string; entries: { application_id: string; approved_intake: { course_name: string; approved_intake: number }[]; letter_document_id: string | null }[] }[]>("/grant/batches"),
  createGrantBatch: (payload: { cycle: string; last_grant_date: string; calendar_source: string; entries: { application_id: string; approved_intake: { course_name: string; approved_intake: number }[] }[] }) => request("/grant/batches", { method: "POST", body: JSON.stringify(payload) }),
  ratifyGrantBatch: (id: string, reason: string) => request(`/grant/batches/${id}/ratify`, { method: "POST", body: JSON.stringify({ reason }) }),
  uploadGrantLetter: (batchId: string, applicationId: string, file: File) => { const form = new FormData(); form.set("file", file); return request(`/grant/batches/${batchId}/applications/${applicationId}/letter`, { method: "POST", body: form }); },
  publishGrantBatch: (id: string) => request(`/grant/batches/${id}/publish`, { method: "POST" }),
  applicationGrant: (id: string) => request<{ application_id: string; published: false } | { application_id: string; published: true; cycle: string; approved_intake: { course_name: string; approved_intake: number }[]; letter_document_id: string; published_at: string }>(`/grant/applications/${id}`),
  application: (id: string) => request<CaseDetail>(`/applications/${id}`),
  institutions: () => request<Institution[]>("/institutions"),
  routes: () => request<WorkflowRoute[]>("/workflow/routes"),
  routeScoreboard: () => request<RouteScoreboard>("/workflow/table-2-3-scoreboard"),
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
  /** The Annexure-2 checklist for this case's category — advisory, read-only. */
  checklist: (id: string) => request<ChecklistOut>(`/applications/${id}/checklist`),
  /** The recorded scrutiny results (FR-14) — checklist lines joined with the
   * officer's per-item and overall verdicts. Read-only. */
  scrutinyResults: (id: string) =>
    request<ScrutinyResultsView>(`/applications/${id}/scrutiny-results`),
  /** Record the officer's verdict on one checklist line, with remarks.
   * Refused (422) if the category/item is not a real checklist line or the
   * result is outside the configured vocabulary. */
  recordScrutinyItemResult: (
    id: string,
    body: { category_id: string; item_id: string; result: string; remarks: string },
  ) =>
    request<{ result: string }>(`/applications/${id}/scrutiny-results`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  /** Record the officer's overall verdict, with remarks. Refused (422) if it
   * contradicts a recorded "deficiency" item result. */
  recordScrutinyOverallResult: (
    id: string,
    body: { result: string; remarks: string },
  ) =>
    request<{ result: string }>(`/applications/${id}/scrutiny-results/overall`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
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

  /** Export this application's audit events after a server-side whole-chain check. */
  downloadAudit: async (id: string) => {
    const headers = new Headers();
    const token = storedToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(`${BASE}/applications/${id}/audit/export`, { headers });
    if (!response.ok) {
      throw new ApiError(`Could not export the audit (${response.status})`, response.status);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${id}-audit.json`;
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
  claimField: (
    id: string,
    documentId: string,
    fieldId: string,
    value: unknown,
    reason: string,
  ) =>
    request<{
      field_id: string;
      document_id: string;
      extraction_value: unknown;
      claim_value: unknown;
      claim_reason: string | null;
      edited: boolean;
    }>(
      `/applications/${id}/documents/${documentId}/fields/${fieldId}/claim`,
      {
        method: "POST",
        body: JSON.stringify({ value, reason }),
      },
    ),
  deficiencies: (id: string) =>
    request<DeficiencyRow[]>(`/applications/${id}/deficiencies`),
  /** The composed deficiency report and compliance window (FR-15) — issued
   * at, reply-by, open/overdue/received, awaiting Re-Scrutiny. Advisory:
   * the window is placeholder config and never blocks a resubmission. */
  deficiencyReport: (id: string) =>
    request<DeficiencyReport>(`/applications/${id}/deficiency-report`),
  /** The RULE-DOC-01 document pre-check (FR-06) — required documents,
   * Affidavit 2, DSC. Read-only and advisory: it names candidates and
   * always carries `needs_review` (the DSC leg is a stub). */
  docCheck: (id: string) =>
    request<DocCheck>(`/applications/${id}/doc-check`),
  /** Stage the pre-check's missing items as DRAFT deficiencies — the
   * officer's deliberate act. Drafts are never shown to the institution
   * and never move or block the case; idempotent per line. */
  stageDocCheckDrafts: (id: string) =>
    request<DocCheckStaged>(`/applications/${id}/doc-check/drafts`, {
      method: "POST",
    }),
  createDeficiency: (
    id: string,
    payload: {
      document_id?: string | null;
      extracted_field_id?: string | null;
      category?: string;
      rule_key?: string | null;
      field_name?: string | null;
      extracted_value?: unknown;
      explanation: string;
      corrective_action: string;
      status?: "draft" | "open";
    },
  ) =>
    request<DeficiencyRow>(`/applications/${id}/deficiencies`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateDeficiency: (
    id: string,
    deficiencyId: string,
    payload: {
      explanation?: string;
      corrective_action?: string;
      status?: "draft" | "open" | "addressed" | "closed";
      resolution_note?: string;
    },
  ) =>
    request<DeficiencyRow>(
      `/applications/${id}/deficiencies/${deficiencyId}`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    ),
  closeDeficiency: (id: string, deficiencyId: string, resolutionNote: string = "") =>
    request<DeficiencyRow>(
      `/applications/${id}/deficiencies/${deficiencyId}/close`,
      {
        method: "POST",
        body: JSON.stringify({ resolution_note: resolutionNote }),
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
  recordFindingDisposition: (
    applicationId: string,
    findingId: string,
    disposition: "confirmed" | "dismissed" | "clarification_requested",
    reason = "",
  ) =>
    request<{ finding_id: string; disposition: string; reason: string }>(
      `/applications/${applicationId}/compliance/findings/${findingId}/disposition`,
      {
        method: "POST",
        body: JSON.stringify({ disposition, reason }),
      },
    ),
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
    request<{
      ok: boolean;
      checked: number;
      first_broken_seq: number | null;
      reason: string;
    }>("/audit/verify"),
  recordAuditVerification: () =>
    request<{
      ok: boolean;
      checked: number;
      first_broken_seq: number | null;
      reason: string;
      verification_event_seq: number;
    }>("/audit/verify", { method: "POST" }),
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
  exportReports: (format: "csv" | "pdf") => download(`/reports/export?format=${format}`),

  // --- Expert Visit Committee scheduling ---
  evcCommittees: () => request<EvcCommittee[]>("/evc/committees"),
  evcQueue: () => request<EvcQueue>("/evc/queue"),
  evcCalendar: () => request<EvcRegionCalendar>("/evc/calendar"),
  evcVisits: (id: string) => request<EvcVisit[]>(`/applications/${id}/evc/visits`),
  evcExperts: (id: string, committeeId: string) =>
    request<Array<{ id: string; name: string }>>(
      `/applications/${id}/evc/committees/${committeeId}/experts`,
    ),
  confirmEvcVisit: (applicationId: string, visitId: string) =>
    request<EvcVisit>(
      `/applications/${applicationId}/evc/visits/${visitId}/confirm`,
      { method: "POST" },
    ),
  uploadEvcReportDocument: (applicationId: string, visitId: string, file: File) => {
    const form = new FormData();
    form.set("file", file);
    return request<UploadResult>(
      `/applications/${applicationId}/evc/visits/${visitId}/report/document`,
      { method: "POST", body: form },
    );
  },
  submitEvcReport: (
    applicationId: string,
    visitId: string,
    body: {
      document_id: string;
      summary: string;
      deficiency_present: boolean;
      fraud_flag: boolean;
      fraud_referral_reason?: string;
    },
  ) =>
    request<EvcReport>(
      `/applications/${applicationId}/evc/visits/${visitId}/report`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  evcReport: (applicationId: string, visitId: string) =>
    request<EvcReport>(
      `/applications/${applicationId}/evc/visits/${visitId}/report`,
    ),
  scheduleEvcVisit: (
    id: string,
    payload: {
      scheduled_date: string;
      visit_mode: "online" | "physical";
      venue?: string;
      meeting_url?: string | null;
      committee_id?: string | null;
      expert_user_ids?: string[];
      notes?: string;
    },
  ) =>
    request<EvcVisit>(`/applications/${id}/evc/visits`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  shcQueue: () =>
    request<{ count: number; rows: ShcQueueRow[] }>("/shc/queue"),
  scheduleShcHearing: (
    reportId: string,
    payload: {
      scheduled_date: string;
      visit_mode: "online" | "physical";
      venue?: string;
      meeting_url?: string | null;
    },
  ) =>
    request<NonNullable<ShcQueueRow["hearing"]>>(
      `/shc/queue/${reportId}/hearing`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  recordShcRecommendation: (
    reportId: string,
    payload: { compliance_record: string; recommendation: string },
  ) =>
    request<{ id: string; report_id: string; status: string; recorded_at: string }>(
      `/shc/queue/${reportId}/recommendation`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  executiveQueue: () =>
    request<{ count: number; rows: ExecutiveQueueRow[] }>(
      "/executive-committee/queue",
    ),
  appealWindow: (applicationId: string) =>
    request<AppealWindow>(`/applications/${applicationId}/appeal-window`),
  applicationAppeal: (applicationId: string) =>
    request<{ application_id: string; appeal: AppealRecord | null }>(`/applications/${applicationId}/appeal`),
  fileAppeal: (applicationId: string, grounds: string, supportingDocumentIds: string[]) =>
    request<AppealRecord>(`/applications/${applicationId}/appeals`, {
      method: "POST",
      body: JSON.stringify({ grounds, supporting_document_ids: supportingDocumentIds }),
    }),
  registerAppealRepresentatives: (appealId: string, representatives: {
    name: string; institutional_role: string; id_document_id: string; authorization_attested: boolean;
  }[]) => request<AppealRecord>(`/appeals/${appealId}/representatives`, {
    method: "POST", body: JSON.stringify({ representatives }),
  }),
  sacAppeals: () => request<{ rows: AppealRecord[] }>("/sac/appeals"),
  scheduleAppealHearing: (appealId: string, payload: { hearing_at: string; venue?: string; meeting_url?: string }) =>
    request<AppealRecord>(`/sac/appeals/${appealId}/schedule`, { method: "POST", body: JSON.stringify(payload) }),
  recordAppealHearing: (appealId: string, recommendation: string) =>
    request<AppealRecord>(`/sac/appeals/${appealId}/hearing-record`, {
      method: "POST", body: JSON.stringify({ recommendation }),
    }),
  councilAppeals: () => request<{ rows: AppealRecord[] }>("/council/appeals"),
  uploadCouncilDecisionOrder: (applicationId: string, file: File) => {
    const form = new FormData();
    form.set("file", file);
    return request<UploadResult>(`/applications/${applicationId}/documents/council-decision-orders`, {
      method: "POST", body: form,
    });
  },
  recordCouncilDecision: (appealId: string, payload: { outcome: "approved" | "not_approved"; decision: string; decision_document_id: string }) =>
    request<AppealRecord>(`/council/appeals/${appealId}/decision`, { method: "POST", body: JSON.stringify(payload) }),
  reopening: (applicationId: string) =>
    request<{ application_id: string; reopening: ReopeningRecord | null }>(`/applications/${applicationId}/reopening`),
  requestReopening: (applicationId: string, reason: string, resolutionDocumentId: string) =>
    request<ReopeningRecord>(`/applications/${applicationId}/reopening`, {
      method: "POST", body: JSON.stringify({ reason, resolution_document_id: resolutionDocumentId }),
    }),
  reopeningQueue: () => request<{ items: ReopeningRecord[] }>("/reopening/queue"),
  reviewReopening: (id: string, payload: { approved: boolean; reason: string; public_notice_document_id?: string }) =>
    request<ReopeningRecord>(`/reopening/${id}/review`, { method: "POST", body: JSON.stringify(payload) }),
  submitReopeningPayment: (id: string, evidenceDocumentId: string) =>
    request<ReopeningRecord>(`/reopening/${id}/payment`, {
      method: "POST", body: JSON.stringify({ evidence_document_id: evidenceDocumentId }),
    }),
  reviewReopeningPayment: (id: string, verified: boolean, reason: string) =>
    request<ReopeningRecord>(`/reopening/${id}/payment-review`, {
      method: "POST", body: JSON.stringify({ verified, reason }),
    }),
  downloadReopeningEvidence: async (reopeningId: string, documentId: string) => {
    const headers = new Headers();
    const token = storedToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(`${BASE}/reopening/${reopeningId}/documents/${documentId}`, { headers });
    if (!response.ok) throw new ApiError(`Could not fetch reopening evidence (${response.status})`, response.status);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `reopening-${documentId}.pdf`;
    anchor.click();
    URL.revokeObjectURL(url);
  },
  downloadAppealEvidence: async (appealId: string, documentId: string) => {
    const headers = new Headers();
    const token = storedToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(`${BASE}/appeals/${appealId}/evidence/${documentId}`, { headers });
    if (!response.ok) throw new ApiError(`Could not fetch appeal evidence (${response.status})`, response.status);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `appeal-${documentId}.pdf`;
    anchor.click();
    URL.revokeObjectURL(url);
  },
  uploadExecutiveSpeakingOrder: (applicationId: string, file: File) => {
    const form = new FormData();
    form.set("file", file);
    return request<UploadResult>(
      `/applications/${applicationId}/documents/executive-speaking-orders`,
      { method: "POST", body: form },
    );
  },
  recordExecutiveDecision: (
    applicationId: string,
    payload: {
      outcome: "approved" | "rejected";
      speaking_order_document_id: string;
      reason: string;
      expected_baseline_version?: number;
    },
  ) =>
    request<{
      accepted: boolean;
      action: string;
      from_state: string;
      to_state: string;
      reasons: string[];
      speaking_order_document_id: string;
    }>(`/executive-committee/applications/${applicationId}/decision`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  downloadCommitteeReport: async (queueItemId: string) => {
    const headers = new Headers();
    const token = storedToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(
      `${BASE}/executive-committee/queue/${queueItemId}/document`,
      { headers },
    );
    if (!response.ok) {
      throw new ApiError(`Could not fetch the report (${response.status})`, response.status);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "committee-report.pdf";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  },

  // --- Demo clock (admin only; refuses in production on the server) ---
  demoClockStatus: () => request<DemoClockStatus>("/admin/demo-clock"),
  demoClockAdvance: (days: number) =>
    request<DemoClockMove>("/admin/demo-clock/advance", {
      method: "POST",
      body: JSON.stringify({ days }),
    }),
  demoClockSet: (moment: string) =>
    request<DemoClockMove>("/admin/demo-clock/set", {
      method: "POST",
      body: JSON.stringify({ moment }),
    }),
  demoClockReset: () => request<DemoClockMove>("/admin/demo-clock/reset", { method: "POST" }),
};

export { BASE as API_BASE };
