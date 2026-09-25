from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

from typer.testing import CliRunner

from bytecode_review_agent.cli import app


FINDINGS_BY_FILE: dict[str, list[dict[str, object]]] = {
    "src/review_project_test/discount_rules.py": [
        {
            "file_path": "src/review_project_test/discount_rules.py",
            "line": 8,
            "severity": "critical",
            "category": "security",
            "title": "Untrusted expression reaches eval",
            "explanation": (
                "The expression is executed as Python code, allowing a caller to access builtins "
                "and execute arbitrary operations."
            ),
            "suggestion": "Replace eval with an allowlisted expression parser.",
            "confidence": "high",
            "evidence": ["The added line passes the caller-controlled expression to eval."],
        },
        {
            "file_path": "src/review_project_test/discount_rules.py",
            "line": 13,
            "severity": "high",
            "category": "security",
            "title": "Credential is hard-coded in source",
            "explanation": (
                "A password literal is stored in the source tree and can be recovered from "
                "repository history or packaged artifacts."
            ),
            "suggestion": "Load the value from a secret store or runtime environment.",
            "confidence": "high",
            "evidence": ["The added line assigns a password literal in application code."],
        },
    ],
    "src/review_project_test/order_service.py": [
        {
            "file_path": "src/review_project_test/order_service.py",
            "line": 20,
            "side": "LEFT",
            "severity": "high",
            "category": "correctness",
            "title": "Empty orders cause division by zero",
            "explanation": "Removing the empty-order guard makes the divisor zero for Order(()).",
            "suggestion": "Restore an explicit empty-order result before division.",
            "confidence": "high",
            "evidence": ["The deleted guard was the only zero-length protection."],
        }
    ],
    "src/review_project_test/profile_loader.py": [
        {
            "file_path": "src/review_project_test/profile_loader.py",
            "line": 9,
            "severity": "medium",
            "category": "resource-management",
            "title": "Profile file handle is never closed",
            "explanation": (
                "The open file is returned from neither a context manager nor an explicit close, "
                "so repeated calls can exhaust file descriptors."
            ),
            "suggestion": "Open the profile with a with statement.",
            "confidence": "high",
            "evidence": ["path.open() is assigned to handle and json.load returns immediately."],
        },
        {
            "file_path": "src/review_project_test/profile_loader.py",
            "line": 14,
            "severity": "medium",
            "category": "correctness",
            "title": "Missing display name raises KeyError",
            "explanation": "Profiles without display_name crash instead of using a fallback.",
            "suggestion": "Use profile.get('display_name', 'anonymous') before normalization.",
            "confidence": "high",
            "evidence": ["Direct dictionary indexing is used for an optional profile field."],
        },
    ],
}


def findings_for_prompt(prompt: str) -> list[dict[str, object]]:
    for file_path, findings in FINDINGS_BY_FILE.items():
        if f"Review file {file_path}." in prompt:
            return findings
    return []


class DemoModelHandler(BaseHTTPRequestHandler):
    request_count = 0

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(length))
        user_prompt = request["messages"][1]["content"]
        findings = findings_for_prompt(user_prompt)
        self.__class__.request_count += 1
        response = json.dumps(
            {
                "id": f"demo-request-{self.request_count}",
                "choices": [
                    {"message": {"content": json.dumps({"findings": findings})}}
                ],
                "usage": {"prompt_tokens": 600, "completion_tokens": 200},
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("x-request-id", f"demo-request-{self.request_count}")
        self.end_headers()
        self.wfile.write(response)


@contextmanager
def demo_model_server() -> Iterator[str]:
    DemoModelHandler.request_count = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), DemoModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic review report through the real CLI pipeline."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("examples/demo-review-report.md"),
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(".review-agent/demo"),
    )
    arguments = parser.parse_args()
    diff = sys.stdin.read()
    if not diff.strip():
        parser.error("a unified diff must be piped to stdin")

    environment = {
        "REVIEW_AGENT_LLM_API_KEY": "local-demo-key",
        "REVIEW_AGENT_LLM_MODEL": "deterministic-demo-model",
        "REVIEW_AGENT_INPUT_PRICE_CNY_PER_MILLION": "1",
        "REVIEW_AGENT_OUTPUT_PRICE_CNY_PER_MILLION": "2",
    }
    with demo_model_server() as base_url, patch.dict(os.environ, environment, clear=False):
        result = CliRunner().invoke(
            app,
            [
                "review",
                "-",
                "--base-url",
                base_url,
                "--budget",
                "1",
                "--data-dir",
                str(arguments.data_dir),
                "--output",
                str(arguments.output),
            ],
            input=diff,
        )
    sys.stdout.write(result.output)
    if result.exception:
        raise result.exception
    print(f"Demo model requests: {DemoModelHandler.request_count}")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
