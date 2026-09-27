from __future__ import annotations

import json
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from bytecode_review_agent.api import create_app
from bytecode_review_agent.config import Settings
from bytecode_review_agent.models import (
    FileContext,
    LLMCallResult,
    RunStatus,
    SourceKind,
    SourceSnapshot,
)
from bytecode_review_agent.providers import SourceLoader
from bytecode_review_agent.service import ReviewService
from bytecode_review_agent.storage import SQLiteStorage
from bytecode_review_agent.tools import default_registry
from bytecode_review_agent.utils import atomic_write_text


DIFF = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -0,0 +1 @@
+value = eval(user_input)
"""


class APIReviewer:
    model = "api-test-model"

    def review(
        self, system_prompt: str, user_prompt: str, max_output_tokens: int
    ) -> LLMCallResult:
        return LLMCallResult(
            content=json.dumps(
                {
                    "findings": [
                        {
                            "file_path": "app.py",
                            "line": 1,
                            "severity": "high",
                            "category": "security",
                            "title": "执行了不可信输入",
                            "explanation": "eval 会执行调用者提供的 Python 代码。",
                            "suggestion": "改用白名单解析器。",
                            "confidence": "high",
                            "evidence": ["新增行调用了 eval。"],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            input_tokens=200,
            output_tokens=80,
            request_id="api-test-request",
        )


def settings_for(root: Path) -> Settings:
    return Settings(
        data_dir=root / "agent-data",
        llm_base_url="https://model.invalid/v1",
        llm_api_key="api-test-key",
        llm_model="api-test-model",
        input_price_cny_per_million=Decimal("1"),
        output_price_cny_per_million=Decimal("2"),
        allowed_hosts=("github.com", "gitlab.com"),
        github_token=None,
        gitlab_token=None,
    )


def service_factory(settings: Settings, storage: SQLiteStorage) -> ReviewService:
    return ReviewService(
        settings=settings,
        reviewer=APIReviewer(),
        storage=storage,
        sources=SourceLoader(settings),
        tools=default_registry(load_plugins=False),
    )


class LocalAPITests(unittest.TestCase):
    def test_session_token_host_and_origin_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(
                settings=settings_for(Path(directory)),
                service_factory=service_factory,
                static_dir=Path(directory) / "missing-static",
                session_token="session-test-token",
                pairing_code="A1B2C3D4",
            )
            with TestClient(app) as client:
                extension_origin = f"chrome-extension://{'a' * 32}"
                unauthorized = client.get("/api/config")
                bootstrap = client.get("/api/bootstrap")
                authorized = client.get("/api/config")
                rejected_origin = client.post(
                    "/api/reviews",
                    headers={"Origin": "https://attacker.invalid"},
                    json={"source": "change.diff", "budget_cny": "1"},
                )
                rejected_host = client.get(
                    "/api/config",
                    headers={"Host": "attacker.invalid"},
                )
                wrong_pair = client.post(
                    "/api/pair",
                    headers={"Origin": extension_origin},
                    json={"code": "00000000"},
                )
                paired = client.post(
                    "/api/pair",
                    headers={"Origin": extension_origin},
                    json={"code": "a1b2c3d4"},
                )
                preflight = client.options(
                    "/api/pair",
                    headers={
                        "Origin": extension_origin,
                        "Access-Control-Request-Method": "POST",
                        "Access-Control-Request-Headers": "content-type",
                    },
                )

            self.assertEqual(unauthorized.status_code, 401)
            self.assertEqual(bootstrap.status_code, 200)
            self.assertEqual(authorized.status_code, 200)
            self.assertEqual(rejected_origin.status_code, 403)
            self.assertEqual(rejected_host.status_code, 400)
            self.assertEqual(wrong_pair.status_code, 401)
            self.assertEqual(paired.status_code, 200)
            self.assertEqual(paired.json()["session_token"], "session-test-token")
            self.assertEqual(preflight.status_code, 200)
            self.assertEqual(
                preflight.headers["access-control-allow-origin"],
                extension_origin,
            )

    def test_built_web_app_is_served_without_shadowing_api_404s(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            static_dir = (
                Path(__file__).resolve().parents[1]
                / "src"
                / "bytecode_review_agent"
                / "web_dist"
            )
            app = create_app(
                settings=settings_for(Path(directory)),
                service_factory=service_factory,
                static_dir=static_dir,
            )
            with TestClient(app) as client:
                page = client.get("/")
                missing_api = client.get("/api/not-found")

            self.assertEqual(page.status_code, 200)
            self.assertIn("<title>Review Agent</title>", page.text)
            self.assertEqual(missing_api.status_code, 404)

    def test_health_and_config_do_not_expose_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(
                settings=settings_for(Path(directory)),
                service_factory=service_factory,
                static_dir=Path(directory) / "missing-static",
            )
            with TestClient(app) as client:
                health = client.get("/api/health")
                config = client.get("/api/config")

            self.assertEqual(health.status_code, 200)
            self.assertTrue(health.json()["local_only"])
            self.assertTrue(config.json()["ready"])
            self.assertTrue(config.json()["api_key_configured"])
            self.assertNotIn("api-test-key", config.text)

    def test_unconfigured_model_cannot_start_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = create_app(
                settings=settings_for(root).with_overrides(llm_api_key=None),
                service_factory=service_factory,
                static_dir=root / "missing-static",
            )
            with TestClient(app) as client:
                response = client.post(
                    "/api/reviews",
                    json={"source": "change.diff", "budget_cny": "1"},
                )

            self.assertEqual(response.status_code, 400)
            self.assertIn("REVIEW_AGENT_LLM_API_KEY", response.text)

    def test_review_language_is_validated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = create_app(
                settings=settings_for(root),
                service_factory=service_factory,
                static_dir=root / "missing-static",
            )
            with TestClient(app) as client:
                response = client.post(
                    "/api/reviews",
                    json={
                        "source": "change.diff",
                        "budget_cny": "1",
                        "language": "fr-FR",
                    },
                )

            self.assertEqual(response.status_code, 422)

    def test_context_endpoint_returns_only_run_scoped_sanitized_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = settings_for(root)
            storage = SQLiteStorage(settings.database_path)
            app = create_app(
                settings=settings,
                service_factory=service_factory,
                static_dir=root / "missing-static",
            )
            diff_path = root / "change.diff"
            diff_path.write_text(DIFF, encoding="utf-8")
            service = service_factory(settings, storage)
            result = service.start(str(diff_path), budget_cny=Decimal("1"))
            context = FileContext(
                file_path="app.py",
                old_path="app.py",
                new_path="app.py",
                status="modified",
                base_content="value = 0\n",
                head_content="value = 1\n",
                base_content_sha256="base-hash",
                head_content_sha256="head-hash",
            )
            atomic_write_text(
                result.run.sanitized_diff_path.with_name("contexts.json"),
                json.dumps([context.model_dump(mode="json")]),
            )

            with TestClient(app) as client:
                base = client.get(
                    f"/api/runs/{result.run.id}/context",
                    params={"file_path": "app.py", "side": "base"},
                )
                missing = client.get(
                    f"/api/runs/{result.run.id}/context",
                    params={"file_path": "../secret.txt", "side": "base"},
                )

            self.assertEqual(base.status_code, 200)
            self.assertEqual(base.json()["content"], "value = 0\n")
            self.assertEqual(base.json()["content_sha256"], "base-hash")
            self.assertEqual(missing.status_code, 404)

    def test_publish_endpoint_defaults_to_safe_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = settings_for(root)
            storage = SQLiteStorage(settings.database_path)
            run_id = "run_publish_api"
            storage.create_run(
                run_id=run_id,
                source=SourceSnapshot(
                    kind=SourceKind.GITHUB,
                    reference="https://github.com/acme/project/pull/7",
                    provider="github",
                    diff=DIFF,
                    metadata={"head_sha": "head-reviewed"},
                ),
                diff_sha256="a" * 64,
                raw_diff_path=root / "raw.diff",
                sanitized_diff_path=root / "sanitized.diff",
                total_chunks=1,
                budget_cny=Decimal("1"),
                config={"source_metadata": {"head_sha": "head-reviewed"}},
            )
            storage.mark_terminal(run_id, RunStatus.COMPLETED)
            app = create_app(
                settings=settings,
                service_factory=service_factory,
                static_dir=root / "missing-static",
            )

            with TestClient(app) as client:
                preview = client.post(f"/api/runs/{run_id}/publish", json={})
                apply = client.post(
                    f"/api/runs/{run_id}/publish",
                    json={"apply": True},
                )

            self.assertEqual(preview.status_code, 200, preview.text)
            self.assertTrue(preview.json()["dry_run"])
            self.assertEqual(preview.json()["eligible_count"], 0)
            self.assertEqual(apply.status_code, 400)
            self.assertIn("GITHUB_TOKEN", apply.text)

    def test_background_review_exposes_run_findings_and_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            diff_path = root / "change.diff"
            diff_path.write_text(DIFF, encoding="utf-8")
            app = create_app(
                settings=settings_for(root),
                service_factory=service_factory,
                static_dir=root / "missing-static",
            )
            with TestClient(app) as client:
                created = client.post(
                    "/api/reviews",
                    json={"source": str(diff_path), "budget_cny": "1"},
                )
                self.assertEqual(created.status_code, 202, created.text)
                job_id = created.json()["id"]

                job: dict[str, object] = {}
                for _ in range(100):
                    job = client.get(f"/api/jobs/{job_id}").json()
                    if job["status"] in {"completed", "failed"}:
                        break
                    time.sleep(0.02)

                self.assertEqual(job["status"], "completed", job)
                run_id = str(job["run_id"])
                detail = client.get(f"/api/runs/{run_id}")
                self.assertEqual(detail.status_code, 200)
                self.assertEqual(len(detail.json()["findings"]), 1)
                self.assertEqual(detail.json()["run"]["status"], "completed")
                trace_id = detail.json()["findings"][0]["trace_id"]
                trace = client.get(f"/api/traces/{trace_id}")
                self.assertEqual(trace.status_code, 200)
                self.assertEqual(trace.json()["request_id"], "api-test-request")


if __name__ == "__main__":
    unittest.main()
