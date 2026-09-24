from __future__ import annotations

import os
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path

from bytecode_review_agent.errors import ConfigurationError


def _decimal_env(name: str, default: str = "0") -> Decimal:
    try:
        return Decimal(os.getenv(name, default))
    except InvalidOperation as exc:
        raise ConfigurationError(f"{name} must be a decimal number") from exc


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

    @classmethod
    def from_env(cls, data_dir: Path | None = None) -> Settings:
        hosts = tuple(
            host.strip().lower()
            for host in os.getenv(
                "REVIEW_AGENT_ALLOWED_HOSTS", "github.com,gitlab.com"
            ).split(",")
            if host.strip()
        )
        return cls(
            data_dir=(data_dir or Path(os.getenv("REVIEW_AGENT_DATA_DIR", ".review-agent"))),
            llm_base_url=os.getenv(
                "REVIEW_AGENT_LLM_BASE_URL", "https://api.openai.com/v1"
            ),
            llm_api_key=os.getenv("REVIEW_AGENT_LLM_API_KEY"),
            llm_model=os.getenv("REVIEW_AGENT_LLM_MODEL"),
            input_price_cny_per_million=_decimal_env(
                "REVIEW_AGENT_INPUT_PRICE_CNY_PER_MILLION"
            ),
            output_price_cny_per_million=_decimal_env(
                "REVIEW_AGENT_OUTPUT_PRICE_CNY_PER_MILLION"
            ),
            allowed_hosts=hosts,
            github_token=os.getenv("GITHUB_TOKEN"),
            gitlab_token=os.getenv("GITLAB_TOKEN"),
            max_diff_bytes=int(os.getenv("REVIEW_AGENT_MAX_DIFF_BYTES", "512000")),
            max_chunk_chars=int(os.getenv("REVIEW_AGENT_MAX_CHUNK_CHARS", "12000")),
            max_output_tokens=int(os.getenv("REVIEW_AGENT_MAX_OUTPUT_TOKENS", "1200")),
            request_timeout_seconds=float(
                os.getenv("REVIEW_AGENT_REQUEST_TIMEOUT_SECONDS", "60")
            ),
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
        if not self.llm_model:
            raise ConfigurationError("REVIEW_AGENT_LLM_MODEL is required for review")
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
