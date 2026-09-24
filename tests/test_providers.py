from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from bytecode_review_agent.config import Settings
from bytecode_review_agent.errors import SourceError
from bytecode_review_agent.providers import SourceLoader


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
            response = Mock()
            response.text = diff
            response.raise_for_status.return_value = None
            with patch("bytecode_review_agent.providers.httpx.get", return_value=response) as get:
                snapshot = SourceLoader(configured).load(
                    "https://github.com/example/project/pull/17"
                )

            self.assertEqual(snapshot.kind.value, "github")
            self.assertEqual(snapshot.diff, diff)
            self.assertEqual(snapshot.metadata["number"], 17)
            endpoint = get.call_args.args[0]
            headers = get.call_args.kwargs["headers"]
            self.assertEqual(endpoint, "https://api.github.com/repos/example/project/pulls/17")
            self.assertEqual(headers["Accept"], "application/vnd.github.v3.diff")
            self.assertEqual(headers["Authorization"], "Bearer github-test-token")

    def test_loads_gitlab_merge_request_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            configured = settings_for(Path(directory)).with_overrides(
                gitlab_token="gitlab-test-token"
            )
            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {
                "changes": [
                    {
                        "old_path": "src/app.py",
                        "new_path": "src/app.py",
                        "new_file": False,
                        "deleted_file": False,
                        "diff": "@@ -1 +1 @@\n-old\n+new",
                    }
                ]
            }
            with patch("bytecode_review_agent.providers.httpx.get", return_value=response) as get:
                snapshot = SourceLoader(configured).load(
                    "https://gitlab.com/example/group/project/-/merge_requests/23"
                )

            self.assertEqual(snapshot.kind.value, "gitlab")
            self.assertEqual(snapshot.metadata["iid"], 23)
            self.assertIn("diff --git a/src/app.py b/src/app.py", snapshot.diff)
            endpoint = get.call_args.args[0]
            headers = get.call_args.kwargs["headers"]
            self.assertIn("projects/example%2Fgroup%2Fproject/merge_requests/23/changes", endpoint)
            self.assertEqual(headers["PRIVATE-TOKEN"], "gitlab-test-token")

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
