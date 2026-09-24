from __future__ import annotations

import re


class SecretRedactor:
    """Best-effort local redaction before any content is sent to an LLM."""

    _standalone_patterns = (
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
        re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.IGNORECASE),
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    )
    _assignment = re.compile(
        r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|passwd)"
        r"(\s*[:=]\s*)([\"']?)([^\s\"',;#]{6,})([\"']?)"
    )
    _private_key = re.compile(
        r"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----.*?"
        r"-----END(?: [A-Z0-9]+)? PRIVATE KEY-----",
        re.DOTALL,
    )

    def redact(self, text: str) -> tuple[str, int]:
        redacted, count = self._private_key.subn("[REDACTED_PRIVATE_KEY]", text)
        for pattern in self._standalone_patterns:
            redacted, matches = pattern.subn("[REDACTED_SECRET]", redacted)
            count += matches

        def replace_assignment(match: re.Match[str]) -> str:
            return f"{match.group(1)}{match.group(2)}[REDACTED_SECRET]"

        redacted, matches = self._assignment.subn(replace_assignment, redacted)
        return redacted, count + matches
