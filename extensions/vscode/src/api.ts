import type { Finding, ReviewJob, RunDetail, RunListItem } from "./types";

export class ReviewAgentApi {
  constructor(
    private readonly baseUrl: string,
    private readonly token: string,
  ) {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-Review-Agent-Token": this.token,
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

  health(): Promise<{ status: string; version: string }> {
    return this.request("/api/health");
  }

  runs(): Promise<RunListItem[]> {
    return this.request("/api/runs?limit=20");
  }

  run(runId: string): Promise<RunDetail> {
    return this.request(`/api/runs/${runId}`);
  }

  context(
    runId: string,
    filePath: string,
    side: "base" | "head",
  ): Promise<{ content: string; content_sha256: string | null }> {
    const query = new URLSearchParams({ file_path: filePath, side });
    return this.request(`/api/runs/${runId}/context?${query.toString()}`);
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

  async latestFindings(): Promise<Array<{ runId: string; finding: Finding }>> {
    const runs = await this.runs();
    const latest = runs.find((item) => item.finding_count > 0);
    if (!latest) return [];
    const detail = await this.run(latest.run.id);
    return detail.findings.map((finding) => ({ runId: latest.run.id, finding }));
  }
}
