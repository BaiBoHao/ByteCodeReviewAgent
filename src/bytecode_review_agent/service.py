from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from bytecode_review_agent.budget import BudgetGuard, Pricing
from bytecode_review_agent.config import Settings
from bytecode_review_agent.context import SelectedContext, select_context
from bytecode_review_agent.diff_parser import chunk_diff
from bytecode_review_agent.errors import (
    BudgetExceeded,
    ModelResponseError,
    ReviewAgentError,
    RunExecutionError,
    SourceError,
)
from bytecode_review_agent.llm import ReviewerClient, parse_model_review
from bytecode_review_agent.models import (
    Confidence,
    DiffSide,
    DiffChunk,
    Disposition,
    Finding,
    FindingDraft,
    FileContext,
    ReviewResult,
    RunStatus,
    ToolObservation,
    TraceRecord,
)
from bytecode_review_agent.prompts import SYSTEM_PROMPT, build_user_prompt, trace_prompt
from bytecode_review_agent.providers import SourceLoader
from bytecode_review_agent.report import MarkdownReporter
from bytecode_review_agent.security import SecretRedactor
from bytecode_review_agent.storage import SQLiteStorage
from bytecode_review_agent.tools import ToolRegistry
from bytecode_review_agent.utils import atomic_write_text, estimate_tokens, sha256_text


class ReviewService:
    def __init__(
        self,
        *,
        settings: Settings,
        reviewer: ReviewerClient,
        storage: SQLiteStorage,
        sources: SourceLoader,
        tools: ToolRegistry,
        reporter: MarkdownReporter | None = None,
    ) -> None:
        self.settings = settings
        self.reviewer = reviewer
        self.storage = storage
        self.sources = sources
        self.tools = tools
        self.reporter = reporter or MarkdownReporter()
        self.redactor = SecretRedactor()
        self.pricing = Pricing(
            input_cny_per_million=settings.input_price_cny_per_million,
            output_cny_per_million=settings.output_price_cny_per_million,
        )

    def start(
        self,
        source_value: str,
        *,
        budget_cny: Decimal,
        output_path: Path | None = None,
        stdin_text: str | None = None,
        run_id: str | None = None,
    ) -> ReviewResult:
        if budget_cny <= 0:
            raise SourceError("budget must be greater than zero")
        source = self.sources.load(source_value, stdin_text=stdin_text)
        run_id = run_id or f"run_{uuid4().hex[:16]}"
        run_dir = self.settings.artifacts_dir / run_id
        raw_path = run_dir / "raw.diff"
        sanitized_path = run_dir / "sanitized.diff"
        contexts_path = run_dir / "contexts.json"
        sanitized, redaction_count = self.redactor.redact(source.diff)
        sanitized_contexts: list[FileContext] = []
        for context in source.file_contexts:
            base_content = context.base_content
            head_content = context.head_content
            if base_content is not None:
                base_content, matches = self.redactor.redact(base_content)
                redaction_count += matches
            if head_content is not None:
                head_content, matches = self.redactor.redact(head_content)
                redaction_count += matches
            sanitized_contexts.append(
                context.model_copy(
                    update={
                        "base_content": base_content,
                        "head_content": head_content,
                    }
                )
            )
        chunks = chunk_diff(sanitized, self.settings.max_chunk_chars)
        if not chunks:
            raise SourceError("no reviewable text was found in the diff")

        atomic_write_text(raw_path, source.diff)
        atomic_write_text(sanitized_path, sanitized)
        atomic_write_text(
            contexts_path,
            json.dumps(
                [item.model_dump(mode="json") for item in sanitized_contexts],
                ensure_ascii=False,
            ),
        )
        self.storage.create_run(
            run_id=run_id,
            source=source,
            diff_sha256=sha256_text(source.diff),
            raw_diff_path=raw_path.resolve(),
            sanitized_diff_path=sanitized_path.resolve(),
            total_chunks=len(chunks),
            budget_cny=budget_cny,
            config={
                "model": self.reviewer.model,
                "input_price_cny_per_million": str(self.pricing.input_cny_per_million),
                "output_price_cny_per_million": str(self.pricing.output_cny_per_million),
                "max_chunk_chars": self.settings.max_chunk_chars,
                "max_output_tokens": self.settings.max_output_tokens,
                "enabled_tools": list(self.settings.enabled_tools),
                "redaction_count": redaction_count,
                "context_file_count": len(sanitized_contexts),
                "max_context_chars": self.settings.max_context_chars,
            },
        )
        self.storage.checkpoint(
            run_id,
            "source_loaded",
            payload={
                "provider": source.provider,
                "diff_sha256": sha256_text(source.diff),
                "raw_diff_path": str(raw_path.resolve()),
            },
        )
        self.storage.checkpoint(
            run_id,
            "secrets_redacted",
            payload={"redaction_count": redaction_count},
        )
        self.storage.checkpoint(
            run_id,
            "context_loaded",
            payload={
                "file_count": len(sanitized_contexts),
                "artifact_path": str(contexts_path.resolve()),
            },
        )
        self.storage.checkpoint(run_id, "diff_chunked", payload={"chunks": len(chunks)})
        return self._execute(run_id, output_path=output_path)

    def resume(
        self,
        run_id: str,
        *,
        budget_cny: Decimal | None = None,
        output_path: Path | None = None,
    ) -> ReviewResult:
        run = self.storage.get_run(run_id)
        if budget_cny is not None and budget_cny != run.budget_cny:
            self.storage.update_budget(run_id, budget_cny)
            run = self.storage.get_run(run_id)
        if run.status == RunStatus.COMPLETED:
            return self._result(run_id, output_path)
        self._validate_resume_config(run.config)
        self.storage.checkpoint(
            run_id, "resumed", payload={"from_chunk": run.next_chunk_index}
        )
        return self._execute(run_id, output_path=output_path)

    def _validate_resume_config(self, config: dict[str, object]) -> None:
        expected = {
            "model": self.reviewer.model,
            "input_price_cny_per_million": str(self.pricing.input_cny_per_million),
            "output_price_cny_per_million": str(self.pricing.output_cny_per_million),
        }
        mismatches = [key for key, value in expected.items() if config.get(key) != value]
        if mismatches:
            raise ReviewAgentError(
                "resume configuration differs from the original run: " + ", ".join(mismatches)
            )

    def _execute(self, run_id: str, *, output_path: Path | None) -> ReviewResult:
        run = self.storage.get_run(run_id)
        try:
            sanitized = run.sanitized_diff_path.read_text(encoding="utf-8")
            context_path = run.sanitized_diff_path.with_name("contexts.json")
            if context_path.is_file():
                raw_contexts = json.loads(context_path.read_text(encoding="utf-8"))
                contexts = [FileContext.model_validate(item) for item in raw_contexts]
            else:
                contexts = []
            contexts_by_path = {
                path: context
                for context in contexts
                for path in {context.file_path, context.old_path, context.new_path}
            }
            max_chars = int(run.config["max_chunk_chars"])
            chunks = chunk_diff(sanitized, max_chars)
            if len(chunks) != run.total_chunks:
                raise ReviewAgentError("stored diff no longer produces the original chunk layout")

            for chunk in chunks[run.next_chunk_index :]:
                run = self.storage.get_run(run_id)
                self.storage.mark_running(run_id, chunk.index)
                observations = self.tools.run(self.settings.enabled_tools, chunk)
                selected_context = select_context(
                    chunk,
                    contexts_by_path.get(chunk.file_path),
                    max_chars=int(
                        run.config.get("max_context_chars", self.settings.max_context_chars)
                    ),
                )
                if selected_context:
                    observations.append(self._context_observation(selected_context))
                user_prompt = build_user_prompt(chunk, observations, selected_context)
                complete_prompt = trace_prompt(SYSTEM_PROMPT, user_prompt)
                max_output = int(run.config["max_output_tokens"])
                BudgetGuard(run.budget_cny, run.spent_cny, self.pricing).reserve(
                    estimate_tokens(complete_prompt), max_output
                )

                trace_id = f"trace_{uuid4().hex[:16]}"
                run_dir = self.settings.artifacts_dir / run_id
                prompt_path = run_dir / f"{trace_id}.prompt.txt"
                response_path = run_dir / f"{trace_id}.response.json"
                atomic_write_text(prompt_path, complete_prompt)
                call = self.reviewer.review(SYSTEM_PROMPT, user_prompt, max_output)
                atomic_write_text(response_path, call.content)
                cost = self.pricing.cost(call.input_tokens, call.output_tokens)
                trace = TraceRecord(
                    id=trace_id,
                    run_id=run_id,
                    chunk_index=chunk.index,
                    file_path=chunk.file_path,
                    diff_sha256=sha256_text(chunk.content),
                    prompt_sha256=sha256_text(complete_prompt),
                    prompt_path=prompt_path.resolve(),
                    response_path=response_path.resolve(),
                    tools=observations,
                    model=self.reviewer.model,
                    request_id=call.request_id,
                    input_tokens=call.input_tokens,
                    output_tokens=call.output_tokens,
                    cost_cny=cost,
                )
                try:
                    review = parse_model_review(call.content)
                except ModelResponseError as exc:
                    failed_trace = trace.model_copy(update={"error": str(exc)})
                    self.storage.record_failed_trace(
                        failed_trace, total_spent_cny=run.spent_cny + cost
                    )
                    raise

                findings = [
                    self._validate_finding(run_id, trace_id, chunk, draft)
                    for draft in review.findings
                ]
                self.storage.complete_chunk(
                    trace,
                    findings,
                    next_chunk_index=chunk.index + 1,
                    total_spent_cny=run.spent_cny + cost,
                )

            self.storage.mark_terminal(run_id, RunStatus.COMPLETED)
        except BudgetExceeded as exc:
            self.storage.mark_terminal(run_id, RunStatus.BUDGET_EXHAUSTED, str(exc))
        except RunExecutionError:
            raise
        except Exception as exc:
            self.storage.mark_terminal(run_id, RunStatus.FAILED, str(exc))
            raise RunExecutionError(run_id, str(exc)) from exc
        return self._result(run_id, output_path)

    def _validate_finding(
        self, run_id: str, trace_id: str, chunk: DiffChunk, draft: FindingDraft
    ) -> Finding:
        expected_path = chunk.file_path.replace("\\", "/")
        reported_path = draft.file_path.replace("\\", "/")
        allowed_lines = (
            chunk.added_lines if draft.side == DiffSide.RIGHT else chunk.removed_lines
        )
        valid_location = reported_path == expected_path and draft.line in allowed_lines
        has_evidence = any(item.strip() for item in draft.evidence)

        if draft.confidence == Confidence.HIGH and valid_location and has_evidence:
            effective = Confidence.HIGH
        elif draft.confidence != Confidence.LOW and valid_location:
            effective = Confidence.MEDIUM
        else:
            effective = Confidence.LOW
        disposition = (
            Disposition.ACCEPT if effective == Confidence.HIGH else Disposition.REFERENCE
        )
        fingerprint = sha256_text(
            f"{expected_path}:{draft.side.value}:{draft.line}:"
            f"{draft.category.lower()}:{draft.title.lower()}"
        )
        return Finding(
            id=f"finding_{uuid4().hex[:16]}",
            run_id=run_id,
            trace_id=trace_id,
            file_path=expected_path,
            line=draft.line,
            side=draft.side,
            old_line=draft.line if draft.side == DiffSide.LEFT else None,
            new_line=draft.line if draft.side == DiffSide.RIGHT else None,
            severity=draft.severity,
            category=draft.category,
            title=draft.title,
            explanation=draft.explanation,
            suggestion=draft.suggestion,
            model_confidence=draft.confidence,
            effective_confidence=effective,
            disposition=disposition,
            evidence=draft.evidence,
            fingerprint=fingerprint,
        )

    def _context_observation(self, context: SelectedContext) -> ToolObservation:
        return ToolObservation(
            tool="context_selector",
            summary=(
                f"selected {context.strategy} context with "
                f"{len(context.symbols)} symbols"
            ),
            data={
                "strategy": context.strategy,
                "symbols": context.symbols,
                "base_ranges": context.base_ranges,
                "head_ranges": context.head_ranges,
                "base_content_sha256": context.base_content_sha256,
                "head_content_sha256": context.head_content_sha256,
            },
        )

    def _result(self, run_id: str, output_path: Path | None) -> ReviewResult:
        run = self.storage.get_run(run_id)
        findings = self.storage.list_findings(run_id)
        report = self.reporter.render(run, findings)
        resolved_output: Path | None = None
        if output_path is not None:
            resolved_output = output_path.expanduser().resolve()
            atomic_write_text(resolved_output, report)
        return ReviewResult(
            run=run, findings=findings, report=report, report_path=resolved_output
        )
