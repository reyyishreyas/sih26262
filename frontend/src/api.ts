import type {
  AlertRow,
  ApplicationSummary,
  AuditEvent,
  CaseDetail,
  ComplianceBatch,
  OfficerDashboard,
  RehearsalReport,
  SessionUser,
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
      transition_id?: string;
    }>(`/applications/${id}/transitions`, {
      method: "POST",
      body: JSON.stringify({ action, reason }),
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
};

export { BASE as API_BASE };
