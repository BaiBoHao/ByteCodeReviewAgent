export type RunStatus =
  | "pending"
  | "running"
  | "completed"
  | "budget_exhausted"
  | "failed";

export interface ConfigStatus {
  ready: boolean;
  error: string | null;
  env_file: string | null;
  model: string | null;
  base_url: string;
  api_key_configured: boolean;
  pairing_code: string | null;
  input_price_cny_per_million: string;
  output_price_cny_per_million: string;
  data_dir: string;
}

export interface RunRecord {
  id: string;
  status: RunStatus;
  source_kind: string;
  source_ref: string;
  provider: string;
  next_chunk_index: number;
  total_chunks: number;
  budget_cny: string;
  spent_cny: string;
  config: Record<string, unknown>;
  error: string | null;
  created_at: string;
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
  line: number;
  side: "LEFT" | "RIGHT";
  old_line: number | null;
  new_line: number | null;
  severity: "critical" | "high" | "medium" | "low";
  category: string;
  title: string;
  explanation: string;
  suggestion: string;
  effective_confidence: "high" | "medium" | "low";
  disposition: "accept" | "reference";
  evidence: string[];
}

export interface RunDetail {
  run: RunRecord;
  findings: Finding[];
  checkpoints: Array<Record<string, unknown>>;
  traces: Array<Record<string, unknown>>;
}

export interface ReviewJob {
  id: string;
  run_id: string;
  operation: "review" | "resume";
  status: "queued" | "running" | "completed" | "failed";
  error: string | null;
  run: RunRecord | null;
}
