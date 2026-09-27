from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

from typer.testing import CliRunner

from bytecode_review_agent.cli import app
from bytecode_review_agent.storage import SQLiteStorage


DIFF = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -0,0 +1,2 @@
+password = "cli-integration-secret"
+result = eval(user_input)
"""


class MockLLMHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))
        self.__class__.requests.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "payload": payload,
            }
        )
        finding = {
            "findings": [
                {
                    "file_path": "app.py",
                    "line": 2,
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
        response = json.dumps(
            {
                "id": "mock-request-1",
                "choices": [{"message": {"content": json.dumps(finding)}}],
                "usage": {"prompt_tokens": 400, "completion_tokens": 100},
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("x-request-id", "mock-request-1")
        self.end_headers()
        self.wfile.write(response)


@contextmanager
def mock_llm_server() -> Iterator[str]:
    MockLLMHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockLLMHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class CLIIntegrationTests(unittest.TestCase):
    def test_review_command_runs_full_pipeline_against_compatible_endpoint(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as directory, mock_llm_server() as base_url:
            root = Path(directory)
            diff_path = root / "change.diff"
            report_path = root / "report.md"
            data_dir = root / "agent-data"
            diff_path.write_text(DIFF, encoding="utf-8")
            environment = {
                "REVIEW_AGENT_LLM_BASE_URL": base_url,
                "REVIEW_AGENT_LLM_API_KEY": "integration-test-key",
                "REVIEW_AGENT_LLM_MODEL": "mock-review-model",
                "REVIEW_AGENT_LLM_THINKING": "disabled",
                "REVIEW_AGENT_INPUT_PRICE_CNY_PER_MILLION": "1",
                "REVIEW_AGENT_OUTPUT_PRICE_CNY_PER_MILLION": "2",
            }

            with patch.dict(os.environ, environment, clear=False):
                result = runner.invoke(
                    app,
                    [
                        "review",
                        str(diff_path),
                        "--budget",
                        "1",
                        "--data-dir",
                        str(data_dir),
                        "--output",
                        str(report_path),
                    ],
                )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("Status: completed", result.output)
            self.assertTrue(report_path.is_file())
            self.assertIn("Dynamic execution", report_path.read_text(encoding="utf-8"))

            self.assertEqual(len(MockLLMHandler.requests), 1)
            request = MockLLMHandler.requests[0]
            self.assertEqual(request["path"], "/v1/chat/completions")
            self.assertEqual(request["authorization"], "Bearer integration-test-key")
            payload = request["payload"]
            self.assertIsInstance(payload, dict)
            system_prompt = payload["messages"][0]["content"]
            user_prompt = payload["messages"][1]["content"]
            self.assertIn("Simplified Chinese", system_prompt)
            self.assertNotIn("cli-integration-secret", user_prompt)
            self.assertIn("[REDACTED_SECRET]", user_prompt)
            self.assertEqual(payload["response_format"], {"type": "json_object"})
            self.assertEqual(payload["thinking"], {"type": "disabled"})

            storage = SQLiteStorage(data_dir / "agent.sqlite3")
            run = storage.list_runs(limit=1)[0]
            finding = storage.list_findings(run.id)[0]
            self.assertEqual(run.status.value, "completed")
            self.assertGreater(run.spent_cny, 0)
            trace = storage.get_trace(finding.trace_id)
            self.assertEqual(trace["request_id"], "mock-request-1")

            trace_result = runner.invoke(
                app,
                [
                    "trace",
                    finding.trace_id,
                    "--data-dir",
                    str(data_dir),
                    "--include-content",
                ],
            )
            self.assertEqual(trace_result.exit_code, 0, trace_result.output)
            self.assertNotIn("cli-integration-secret", trace_result.output)
            self.assertIn("[REDACTED_SECRET]", trace_result.output)


if __name__ == "__main__":
    unittest.main()
