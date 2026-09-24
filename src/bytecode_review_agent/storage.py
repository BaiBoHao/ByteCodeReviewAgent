from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterator

from bytecode_review_agent.errors import RunNotFound
from bytecode_review_agent.models import (
    Finding,
    RunRecord,
    RunStatus,
    SourceSnapshot,
    TraceRecord,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SQLiteStorage:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    diff_sha256 TEXT NOT NULL,
                    raw_diff_path TEXT NOT NULL,
                    sanitized_diff_path TEXT NOT NULL,
                    next_chunk_index INTEGER NOT NULL,
                    total_chunks INTEGER NOT NULL,
                    budget_cny TEXT NOT NULL,
                    spent_cny TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    stage TEXT NOT NULL,
                    chunk_index INTEGER,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS traces (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    chunk_index INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    diff_sha256 TEXT NOT NULL,
                    prompt_sha256 TEXT NOT NULL,
                    prompt_path TEXT NOT NULL,
                    response_path TEXT NOT NULL,
                    tools_json TEXT NOT NULL,
                    model TEXT NOT NULL,
                    request_id TEXT,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    cost_cny TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS findings (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    trace_id TEXT NOT NULL REFERENCES traces(id),
                    file_path TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    severity TEXT NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    suggestion TEXT NOT NULL,
                    model_confidence TEXT NOT NULL,
                    effective_confidence TEXT NOT NULL,
                    disposition TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    UNIQUE(run_id, fingerprint)
                );
                """
            )

    def create_run(
        self,
        *,
        run_id: str,
        source: SourceSnapshot,
        diff_sha256: str,
        raw_diff_path: Path,
        sanitized_diff_path: Path,
        total_chunks: int,
        budget_cny: Decimal,
        config: dict[str, object],
    ) -> RunRecord:
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    id, status, source_kind, source_ref, provider, diff_sha256,
                    raw_diff_path, sanitized_diff_path, next_chunk_index, total_chunks,
                    budget_cny, spent_cny, config_json, error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, '0', ?, NULL, ?, ?)
                """,
                (
                    run_id,
                    RunStatus.PENDING.value,
                    source.kind.value,
                    source.reference,
                    source.provider,
                    diff_sha256,
                    str(raw_diff_path),
                    str(sanitized_diff_path),
                    total_chunks,
                    str(budget_cny),
                    json.dumps(config, ensure_ascii=False, default=str),
                    timestamp,
                    timestamp,
                ),
            )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> RunRecord:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise RunNotFound(f"run not found: {run_id}")
        return self._run_from_row(row)

    def list_runs(self, limit: int = 20) -> list[RunRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._run_from_row(row) for row in rows]

    def _run_from_row(self, row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            id=row["id"],
            status=row["status"],
            source_kind=row["source_kind"],
            source_ref=row["source_ref"],
            provider=row["provider"],
            diff_sha256=row["diff_sha256"],
            raw_diff_path=Path(row["raw_diff_path"]),
            sanitized_diff_path=Path(row["sanitized_diff_path"]),
            next_chunk_index=row["next_chunk_index"],
            total_chunks=row["total_chunks"],
            budget_cny=Decimal(row["budget_cny"]),
            spent_cny=Decimal(row["spent_cny"]),
            config=json.loads(row["config_json"]),
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def checkpoint(
        self,
        run_id: str,
        stage: str,
        *,
        chunk_index: int | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO checkpoints (run_id, stage, chunk_index, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    stage,
                    chunk_index,
                    json.dumps(payload or {}, ensure_ascii=False, default=str),
                    _now(),
                ),
            )

    def mark_running(self, run_id: str, chunk_index: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE runs SET status = ?, error = NULL, updated_at = ? WHERE id = ?",
                (RunStatus.RUNNING.value, _now(), run_id),
            )
        self.checkpoint(run_id, "chunk_started", chunk_index=chunk_index)

    def complete_chunk(
        self,
        trace: TraceRecord,
        findings: list[Finding],
        *,
        next_chunk_index: int,
        total_spent_cny: Decimal,
    ) -> None:
        timestamp = _now()
        with self._connect() as connection:
            self._insert_trace(connection, trace, timestamp)
            for finding in findings:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO findings (
                        id, run_id, trace_id, file_path, line, severity, category, title,
                        explanation, suggestion, model_confidence, effective_confidence,
                        disposition, evidence_json, fingerprint
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        finding.id,
                        finding.run_id,
                        finding.trace_id,
                        finding.file_path,
                        finding.line,
                        finding.severity.value,
                        finding.category,
                        finding.title,
                        finding.explanation,
                        finding.suggestion,
                        finding.model_confidence.value,
                        finding.effective_confidence.value,
                        finding.disposition.value,
                        json.dumps(finding.evidence, ensure_ascii=False),
                        finding.fingerprint,
                    ),
                )
            connection.execute(
                """
                UPDATE runs
                SET next_chunk_index = ?, spent_cny = ?, status = ?, error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (
                    next_chunk_index,
                    str(total_spent_cny),
                    RunStatus.RUNNING.value,
                    timestamp,
                    trace.run_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO checkpoints (run_id, stage, chunk_index, payload_json, created_at)
                VALUES (?, 'chunk_completed', ?, ?, ?)
                """,
                (
                    trace.run_id,
                    trace.chunk_index,
                    json.dumps(
                        {"trace_id": trace.id, "finding_count": len(findings)},
                        ensure_ascii=False,
                    ),
                    timestamp,
                ),
            )

    def record_failed_trace(
        self, trace: TraceRecord, *, total_spent_cny: Decimal
    ) -> None:
        timestamp = _now()
        with self._connect() as connection:
            self._insert_trace(connection, trace, timestamp)
            connection.execute(
                "UPDATE runs SET spent_cny = ?, updated_at = ? WHERE id = ?",
                (str(total_spent_cny), timestamp, trace.run_id),
            )

    def _insert_trace(
        self, connection: sqlite3.Connection, trace: TraceRecord, timestamp: str
    ) -> None:
        connection.execute(
            """
            INSERT INTO traces (
                id, run_id, chunk_index, file_path, diff_sha256, prompt_sha256,
                prompt_path, response_path, tools_json, model, request_id,
                input_tokens, output_tokens, cost_cny, error, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace.id,
                trace.run_id,
                trace.chunk_index,
                trace.file_path,
                trace.diff_sha256,
                trace.prompt_sha256,
                str(trace.prompt_path),
                str(trace.response_path),
                json.dumps(
                    [item.model_dump(mode="json") for item in trace.tools],
                    ensure_ascii=False,
                ),
                trace.model,
                trace.request_id,
                trace.input_tokens,
                trace.output_tokens,
                str(trace.cost_cny),
                trace.error,
                timestamp,
            ),
        )

    def mark_terminal(self, run_id: str, status: RunStatus, error: str | None = None) -> None:
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE runs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
                (status.value, error, timestamp, run_id),
            )
            connection.execute(
                """
                INSERT INTO checkpoints (run_id, stage, chunk_index, payload_json, created_at)
                VALUES (?, ?, NULL, ?, ?)
                """,
                (
                    run_id,
                    status.value,
                    json.dumps({"error": error} if error else {}, ensure_ascii=False),
                    timestamp,
                ),
            )

    def update_budget(self, run_id: str, budget_cny: Decimal) -> None:
        run = self.get_run(run_id)
        if budget_cny <= run.spent_cny:
            raise ValueError(
                f"new budget must be greater than already spent {run.spent_cny} CNY"
            )
        with self._connect() as connection:
            connection.execute(
                "UPDATE runs SET budget_cny = ?, updated_at = ? WHERE id = ?",
                (str(budget_cny), _now(), run_id),
            )
        self.checkpoint(run_id, "budget_updated", payload={"budget_cny": str(budget_cny)})

    def list_findings(self, run_id: str) -> list[Finding]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM findings WHERE run_id = ?
                ORDER BY CASE severity
                    WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2 ELSE 3 END, file_path, line
                """,
                (run_id,),
            ).fetchall()
        return [
            Finding(
                id=row["id"],
                run_id=row["run_id"],
                trace_id=row["trace_id"],
                file_path=row["file_path"],
                line=row["line"],
                severity=row["severity"],
                category=row["category"],
                title=row["title"],
                explanation=row["explanation"],
                suggestion=row["suggestion"],
                model_confidence=row["model_confidence"],
                effective_confidence=row["effective_confidence"],
                disposition=row["disposition"],
                evidence=json.loads(row["evidence_json"]),
                fingerprint=row["fingerprint"],
            )
            for row in rows
        ]

    def get_trace(self, trace_id: str) -> dict[str, object]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT traces.*, runs.raw_diff_path, runs.diff_sha256 AS raw_diff_sha256
                FROM traces JOIN runs ON runs.id = traces.run_id
                WHERE traces.id = ?
                """,
                (trace_id,),
            ).fetchone()
        if row is None:
            raise RunNotFound(f"trace not found: {trace_id}")
        result = dict(row)
        result["tools"] = json.loads(str(result.pop("tools_json")))
        return result

    def list_checkpoints(self, run_id: str) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM checkpoints WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        result: list[dict[str, object]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(str(item.pop("payload_json")))
            result.append(item)
        return result

    def list_traces(self, run_id: str) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, chunk_index, file_path, model, request_id, input_tokens,
                       output_tokens, cost_cny, error, created_at
                FROM traces WHERE run_id = ? ORDER BY created_at
                """,
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]
