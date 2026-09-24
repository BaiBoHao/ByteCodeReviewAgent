from __future__ import annotations

import re
from importlib.metadata import entry_points
from typing import Protocol

from bytecode_review_agent.models import DiffChunk, ToolObservation


class ReviewTool(Protocol):
    name: str

    def run(self, chunk: DiffChunk) -> ToolObservation: ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ReviewTool] = {}

    def register(self, tool: ReviewTool) -> ReviewTool:
        if not tool.name:
            raise ValueError("tool name cannot be empty")
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool
        return tool

    def load_entry_points(self) -> None:
        for item in entry_points(group="bytecode_review_agent.tools"):
            loaded = item.load()
            tool = loaded() if isinstance(loaded, type) else loaded
            self.register(tool)

    def run(self, names: tuple[str, ...], chunk: DiffChunk) -> list[ToolObservation]:
        missing = [name for name in names if name not in self._tools]
        if missing:
            raise ValueError(f"unknown review tools: {', '.join(missing)}")
        return [self._tools[name].run(chunk) for name in names]

    def names(self) -> list[str]:
        return sorted(self._tools)


def _iter_added_lines(chunk: DiffChunk) -> list[tuple[int, str]]:
    hunk = re.compile(r"^@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@")
    current: int | None = None
    result: list[tuple[int, str]] = []
    for line in chunk.content.splitlines():
        match = hunk.match(line)
        if match:
            current = int(match.group(1))
            continue
        if current is None:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            result.append((current, line[1:]))
            current += 1
        elif line.startswith("-") and not line.startswith("---"):
            continue
        elif not line.startswith("\\"):
            current += 1
    return result


class DiffStatsTool:
    name = "diff_stats"

    def run(self, chunk: DiffChunk) -> ToolObservation:
        added = _iter_added_lines(chunk)
        removed = sum(
            1
            for line in chunk.content.splitlines()
            if line.startswith("-") and not line.startswith("---")
        )
        return ToolObservation(
            tool=self.name,
            summary=f"{len(added)} added lines and {removed} removed lines",
            data={"added_lines": len(added), "removed_lines": removed},
        )


class RiskPatternsTool:
    name = "risk_patterns"
    _patterns = {
        "dynamic_execution": re.compile(r"\b(eval|exec)\s*\("),
        "shell_execution": re.compile(
            r"\b(subprocess\.|os\.system\s*\(|Runtime\.getRuntime\(\)\.exec)"
        ),
        "unsafe_deserialization": re.compile(r"\b(pickle\.loads?|yaml\.load)\s*\("),
        "debug_marker": re.compile(r"\b(TODO|FIXME|HACK)\b"),
    }

    def run(self, chunk: DiffChunk) -> ToolObservation:
        matches: list[dict[str, object]] = []
        for line_number, line in _iter_added_lines(chunk):
            for category, pattern in self._patterns.items():
                if pattern.search(line):
                    matches.append(
                        {
                            "category": category,
                            "line": line_number,
                            "excerpt": line[:200],
                        }
                    )
        return ToolObservation(
            tool=self.name,
            summary=f"found {len(matches)} potentially risky added-line patterns",
            data={"matches": matches},
        )


def default_registry(load_plugins: bool = True) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(DiffStatsTool())
    registry.register(RiskPatternsTool())
    if load_plugins:
        registry.load_entry_points()
    return registry
