from __future__ import annotations

from collections.abc import Iterable

from bytecode_review_agent.models import Disposition, Finding, RunRecord


def _inline(value: str) -> str:
    return value.replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ").strip()


class MarkdownReporter:
    def render(self, run: RunRecord, findings: list[Finding]) -> str:
        accepted = [item for item in findings if item.disposition == Disposition.ACCEPT]
        reference = [item for item in findings if item.disposition == Disposition.REFERENCE]
        sections = [
            "# Code Review Report",
            "",
            f"- Run: `{run.id}`",
            f"- Status: `{run.status.value}`",
            f"- Source: `{_inline(run.source_ref)}`",
            f"- Diff SHA-256: `{run.diff_sha256}`",
            f"- Budget: `{run.budget_cny} CNY`",
            f"- Recorded cost: `{run.spent_cny} CNY`",
            f"- Progress: `{run.next_chunk_index}/{run.total_chunks}` chunks",
            "",
        ]
        if run.error:
            sections.extend([f"> {_inline(run.error)}", ""])
        sections.extend(self._finding_section("High-confidence findings", accepted))
        sections.extend(self._finding_section("Reference findings", reference))
        sections.extend(
            [
                "## Traceability",
                "",
                (
                    "Each finding includes a trace ID. Use `review-agent trace <TRACE_ID>` to "
                    "inspect the model request, deterministic tool observations and stored "
                    "response."
                ),
                "",
            ]
        )
        return "\n".join(sections)

    def _finding_section(self, title: str, findings: Iterable[Finding]) -> list[str]:
        items = list(findings)
        output = [f"## {title}", ""]
        if not items:
            return output + ["No findings.", ""]
        for finding in items:
            output.extend(
                [
                    f"### [{finding.severity.value.upper()}] {_inline(finding.title)}",
                    "",
                    f"- Location: `{_inline(finding.file_path)}:{finding.line}`",
                    f"- Category: `{_inline(finding.category)}`",
                    f"- Confidence: `{finding.effective_confidence.value}`",
                    f"- Trace: `{finding.trace_id}`",
                    "",
                    _inline(finding.explanation),
                    "",
                ]
            )
            if finding.suggestion:
                output.extend([f"Suggested action: {_inline(finding.suggestion)}", ""])
            if finding.evidence:
                output.extend(["Evidence:", ""])
                output.extend(f"- {_inline(item)}" for item in finding.evidence)
                output.append("")
        return output
