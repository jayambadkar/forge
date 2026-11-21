import type { AuditEvent, CaseDetail, CasePage, DashboardStats, Institution, Job } from "./types";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json() as Promise<T>;
}

export type CaseQuery = {
  institution?: string;
  verdict?: string;
  reason?: string;
  q?: string;
  rule?: string;
  risk?: string;
  status?: string;
  sort?: string;
  limit?: number;
  offset?: number;
};

export function fetchInstitutions() {
  return get<Institution[]>("/api/institutions");
}

export function fetchDashboard() {
  return get<DashboardStats>("/api/dashboard");
}

export function fetchHealth() {
  return get<{ ok: boolean; environment: string; syncedAt: string }>("/api/health");
}

export function fetchCases(params: CaseQuery) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  if (!query.has("limit")) query.set("limit", "25");
  return get<CasePage>(`/api/cases?${query}`);
}

export function fetchCase(institution: string, caseId: string) {
  return get<CaseDetail>(`/api/cases/${institution}/${encodeURIComponent(caseId)}`);
}

export async function act(
  institution: string,
  caseId: string,
  body: { action: string; actor: string; verdict?: string; note?: string },
) {
  const response = await fetch(`/api/cases/${institution}/${encodeURIComponent(caseId)}/actions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => ({ error: response.statusText }));
    const message =
      typeof payload === "object" &&
      payload !== null &&
      "error" in payload &&
      typeof payload.error === "string"
        ? payload.error
        : response.statusText;
    throw new Error(message);
  }
  return response.json() as Promise<unknown>;
}

export function fetchAudit(params: {
  institution?: string;
  caseId?: string;
  kind?: string;
  q?: string;
  limit?: number;
}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) query.set(key, String(value));
  }
  return get<AuditEvent[]>(`/api/audit?${query}`);
}

export function fetchNotifications() {
  return get<{ unread: number; items: AuditEvent[] }>("/api/notifications");
}

export function markNotificationsRead() {
  return fetch("/api/notifications/read", { method: "POST" });
}

export function fetchJobs() {
  return get<Job[]>("/api/runs");
}

export async function startRun(institution: string, mode: "run" | "replay") {
  const response = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ institution, mode }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<{ id: string; institution: string; mode: string }>;
}

export function exportHref(
  kind: "decisions" | "audit",
  format: "jsonl" | "csv",
  params: Record<string, string>,
) {
  const query = new URLSearchParams({ format, ...params });
  const path = kind === "audit" ? "/api/audit/export" : "/api/export";
  return `${path}?${query}`;
}
