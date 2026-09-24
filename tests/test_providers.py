from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

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
