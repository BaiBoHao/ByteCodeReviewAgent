from __future__ import annotations

import json
import re
from typing import Protocol

import httpx
from pydantic import ValidationError

from bytecode_review_agent.errors import ModelResponseError
from bytecode_review_agent.models import LLMCallResult, ModelReview
from bytecode_review_agent.utils import estimate_tokens


class ReviewerClient(Protocol):
    model: str

    def review(
        self, system_prompt: str, user_prompt: str, max_output_tokens: int
    ) -> LLMCallResult: ...


class OpenAICompatibleReviewer:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        thinking: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.thinking = thinking

    def review(
        self, system_prompt: str, user_prompt: str, max_output_tokens: int
    ) -> LLMCallResult:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        if self.thinking is not None:
            payload["thinking"] = {"type": self.thinking}
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise ModelResponseError(f"LLM request failed: {exc}") from exc

        usage = body.get("usage") or {}
        input_tokens = int(
            usage.get("prompt_tokens") or estimate_tokens(system_prompt + user_prompt)
        )
        output_tokens = int(usage.get("completion_tokens") or estimate_tokens(content))
        return LLMCallResult(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            request_id=response.headers.get("x-request-id") or body.get("id"),
        )


def parse_model_review(content: str) -> ModelReview:
    cleaned = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)
    try:
        payload = json.loads(cleaned)
        return ModelReview.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise ModelResponseError(f"model returned invalid review JSON: {exc}") from exc
