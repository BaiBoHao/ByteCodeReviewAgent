from __future__ import annotations

import hashlib
import os
from pathlib import Path


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def estimate_tokens(text: str) -> int:
    """Conservative tokenizer-independent estimate used only for budget reservation."""
    return max(1, (len(text) + 2) // 3)
