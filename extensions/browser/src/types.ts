export interface ConfigStatus {
  ready: boolean;
  error: string | null;
  model: string | null;
  api_key_configured: boolean;
}

export interface RunRecord {
  id: string;
  status: string;
  source_ref: string;
  spent_cny: string;
  budget_cny: string;
  updated_at: string;
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
