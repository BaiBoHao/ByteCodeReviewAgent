from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from bytecode_review_agent.config import Settings
from bytecode_review_agent.errors import ModelResponseError, RunExecutionError
from bytecode_review_agent.llm import ReviewerClient
from bytecode_review_agent.models import LLMCallResult, RunStatus
from bytecode_review_agent.providers import SourceLoader
from bytecode_review_agent.service import ReviewService
from bytecode_review_agent.storage import SQLiteStorage
from bytecode_review_agent.tools import default_registry


DIFF = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -0,0 +1,2 @@
+password = "supersecret123"
+result = eval(user_input)
"""


class FakeReviewer(ReviewerClient):
    model = "fake-model"

    def __init__(self, failures: int = 0, malformed: int = 0, line: int = 2) -> None:
        self.failures = failures
        self.malformed = malformed
        self.line = line
        self.calls = 0
        self.prompts: list[str] = []

    def review(
        self, system_prompt: str, user_prompt: str, max_output_tokens: int
    ) -> LLMCallResult:
        self.calls += 1
        self.prompts.append(user_prompt)
        if self.calls <= self.failures:
            raise ModelResponseError("simulated transient failure")
        if self.calls <= self.failures + self.malformed:
            return LLMCallResult(
                content="not-json",
                input_tokens=400,
                output_tokens=10,
                request_id=f"fake-{self.calls}",
            )
        content = json.dumps(
            {
                "findings": [
                    {
                        "file_path": "app.py",
                        "line": self.line,
                        "severity": "high",
                        "category": "security",
                        "title": "Dynamic execution of untrusted input",
                        "explanation": "eval executes attacker-controlled Python code.",
                        "suggestion": "Parse the supported input format without eval.",
                        "confidence": "high",
                        "evidence": ["The added line calls eval(user_input)."],
                    }
                ]
            }
        )
        return LLMCallResult(
            content=content,
            input_tokens=400,
            output_tokens=100,
            request_id=f"fake-{self.calls}",
        )


def make_settings(path: Path, *, input_price: str = "1", output_price: str = "2") -> Settings:
    return Settings(
        data_dir=path / ".review-agent",
        llm_base_url="https://model.invalid/v1",
        llm_api_key="test",
        llm_model="fake-model",
        input_price_cny_per_million=Decimal(input_price),
        output_price_cny_per_million=Decimal(output_price),
        allowed_hosts=("github.com", "gitlab.com"),
        github_token=None,
        gitlab_token=None,
    )


def make_service(path: Path, reviewer: FakeReviewer, settings: Settings) -> ReviewService:
    return ReviewService(
        settings=settings,
        reviewer=reviewer,
        storage=SQLiteStorage(settings.database_path),
        sources=SourceLoader(settings),
        tools=default_registry(load_plugins=False),
    )


class ReviewServiceTests(unittest.TestCase):
    def test_review_redacts_model_input_and_writes_traceable_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            diff_path = root / "change.diff"
            diff_path.write_text(DIFF, encoding="utf-8")
            settings = make_settings(root)
            reviewer = FakeReviewer()
            service = make_service(root, reviewer, settings)
            report_path = root / "report.md"

            result = service.start(
                str(diff_path), budget_cny=Decimal("1"), output_path=report_path
            )

            self.assertEqual(result.run.status, RunStatus.COMPLETED)
            self.assertEqual(len(result.findings), 1)
            self.assertEqual(result.findings[0].disposition.value, "accept")
            self.assertNotIn("supersecret123", reviewer.prompts[0])
            self.assertIn("[REDACTED_SECRET]", reviewer.prompts[0])
            self.assertIn(result.findings[0].trace_id, report_path.read_text(encoding="utf-8"))

            trace = service.storage.get_trace(result.findings[0].trace_id)
            self.assertEqual(trace["raw_diff_sha256"], result.run.diff_sha256)
            self.assertTrue(Path(str(trace["raw_diff_path"])).is_file())
            self.assertIn("risk_patterns", {tool["tool"] for tool in trace["tools"]})

    def test_failed_run_can_resume_from_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            diff_path = root / "change.diff"
            diff_path.write_text(DIFF, encoding="utf-8")
            settings = make_settings(root)
            reviewer = FakeReviewer(failures=1)
            service = make_service(root, reviewer, settings)

            with self.assertRaises(RunExecutionError) as captured:
                service.start(str(diff_path), budget_cny=Decimal("1"))
            run_id = captured.exception.run_id
            self.assertEqual(service.storage.get_run(run_id).status, RunStatus.FAILED)
            self.assertEqual(service.storage.get_run(run_id).next_chunk_index, 0)

            result = service.resume(run_id)
            self.assertEqual(result.run.status, RunStatus.COMPLETED)
            self.assertEqual(result.run.next_chunk_index, 1)
            stages = [item["stage"] for item in service.storage.list_checkpoints(run_id)]
            self.assertIn("resumed", stages)
            self.assertIn("chunk_completed", stages)

    def test_budget_exhaustion_stops_before_model_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            diff_path = root / "change.diff"
            diff_path.write_text(DIFF, encoding="utf-8")
            settings = make_settings(root, input_price="1000000", output_price="1000000")
            reviewer = FakeReviewer()
            service = make_service(root, reviewer, settings)

            result = service.start(str(diff_path), budget_cny=Decimal("0.01"))

            self.assertEqual(result.run.status, RunStatus.BUDGET_EXHAUSTED)
            self.assertEqual(result.run.next_chunk_index, 0)
            self.assertEqual(reviewer.calls, 0)

    def test_invalid_model_location_is_reference_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            diff_path = root / "change.diff"
            diff_path.write_text(DIFF, encoding="utf-8")
            settings = make_settings(root)
            service = make_service(root, FakeReviewer(line=99), settings)

            result = service.start(str(diff_path), budget_cny=Decimal("1"))

            self.assertEqual(result.findings[0].effective_confidence.value, "low")
            self.assertEqual(result.findings[0].disposition.value, "reference")

    def test_malformed_response_is_traced_and_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            diff_path = root / "change.diff"
            diff_path.write_text(DIFF, encoding="utf-8")
            settings = make_settings(root)
            reviewer = FakeReviewer(malformed=1)
            service = make_service(root, reviewer, settings)

            with self.assertRaises(RunExecutionError) as captured:
                service.start(str(diff_path), budget_cny=Decimal("1"))
            run_id = captured.exception.run_id
            failed_traces = service.storage.list_traces(run_id)
            self.assertEqual(len(failed_traces), 1)
            self.assertIn("invalid review JSON", str(failed_traces[0]["error"]))
            self.assertGreater(service.storage.get_run(run_id).spent_cny, Decimal("0"))

            result = service.resume(run_id)
            self.assertEqual(result.run.status, RunStatus.COMPLETED)
            self.assertEqual(len(service.storage.list_traces(run_id)), 2)


if __name__ == "__main__":
    unittest.main()
