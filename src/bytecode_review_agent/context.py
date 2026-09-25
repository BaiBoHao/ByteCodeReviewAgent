from __future__ import annotations

import ast
from dataclasses import dataclass

from pydantic import BaseModel, Field

from bytecode_review_agent.models import DiffChunk, FileContext


class SelectedContext(BaseModel):
    file_path: str
    strategy: str
    symbols: list[str] = Field(default_factory=list)
    base_excerpt: str | None = None
    head_excerpt: str | None = None
    base_ranges: list[tuple[int, int]] = Field(default_factory=list)
    head_ranges: list[tuple[int, int]] = Field(default_factory=list)
    base_content_sha256: str | None = None
    head_content_sha256: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.base_excerpt or self.head_excerpt)


@dataclass(frozen=True, slots=True)
class _Symbol:
    name: str
    start: int
    end: int


def _python_symbols(content: str) -> list[_Symbol]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    symbols: list[_Symbol] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            end = getattr(node, "end_lineno", None)
            if end is not None:
                symbols.append(_Symbol(name=node.name, start=node.lineno, end=end))
    return sorted(symbols, key=lambda item: (item.end - item.start, item.start))


def _symbol_ranges(
    symbols: list[_Symbol],
    changed_lines: set[int],
    preferred_names: set[str] | None = None,
) -> tuple[list[tuple[int, int]], list[str]]:
    selected: list[_Symbol] = []
    for line in sorted(changed_lines):
        match = next(
            (symbol for symbol in symbols if symbol.start <= line <= symbol.end),
            None,
        )
        if match and match not in selected:
            selected.append(match)
    if not selected and preferred_names:
        selected = [symbol for symbol in symbols if symbol.name in preferred_names]
    return (
        _merge_ranges([(item.start, item.end) for item in selected]),
        [item.name for item in selected],
    )


def _fallback_ranges(content: str, changed_lines: set[int]) -> list[tuple[int, int]]:
    line_count = len(content.splitlines())
    if not line_count:
        return []
    if not changed_lines:
        return [(1, min(line_count, 80))]
    return _merge_ranges(
        [
            (max(1, line - 20), min(line_count, line + 20))
            for line in sorted(changed_lines)
        ]
    )


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not ranges:
        return []
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if not merged or start > merged[-1][1] + 1:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _render_excerpt(
    content: str | None,
    ranges: list[tuple[int, int]],
    max_chars: int,
) -> str | None:
    if content is None or not ranges:
        return None
    lines = content.splitlines()
    rendered: list[str] = []
    used = 0
    for range_index, (start, end) in enumerate(ranges):
        if range_index:
            rendered.append("     ...")
            used += 8
        for line_number in range(start, min(end, len(lines)) + 1):
            value = f"{line_number:>6}: {lines[line_number - 1]}"
            if used + len(value) + 1 > max_chars:
                rendered.append("     ... [上下文已按预算截断]")
                return "\n".join(rendered)
            rendered.append(value)
            used += len(value) + 1
    return "\n".join(rendered) if rendered else None


def select_context(
    chunk: DiffChunk,
    file_context: FileContext | None,
    *,
    max_chars: int,
) -> SelectedContext | None:
    if file_context is None:
        return None

    base_content = file_context.base_content
    head_content = file_context.head_content
    is_python = file_context.file_path.lower().endswith(".py")
    symbols: set[str] = set()

    if is_python and base_content:
        base_ranges, base_names = _symbol_ranges(
            _python_symbols(base_content), chunk.removed_lines
        )
        symbols.update(base_names)
    else:
        base_ranges = _fallback_ranges(base_content or "", chunk.removed_lines)

    if is_python and head_content:
        head_ranges, head_names = _symbol_ranges(
            _python_symbols(head_content),
            chunk.added_lines,
            preferred_names=symbols,
        )
        symbols.update(head_names)
    else:
        head_lines = chunk.added_lines or chunk.removed_lines
        head_ranges = _fallback_ranges(head_content or "", head_lines)

    if not base_ranges and base_content:
        base_ranges = _fallback_ranges(base_content, chunk.removed_lines)
    if not head_ranges and head_content:
        head_ranges = _fallback_ranges(
            head_content, chunk.added_lines or chunk.removed_lines
        )

    selected = SelectedContext(
        file_path=file_context.file_path,
        strategy="python-symbol" if is_python and symbols else "line-window",
        symbols=sorted(symbols),
        base_excerpt=_render_excerpt(base_content, base_ranges, max_chars),
        head_excerpt=_render_excerpt(head_content, head_ranges, max_chars),
        base_ranges=base_ranges,
        head_ranges=head_ranges,
        base_content_sha256=file_context.base_content_sha256,
        head_content_sha256=file_context.head_content_sha256,
    )
    return selected if selected.available else None
