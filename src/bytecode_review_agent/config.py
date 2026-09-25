from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path

from bytecode_review_agent.errors import ConfigurationError


_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PLACEHOLDERS = {"...", "replace-me", "your-api-key", "your-model"}


def _decimal_value(name: str, value: str | None, default: str = "0") -> Decimal:
    try:
        return Decimal(value if value is not None else default)
    except InvalidOperation as exc:
        raise ConfigurationError(f"{name} must be a decimal number") from exc


def _read_env_file(path: Path, *, required: bool) -> dict[str, str]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        if required:
            raise ConfigurationError(f"environment file does not exist: {resolved}")
        return {}

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        resolved.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ConfigurationError(
                f"invalid environment entry at {resolved}:{line_number}"
            )
        key, value = (part.strip() for part in line.split("=", 1))
        if not _ENV_KEY.fullmatch(key):
            raise ConfigurationError(
                f"invalid environment key at {resolved}:{line_number}: {key!r}"
            )
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    llm_base_url: str
    llm_api_key: str | None
    llm_model: str | None
    input_price_cny_per_million: Decimal
    output_price_cny_per_million: Decimal
    allowed_hosts: tuple[str, ...]
    github_token: str | None
    gitlab_token: str | None
    max_diff_bytes: int = 512_000
    max_chunk_chars: int = 12_000
    max_output_tokens: int = 1_200
    request_timeout_seconds: float = 60.0
    enabled_tools: tuple[str, ...] = ("diff_stats", "risk_patterns")
    env_file_path: Path | None = None

    @classmethod
    def from_env(
        cls,
        data_dir: Path | None = None,
        env_file: Path | None = None,
    ) -> Settings:
        configured_file = os.getenv("REVIEW_AGENT_ENV_FILE")
        if env_file is not None:
            env_file_path = env_file.expanduser().resolve()
            file_values = _read_env_file(env_file_path, required=True)
        elif configured_file:
            env_file_path = Path(configured_file).expanduser().resolve()
            file_values = _read_env_file(env_file_path, required=True)
        else:
            candidate = Path(".env").resolve()
            env_file_path = candidate if candidate.is_file() else None
            file_values = _read_env_file(candidate, required=False)

        def value(name: str, default: str | None = None) -> str | None:
            return os.getenv(name, file_values.get(name, default))

        hosts = tuple(
            host.strip().lower()
            for host in (
                value("REVIEW_AGENT_ALLOWED_HOSTS", "github.com,gitlab.com") or ""
            ).split(",")
            if host.strip()
        )
        return cls(
            data_dir=(
                data_dir
                or Path(value("REVIEW_AGENT_DATA_DIR", ".review-agent") or ".review-agent")
            ),
            llm_base_url=(
                value("REVIEW_AGENT_LLM_BASE_URL", "https://api.openai.com/v1")
                or "https://api.openai.com/v1"
            ),
            llm_api_key=value("REVIEW_AGENT_LLM_API_KEY"),
            llm_model=value("REVIEW_AGENT_LLM_MODEL"),
            input_price_cny_per_million=_decimal_value(
                "REVIEW_AGENT_INPUT_PRICE_CNY_PER_MILLION",
                value("REVIEW_AGENT_INPUT_PRICE_CNY_PER_MILLION"),
            ),
            output_price_cny_per_million=_decimal_value(
                "REVIEW_AGENT_OUTPUT_PRICE_CNY_PER_MILLION",
                value("REVIEW_AGENT_OUTPUT_PRICE_CNY_PER_MILLION"),
            ),
            allowed_hosts=hosts,
            github_token=value("GITHUB_TOKEN"),
            gitlab_token=value("GITLAB_TOKEN"),
            max_diff_bytes=int(value("REVIEW_AGENT_MAX_DIFF_BYTES", "512000") or "512000"),
            max_chunk_chars=int(value("REVIEW_AGENT_MAX_CHUNK_CHARS", "12000") or "12000"),
            max_output_tokens=int(value("REVIEW_AGENT_MAX_OUTPUT_TOKENS", "1200") or "1200"),
            request_timeout_seconds=float(
                value("REVIEW_AGENT_REQUEST_TIMEOUT_SECONDS", "60") or "60"
            ),
            env_file_path=env_file_path,
        )

    @property
    def database_path(self) -> Path:
        return self.data_dir / "agent.sqlite3"

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"

    def with_overrides(self, **changes: object) -> Settings:
        return replace(self, **changes)

    def validate_for_review(self) -> None:
        if not self.llm_api_key:
            raise ConfigurationError("REVIEW_AGENT_LLM_API_KEY is required for review")
        if self.llm_api_key.strip().lower() in _PLACEHOLDERS:
            raise ConfigurationError(
                "REVIEW_AGENT_LLM_API_KEY still contains an example placeholder"
            )
        if not self.llm_model:
            raise ConfigurationError("REVIEW_AGENT_LLM_MODEL is required for review")
        if self.llm_model.strip().lower() in _PLACEHOLDERS:
            raise ConfigurationError(
                "REVIEW_AGENT_LLM_MODEL still contains an example placeholder"
            )
        if self.input_price_cny_per_million <= 0:
            raise ConfigurationError(
                "REVIEW_AGENT_INPUT_PRICE_CNY_PER_MILLION must be greater than zero"
            )
        if self.output_price_cny_per_million <= 0:
            raise ConfigurationError(
                "REVIEW_AGENT_OUTPUT_PRICE_CNY_PER_MILLION must be greater than zero"
            )
        if not self.allowed_hosts:
            raise ConfigurationError("at least one allowed source host is required")
