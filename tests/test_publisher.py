from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import httpx
from typer.testing import CliRunner

from bytecode_review_agent.cli import app
from bytecode_review_agent.config import Settings
from bytecode_review_agent.errors import ConfigurationError, PublicationError
from bytecode_review_agent.models import (
    Confidence,
    DiffSide,
    Disposition,
    Finding,
    RunRecord,
    RunStatus,
    Severity,
    SourceKind,
    SourceSnapshot,
)
from bytecode_review_agent.publisher import GITHUB_API_VERSION, GitHubCommentPublisher
from bytecode_review_agent.storage import SQLiteStorage


def settings_for(root: Path, token: str | None = "github-test-token") -> Settings:
    return Settings(
        data_dir=root,
        llm_base_url="https://model.invalid/v1",
        llm_api_key="test",
        llm_model="test-model",
        input_price_cny_per_million=Decimal("1"),
        output_price_cny_per_million=Decimal("1"),
        allowed_hosts=("github.com",),
        github_token=token,
        gitlab_token=None,
    )


def run_record(
    *,
    head_sha: str = "head-reviewed",
    output_language: str = "zh-CN",
) -> RunRecord:
    return RunRecord(
        id="run_publish_test",
        status=RunStatus.COMPLETED,
        source_kind=SourceKind.GITHUB,
        source_ref="https://github.com/acme/project/pull/7",
        provider="github",
        diff_sha256="a" * 64,
        raw_diff_path=Path("raw.diff"),
        sanitized_diff_path=Path("sanitized.diff"),
        next_chunk_index=1,
        total_chunks=1,
        budget_cny=Decimal("10"),
        spent_cny=Decimal("1"),
        config={
            "source_metadata": {"head_sha": head_sha},
            "output_language": output_language,
        },
        created_at="2026-09-27T00:00:00+00:00",
        updated_at="2026-09-27T00:00:01+00:00",
    )


def finding(
    number: int,
    *,
    side: DiffSide = DiffSide.RIGHT,
    confidence: Confidence = Confidence.HIGH,
    disposition: Disposition = Disposition.ACCEPT,
) -> Finding:
    line = number + 3
    return Finding(
        id=f"finding_{number}",
        run_id="run_publish_test",
        trace_id=f"trace_{number}",
        file_path=f"src/file_{number}.py",
        line=line,
        side=side,
        old_line=line if side == DiffSide.LEFT else None,
        new_line=line if side == DiffSide.RIGHT else None,
        severity=Severity.HIGH,
        category="security",
        title=f"Finding {number}",
        explanation="The reviewed line is unsafe.",
        suggestion="Use the safe implementation.",
        model_confidence=confidence,
        effective_confidence=confidence,
        disposition=disposition,
        evidence=["The changed line reaches an unsafe call."],
        fingerprint=f"{number:064x}",
    )


class GitHubCommentPublisherTests(unittest.TestCase):
    def test_comment_labels_follow_review_output_language(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = GitHubCommentPublisher(
                settings_for(Path(directory), token=None),
                client=httpx.Client(
                    transport=httpx.MockTransport(
                        lambda _: (_ for _ in ()).throw(AssertionError("unexpected network"))
                    )
                ),
            ).publish(run_record(output_language="en-US"), [finding(1)])

        self.assertIn("**Suggestion**", result.comments[0].body)
        self.assertIn("**Evidence**", result.comments[0].body)
        self.assertNotIn("**建议**", result.comments[0].body)

    def test_cli_publish_is_a_dry_run_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = SQLiteStorage(root / "agent.sqlite3")
            run = run_record()
            storage.create_run(
                run_id=run.id,
                source=SourceSnapshot(
                    kind=SourceKind.GITHUB,
                    reference=run.source_ref,
                    provider="github",
                    diff="diff --git a/a.py b/a.py\n",
                    metadata={"head_sha": "head-reviewed"},
                ),
                diff_sha256=run.diff_sha256,
                raw_diff_path=root / "raw.diff",
                sanitized_diff_path=root / "sanitized.diff",
                total_chunks=1,
                budget_cny=Decimal("10"),
                config=run.config,
            )
            storage.mark_terminal(run.id, RunStatus.COMPLETED)

            result = CliRunner().invoke(
                app,
                ["publish", run.id, "--data-dir", str(root)],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn('"dry_run": true', result.output)
        self.assertIn("Dry run only", result.output)

    def test_dry_run_filters_findings_without_network_or_token(self) -> None:
        def reject_network(_: httpx.Request) -> httpx.Response:
            raise AssertionError("dry-run must not access GitHub")

        with tempfile.TemporaryDirectory() as directory:
            client = httpx.Client(transport=httpx.MockTransport(reject_network))
            publisher = GitHubCommentPublisher(
                settings_for(Path(directory), token=None),
                client=client,
            )
            result = publisher.publish(
                run_record(),
                [
                    finding(1),
                    finding(2, confidence=Confidence.MEDIUM),
                    finding(3, disposition=Disposition.REFERENCE),
                ],
            )

        self.assertTrue(result.dry_run)
        self.assertEqual(result.eligible_count, 1)
        self.assertEqual(result.skipped_count, 2)
        self.assertEqual(result.comments[0].action.value, "preview")
        self.assertIn(
            "<!-- bytecode-review-agent:finding:",
            result.comments[0].body,
        )

    def test_apply_creates_updates_and_keeps_idempotent_comments(self) -> None:
        findings = [finding(1), finding(2, side=DiffSide.LEFT), finding(3)]
        requests: list[tuple[str, str, dict[str, object] | None]] = []

        with tempfile.TemporaryDirectory() as directory:
            configured = settings_for(Path(directory))
            preview_client = httpx.Client(
                transport=httpx.MockTransport(
                    lambda _: (_ for _ in ()).throw(AssertionError("unexpected network"))
                )
            )
            preview = GitHubCommentPublisher(configured, client=preview_client).publish(
                run_record(), findings
            )
            bodies = {item.fingerprint: item.body for item in preview.comments}

            def handler(request: httpx.Request) -> httpx.Response:
                payload = json.loads(request.content) if request.content else None
                requests.append((request.method, request.url.path, payload))
                self.assertEqual(
                    request.headers["X-GitHub-Api-Version"],
                    GITHUB_API_VERSION,
                )
                self.assertEqual(
                    request.headers["Authorization"],
                    "Bearer github-test-token",
                )
                if request.method == "GET" and request.url.path.endswith("/pulls/7"):
                    return httpx.Response(200, json={"head": {"sha": "head-reviewed"}})
                if request.method == "GET" and request.url.path.endswith("/pulls/7/comments"):
                    return httpx.Response(
                        200,
                        json=[
                            {
                                "id": 101,
                                "body": bodies[f"{1:064x}"],
                                "html_url": "https://github.test/comment/101",
                            },
                            {
                                "id": 102,
                                "body": (
                                    "old body\n\n"
                                    f"<!-- bytecode-review-agent:finding:{2:064x} -->"
                                ),
                                "html_url": "https://github.test/comment/102",
                            },
                        ],
                    )
                if request.method == "PATCH" and request.url.path.endswith("/comments/102"):
                    return httpx.Response(
                        200,
                        json={"id": 102, "html_url": "https://github.test/comment/102"},
                    )
                if request.method == "POST" and request.url.path.endswith("/pulls/7/comments"):
                    return httpx.Response(
                        201,
                        json={"id": 103, "html_url": "https://github.test/comment/103"},
                    )
                return httpx.Response(404, json={"message": "unexpected request"})

            client = httpx.Client(transport=httpx.MockTransport(handler))
            result = GitHubCommentPublisher(configured, client=client).publish(
                run_record(), findings, apply=True
            )

        self.assertFalse(result.dry_run)
        self.assertEqual(result.unchanged_count, 1)
        self.assertEqual(result.updated_count, 1)
        self.assertEqual(result.created_count, 1)
        actions = {item.finding_id: item.action.value for item in result.comments}
        self.assertEqual(
            actions,
            {"finding_1": "unchanged", "finding_2": "update", "finding_3": "create"},
        )
        created_payload = next(
            payload
            for method, path, payload in requests
            if method == "POST" and path.endswith("/pulls/7/comments")
        )
        self.assertEqual(created_payload["side"], "RIGHT")  # type: ignore[index]
        updated_payload = next(
            payload for method, _, payload in requests if method == "PATCH"
        )
        self.assertEqual(updated_payload, {"body": bodies[f"{2:064x}"]})

    def test_apply_rejects_changed_pull_request_head(self) -> None:
        writes: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method != "GET":
                writes.append(request.method)
            return httpx.Response(200, json={"head": {"sha": "new-head"}})

        with tempfile.TemporaryDirectory() as directory:
            publisher = GitHubCommentPublisher(
                settings_for(Path(directory)),
                client=httpx.Client(transport=httpx.MockTransport(handler)),
            )
            with self.assertRaises(PublicationError):
                publisher.publish(run_record(), [finding(1)], apply=True)

        self.assertEqual(writes, [])

    def test_apply_requires_write_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            publisher = GitHubCommentPublisher(
                settings_for(Path(directory), token=None),
                client=httpx.Client(
                    transport=httpx.MockTransport(
                        lambda _: (_ for _ in ()).throw(AssertionError("unexpected network"))
                    )
                ),
            )
            with self.assertRaises(ConfigurationError):
                publisher.publish(run_record(), [finding(1)], apply=True)


if __name__ == "__main__":
    unittest.main()
