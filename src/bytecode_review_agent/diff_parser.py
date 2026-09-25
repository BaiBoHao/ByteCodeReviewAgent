from __future__ import annotations

import re
from dataclasses import dataclass

from bytecode_review_agent.models import DiffChunk


_HUNK_HEADER = re.compile(r"^@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@")


@dataclass(frozen=True, slots=True)
class _FilePatch:
    path: str
    content: str


def _normalise_path(value: str) -> str:
    value = value.strip().split("\t", 1)[0]
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    if value.startswith("a/") or value.startswith("b/"):
        value = value[2:]
    return value


def _path_from_patch(content: str) -> str:
    old_path = "unknown.diff"
    for line in content.splitlines():
        if line.startswith("--- ") and line[4:].strip() != "/dev/null":
            old_path = _normalise_path(line[4:])
        if line.startswith("+++ ") and line[4:].strip() != "/dev/null":
            return _normalise_path(line[4:])
    return old_path


def split_file_patches(diff: str) -> list[_FilePatch]:
    lines = diff.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.startswith("diff --git ")]
    if not starts:
        return [_FilePatch(path=_path_from_patch(diff), content=diff)] if diff.strip() else []

    patches: list[_FilePatch] = []
    starts.append(len(lines))
    for current, following in zip(starts, starts[1:]):
        content = "".join(lines[current:following])
        patches.append(_FilePatch(path=_path_from_patch(content), content=content))
    return patches


def _changed_lines(content: str) -> tuple[set[int], set[int]]:
    added: set[int] = set()
    removed: set[int] = set()
    old_line: int | None = None
    new_line: int | None = None
    for line in content.splitlines():
        match = re.match(
            r"^@@\s+-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@", line
        )
        if match:
            old_line = int(match.group(1))
            new_line = int(match.group(2))
            continue
        if old_line is None or new_line is None:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added.add(new_line)
            new_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed.add(old_line)
            old_line += 1
        elif not line.startswith("\\"):
            old_line += 1
            new_line += 1
    return added, removed


def _split_large_patch(patch: _FilePatch, max_chars: int) -> list[str]:
    if len(patch.content) <= max_chars:
        return [patch.content]

    lines = patch.content.splitlines(keepends=True)
    header: list[str] = []
    hunks: list[str] = []
    current: list[str] = []
    seen_hunk = False
    for line in lines:
        if line.startswith("@@ "):
            if current:
                if seen_hunk:
                    hunks.append("".join(current))
                else:
                    header = current
            current = [line]
            seen_hunk = True
        else:
            current.append(line)
    if current:
        if seen_hunk:
            hunks.append("".join(current))
        else:
            header = current

    header_text = "".join(header)
    if not hunks:
        return [
            patch.content[index : index + max_chars]
            for index in range(0, len(patch.content), max_chars)
        ]

    chunks: list[str] = []
    active = header_text
    for hunk in hunks:
        if len(active) + len(hunk) > max_chars and active != header_text:
            chunks.append(active)
            active = header_text
        if len(header_text) + len(hunk) > max_chars:
            if active != header_text:
                chunks.append(active)
                active = header_text
            chunks.extend(_split_oversized_hunk(header_text, hunk, max_chars))
        else:
            active += hunk
    if active != header_text:
        chunks.append(active)
    return chunks


def _split_oversized_hunk(header: str, hunk: str, max_chars: int) -> list[str]:
    lines = hunk.splitlines(keepends=True)
    match = re.match(
        r"^@@\s+-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@", lines[0]
    )
    if not match:
        return [header + hunk]

    old_line = int(match.group(1))
    new_line = int(match.group(2))
    segment_old = old_line
    segment_new = new_line
    body: list[str] = []
    body_length = 0
    result: list[str] = []

    def synthetic_hunk_header() -> str:
        return f"@@ -{segment_old} +{segment_new} @@\n"

    def flush() -> None:
        nonlocal body, body_length, segment_old, segment_new
        if body:
            result.append(header + synthetic_hunk_header() + "".join(body))
            body = []
            body_length = 0
            segment_old = old_line
            segment_new = new_line

    for line in lines[1:]:
        projected = len(header) + len(synthetic_hunk_header()) + body_length + len(line)
        if body and projected > max_chars:
            flush()
        if not body:
            segment_old = old_line
            segment_new = new_line
        body.append(line)
        body_length += len(line)
        if line.startswith("+") and not line.startswith("+++"):
            new_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            old_line += 1
        elif not line.startswith("\\"):
            old_line += 1
            new_line += 1
    flush()
    return result


def chunk_diff(diff: str, max_chars: int) -> list[DiffChunk]:
    chunks: list[DiffChunk] = []
    for patch in split_file_patches(diff):
        for content in _split_large_patch(patch, max_chars):
            added_lines, removed_lines = _changed_lines(content)
            chunks.append(
                DiffChunk(
                    index=len(chunks),
                    file_path=patch.path,
                    content=content,
                    added_lines=added_lines,
                    removed_lines=removed_lines,
                )
            )
    return chunks
