import type { ConfigStatus, ReviewJob, RunDetail, RunListItem } from "./types";

const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
const sessionToken = fragment.get("session");
if (sessionToken) {
  window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(sessionToken ? { "X-Review-Agent-Token": sessionToken } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || `请求失败：${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  bootstrap: () => request<{ status: string; version: string }>("/api/bootstrap"),
  health: () => request<{ status: string; version: string; local_only: boolean }>("/api/health"),
  config: () => request<ConfigStatus>("/api/config"),
  tools: () => request<{ tools: string[] }>("/api/tools"),
  runs: () => request<RunListItem[]>("/api/runs?limit=50"),
  run: (runId: string) => request<RunDetail>(`/api/runs/${runId}`),
  trace: (traceId: string) => request<Record<string, unknown>>(`/api/traces/${traceId}`),
  job: (jobId: string) => request<ReviewJob>(`/api/jobs/${jobId}`),
  createReview: (source: string, budget: number) =>
    request<ReviewJob>("/api/reviews", {
      method: "POST",
      body: JSON.stringify({ source, budget_cny: String(budget) }),
    }),
  resume: (runId: string, budget?: number) =>
    request<ReviewJob>(`/api/runs/${runId}/resume`, {
      method: "POST",
      body: JSON.stringify({ budget_cny: budget ? String(budget) : null }),
    }),
};
