export interface RunRecord {
  id: string;
  status: "pending" | "running" | "completed" | "budget_exhausted" | "failed";
  source_ref: string;
  next_chunk_index: number;
  total_chunks: number;
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
  line: number;
  side: "LEFT" | "RIGHT";
  old_line: number | null;
  new_line: number | null;
  severity: "critical" | "high" | "medium" | "low";
  title: string;
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
