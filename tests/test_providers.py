from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from bytecode_review_agent.config import Settings
from bytecode_review_agent.errors import SourceError
from bytecode_review_agent.providers import SourceLoader


def response(*, text: str = "", payload: object | None = None) -> Mock:
    value = Mock()
    value.text = text
    value.json.return_value = payload
    value.raise_for_status.return_value = None
    return value


def settings_for(path: Path) -> Settings:
    return Settings(
        data_dir=path,
        llm_base_url="https://model.invalid/v1",
        llm_api_key="test",
        llm_model="test-model",
        input_price_cny_per_million=Decimal("1"),
        output_price_cny_per_million=Decimal("1"),
        allowed_hosts=("github.com", "gitlab.com"),
        github_token=None,
        gitlab_token=None,
    )


class SourceLoaderTests(unittest.TestCase):
    def test_loads_github_pull_request_diff_with_read_only_headers(self) -> None:
        diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -0,0 +1 @@
+value = 1
"""
        with tempfile.TemporaryDirectory() as directory:
            configured = settings_for(Path(directory)).with_overrides(
                github_token="github-test-token"
            )
            def github_get(endpoint: str, **kwargs: object) -> Mock:
                accept = str(kwargs["headers"].get("Accept"))  # type: ignore[union-attr]
                if endpoint.endswith("/pulls/17/files"):
                    return response(
                        payload=[{"filename": "app.py", "status": "modified"}]
                    )
                if "/contents/app.py" in endpoint:
                    ref = kwargs["params"]["ref"]  # type: ignore[index]
                    return response(text="value = 0\n" if ref == "base-17" else "value = 1\n")
                if accept == "application/vnd.github.v3.diff":
                    return response(text=diff)
                return response(
                    payload={"base": {"sha": "base-17"}, "head": {"sha": "head-17"}}
                )

            with patch("bytecode_review_agent.providers.httpx.get", side_effect=github_get) as get:
                snapshot = SourceLoader(configured).load(
                    "https://github.com/example/project/pull/17"
                )

            self.assertEqual(snapshot.kind.value, "github")
            self.assertEqual(snapshot.diff, diff)
            self.assertEqual(snapshot.metadata["number"], 17)
            self.assertEqual(snapshot.metadata["base_sha"], "base-17")
            self.assertEqual(len(snapshot.file_contexts), 1)
            self.assertEqual(snapshot.file_contexts[0].base_content, "value = 0\n")
            self.assertEqual(snapshot.file_contexts[0].head_content, "value = 1\n")
            self.assertTrue(snapshot.file_contexts[0].base_content_sha256)
            self.assertEqual(len(get.call_args_list), 5)
            for call in get.call_args_list:
                self.assertEqual(
                    call.kwargs["headers"].get("Authorization"),
                    "Bearer github-test-token",
                )

    def test_loads_gitlab_merge_request_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            configured = settings_for(Path(directory)).with_overrides(
                gitlab_token="gitlab-test-token"
            )
            def gitlab_get(endpoint: str, **kwargs: object) -> Mock:
                if "/repository/files/" in endpoint:
                    ref = kwargs["params"]["ref"]  # type: ignore[index]
                    return response(text="old\n" if ref == "base-23" else "new\n")
                return response(
                    payload={
                        "diff_refs": {"base_sha": "base-23", "head_sha": "head-23"},
                        "changes": [
                            {
                                "old_path": "src/app.py",
                                "new_path": "src/app.py",
                                "new_file": False,
                                "deleted_file": False,
                                "diff": "@@ -1 +1 @@\n-old\n+new",
                            }
                        ],
                    }
                )

            with patch("bytecode_review_agent.providers.httpx.get", side_effect=gitlab_get) as get:
                snapshot = SourceLoader(configured).load(
                    "https://gitlab.com/example/group/project/-/merge_requests/23"
                )

            self.assertEqual(snapshot.kind.value, "gitlab")
            self.assertEqual(snapshot.metadata["iid"], 23)
            self.assertIn("diff --git a/src/app.py b/src/app.py", snapshot.diff)
            self.assertEqual(snapshot.metadata["head_sha"], "head-23")
            self.assertEqual(snapshot.file_contexts[0].base_content, "old\n")
            self.assertEqual(snapshot.file_contexts[0].head_content, "new\n")
            self.assertEqual(len(get.call_args_list), 3)
            for call in get.call_args_list:
                self.assertEqual(
                    call.kwargs["headers"]["PRIVATE-TOKEN"], "gitlab-test-token"
                )

    def test_rejects_non_https_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            loader = SourceLoader(settings_for(Path(directory)))
            with self.assertRaises(SourceError):
                loader.load("http://github.com/org/repo/pull/1")

    def test_rejects_non_allowlisted_host_before_network_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            loader = SourceLoader(settings_for(Path(directory)))
            with self.assertRaises(SourceError):
                loader.load("https://attacker.invalid/org/repo/pull/1")

    def test_rejects_url_query_to_avoid_persisting_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            loader = SourceLoader(settings_for(Path(directory)))
            with self.assertRaises(SourceError):
                loader.load("https://github.com/org/repo/pull/1?access_token=secret")


if __name__ == "__main__":
    unittest.main()
