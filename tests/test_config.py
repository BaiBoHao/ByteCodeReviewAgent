from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from bytecode_review_agent.cli import app
from bytecode_review_agent.config import Settings
from bytecode_review_agent.errors import ConfigurationError


ENV_CONTENT = """# 本地测试配置
REVIEW_AGENT_LLM_BASE_URL=https://model.example/v1
REVIEW_AGENT_LLM_API_KEY="file-secret-value"
REVIEW_AGENT_LLM_MODEL=test-model
REVIEW_AGENT_INPUT_PRICE_CNY_PER_MILLION=2
REVIEW_AGENT_OUTPUT_PRICE_CNY_PER_MILLION=8
REVIEW_AGENT_ALLOWED_HOSTS=github.com,gitlab.example.com
"""


class SettingsFileTests(unittest.TestCase):
    def test_default_env_file_is_loaded_from_current_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(ENV_CONTENT, encoding="utf-8")
            previous_directory = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, {}, clear=True):
                    settings = Settings.from_env()
            finally:
                os.chdir(previous_directory)

            self.assertEqual(settings.llm_model, "test-model")
            self.assertEqual(settings.env_file_path, (root / ".env").resolve())

    def test_explicit_env_file_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / "review.env"
            env_file.write_text(ENV_CONTENT, encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                settings = Settings.from_env(env_file=env_file)

            self.assertEqual(settings.llm_base_url, "https://model.example/v1")
            self.assertEqual(settings.llm_api_key, "file-secret-value")
            self.assertEqual(settings.llm_model, "test-model")
            self.assertEqual(settings.allowed_hosts, ("github.com", "gitlab.example.com"))
            self.assertEqual(settings.env_file_path, env_file.resolve())

    def test_environment_variable_overrides_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(ENV_CONTENT, encoding="utf-8")
            with patch.dict(
                os.environ,
                {"REVIEW_AGENT_LLM_MODEL": "environment-model"},
                clear=True,
            ):
                settings = Settings.from_env(env_file=env_file)

            self.assertEqual(settings.llm_model, "environment-model")
            self.assertEqual(settings.llm_api_key, "file-secret-value")

    def test_missing_explicit_env_file_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.env"
            with self.assertRaises(ConfigurationError):
                Settings.from_env(env_file=missing)

    def test_example_placeholders_are_not_accepted_as_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                ENV_CONTENT.replace("file-secret-value", "replace-me"),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                settings = Settings.from_env(env_file=env_file)

            with self.assertRaisesRegex(ConfigurationError, "placeholder"):
                settings.validate_for_review()

    def test_doctor_never_prints_api_key(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(ENV_CONTENT, encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                result = runner.invoke(app, ["doctor", "--env-file", str(env_file)])

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("API Key: 已配置", result.output)
            self.assertIn("配置状态: 可以执行评审", result.output)
            self.assertNotIn("file-secret-value", result.output)


if __name__ == "__main__":
    unittest.main()
