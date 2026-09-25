from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class SourceKind(StrEnum):
    DIFF = "diff"
    GITHUB = "github"
    GITLAB = "gitlab"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    FAILED = "failed"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Disposition(StrEnum):
    ACCEPT = "accept"
    REFERENCE = "reference"


class DiffSide(StrEnum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"


class SourceSnapshot(BaseModel):
    kind: SourceKind
    reference: str
    provider: str
    diff: str
    metadata: dict[str, str | int | bool | None] = Field(default_factory=dict)
    file_contexts: list[FileContext] = Field(default_factory=list)


class FileContext(BaseModel):
    file_path: str
    old_path: str
    new_path: str
    status: str
    base_commit_sha: str | None = None
    head_commit_sha: str | None = None
    base_content: str | None = None
    head_content: str | None = None
    base_content_sha256: str | None = None
    head_content_sha256: str | None = None


class DiffChunk(BaseModel):
    index: int
    file_path: str
    content: str
    added_lines: set[int] = Field(default_factory=set)
    removed_lines: set[int] = Field(default_factory=set)


class ToolObservation(BaseModel):
    tool: str
    summary: str
    data: dict[str, object] = Field(default_factory=dict)


class FindingDraft(BaseModel):
    file_path: str
    line: int = Field(ge=1)
    side: DiffSide = DiffSide.RIGHT
    severity: Severity
    category: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    explanation: str = Field(min_length=1)
    suggestion: str = ""
    confidence: Confidence = Confidence.MEDIUM
    evidence: list[str] = Field(default_factory=list)


class ModelReview(BaseModel):
    findings: list[FindingDraft] = Field(default_factory=list)


class Finding(BaseModel):
    id: str
    run_id: str
    trace_id: str
    file_path: str
    line: int
    side: DiffSide
    old_line: int | None = None
    new_line: int | None = None
    severity: Severity
    category: str
    title: str
    explanation: str
    suggestion: str
    model_confidence: Confidence
    effective_confidence: Confidence
    disposition: Disposition
    evidence: list[str]
    fingerprint: str


class LLMCallResult(BaseModel):
    content: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    request_id: str | None = None


class TraceRecord(BaseModel):
    id: str
    run_id: str
    chunk_index: int
    file_path: str
    diff_sha256: str
    prompt_sha256: str
    prompt_path: Path
    response_path: Path
    tools: list[ToolObservation]
    model: str
    request_id: str | None
    input_tokens: int
    output_tokens: int
    cost_cny: Decimal
    error: str | None = None


class RunRecord(BaseModel):
    id: str
    status: RunStatus
    source_kind: SourceKind
    source_ref: str
    provider: str
    diff_sha256: str
    raw_diff_path: Path
    sanitized_diff_path: Path
    next_chunk_index: int
    total_chunks: int
    budget_cny: Decimal
    spent_cny: Decimal
    config: dict[str, object]
    error: str | None = None
    created_at: str
    updated_at: str


class ReviewResult(BaseModel):
    run: RunRecord
    findings: list[Finding]
    report: str
    report_path: Path | None = None
