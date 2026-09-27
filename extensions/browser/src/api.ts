import type {
  ConfigStatus,
  PublicationResult,
  ReviewJob,
  RunDetail,
  RunListItem,
} from "./types";

export class LocalRunnerApi {
  constructor(
    private readonly baseUrl: string,
    private readonly token: string | null,
  ) {}

  private async request<T>(path: string, init?: RequestInit, authenticated = true): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(authenticated && this.token
          ? { "X-Review-Agent-Token": this.token }
          : {}),
        ...init?.headers,
      },
    });
    if (!response.ok) {
      const body = (await response.json().catch(() => ({ detail: response.statusText }))) as {
        detail?: string;
      };
      throw new Error(body.detail || `请求失败：${response.status}`);
    }
    return response.json() as Promise<T>;
  }

  pair(code: string): Promise<{ session_token: string }> {
    return this.request(
      "/api/pair",
      { method: "POST", body: JSON.stringify({ code }) },
      false,
    );
  }

  health(): Promise<{ status: string; version: string }> {
    return this.request("/api/health");
  }

  config(): Promise<ConfigStatus> {
    return this.request("/api/config");
  }

  runs(): Promise<RunListItem[]> {
    return this.request("/api/runs?limit=10");
  }

  run(runId: string): Promise<RunDetail> {
    return this.request(`/api/runs/${runId}`);
  }

  createReview(source: string, budget: number): Promise<ReviewJob> {
    return this.request("/api/reviews", {
      method: "POST",
      body: JSON.stringify({ source, budget_cny: String(budget) }),
    });
  }

  job(jobId: string): Promise<ReviewJob> {
    return this.request(`/api/jobs/${jobId}`);
  }

  trace(traceId: string): Promise<Record<string, unknown>> {
    return this.request(`/api/traces/${traceId}`);
  }

  publish(runId: string, apply = false): Promise<PublicationResult> {
    return this.request(`/api/runs/${runId}/publish`, {
      method: "POST",
      body: JSON.stringify({ apply }),
    });
  }
}
