from __future__ import annotations

from collections.abc import Iterable

from bytecode_review_agent.models import DiffSide, Disposition, Finding, RunRecord


def _inline(value: str) -> str:
    return value.replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ").strip()


class MarkdownReporter:
    def render(self, run: RunRecord, findings: list[Finding]) -> str:
        accepted = [item for item in findings if item.disposition == Disposition.ACCEPT]
        reference = [item for item in findings if item.disposition == Disposition.REFERENCE]
        sections = [
            "# 代码评审报告",
            "",
            f"- 运行 ID：`{run.id}`",
            f"- 状态：`{run.status.value}`",
            f"- 来源：`{_inline(run.source_ref)}`",
            f"- Diff SHA-256：`{run.diff_sha256}`",
            f"- 预算：`{run.budget_cny} CNY`",
            f"- 记录费用：`{run.spent_cny} CNY`",
            f"- 进度：`{run.next_chunk_index}/{run.total_chunks}` 分块",
            "",
        ]
        if run.error:
            sections.extend([f"> {_inline(run.error)}", ""])
        sections.extend(self._finding_section("高置信度问题", accepted))
        sections.extend(self._finding_section("仅供参考", reference))
        sections.extend(
            [
                "## 可追踪性",
                "",
                (
                    "每条 Finding 都包含 Trace ID。使用 `review-agent trace <TRACE_ID>` "
                    "查看模型请求、确定性工具观察和已保存响应。"
                ),
                "",
            ]
        )
        return "\n".join(sections)

    def _finding_section(self, title: str, findings: Iterable[Finding]) -> list[str]:
        items = list(findings)
        output = [f"## {title}", ""]
        if not items:
            return output + ["无问题。", ""]
        for finding in items:
            side_label = (
                "LEFT/删除侧" if finding.side == DiffSide.LEFT else "RIGHT/新增侧"
            )
            output.extend(
                [
                    f"### [{finding.severity.value.upper()}] {_inline(finding.title)}",
                    "",
                    f"- 位置：`{_inline(finding.file_path)}:{finding.line}`（{side_label}）",
                    f"- 类别：`{_inline(finding.category)}`",
                    f"- 置信度：`{finding.effective_confidence.value}`",
                    f"- Trace：`{finding.trace_id}`",
                    "",
                    _inline(finding.explanation),
                    "",
                ]
            )
            if finding.suggestion:
                output.extend([f"修复建议：{_inline(finding.suggestion)}", ""])
            if finding.evidence:
                output.extend(["证据：", ""])
                output.extend(f"- {_inline(item)}" for item in finding.evidence)
                output.append("")
        return output
