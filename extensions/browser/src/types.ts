export interface ConfigStatus {
  ready: boolean;
  error: string | null;
  model: string | null;
  api_key_configured: boolean;
  github_token_configured: boolean;
}

export interface RunRecord {
  id: string;
  status: string;
  source_kind: "diff" | "github" | "gitlab";
  source_ref: string;
  provider: string;
  spent_cny: string;
  budget_cny: string;
  updated_at: string;
  config: {
    output_language?: "zh-CN" | "en-US";
    source_metadata?: {
      head_sha?: string;
    };
  };
}

export interface RunListItem {
  run: RunRecord;
  finding_count: number;
}

export interface Finding {
  id: string;
  trace_id: string;
  file_path: string;
  side: "LEFT" | "RIGHT";
  old_line: number | null;
  new_line: number | null;
  severity: "critical" | "high" | "medium" | "low";
  category: string;
  title: string;
  explanation: string;
  suggestion: string;
  disposition: "accept" | "reference";
  effective_confidence: "high" | "medium" | "low";
}

export interface RunDetail {
  run: RunRecord;
  findings: Finding[];
}

export interface ReviewJob {
  id: string;
  run_id: string;
  status: "queued" | "running" | "completed" | "failed";
  error: string | null;
}

export interface PlannedComment {
  finding_id: string;
  fingerprint: string;
  path: string;
  line: number;
  side: "LEFT" | "RIGHT";
  title: string;
  body: string;
  action: "preview" | "create" | "update" | "unchanged";
  remote_comment_id: number | null;
  remote_url: string | null;
}

export interface PublicationResult {
  provider: "github";
  source_ref: string;
  dry_run: boolean;
  reviewed_head_sha: string;
  eligible_count: number;
  skipped_count: number;
  created_count: number;
  updated_count: number;
  unchanged_count: number;
  comments: PlannedComment[];
}
