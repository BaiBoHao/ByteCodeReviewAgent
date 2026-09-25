from __future__ import annotations

import unittest

from bytecode_review_agent.diff_parser import chunk_diff
from bytecode_review_agent.security import SecretRedactor


SAMPLE_DIFF = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -0,0 +1,3 @@
+password = "supersecret123"
+value = eval(user_input)
+print(value)
"""


class DiffAndSecurityTests(unittest.TestCase):
    def test_parses_added_line_numbers(self) -> None:
        chunks = chunk_diff(SAMPLE_DIFF, max_chars=10_000)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].file_path, "app.py")
        self.assertEqual(chunks[0].added_lines, {1, 2, 3})
        self.assertEqual(chunks[0].removed_lines, set())

    def test_parses_removed_line_numbers(self) -> None:
        diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -4,3 +4,1 @@
-guard = True
-validate(guard)
 return run()
"""
        chunk = chunk_diff(diff, max_chars=10_000)[0]
        self.assertEqual(chunk.removed_lines, {4, 5})
        self.assertEqual(chunk.added_lines, set())

    def test_redacts_secret_assignments_before_model_use(self) -> None:
        sanitized, count = SecretRedactor().redact(SAMPLE_DIFF)
        self.assertEqual(count, 1)
        self.assertNotIn("supersecret123", sanitized)
        self.assertIn("[REDACTED_SECRET]", sanitized)

    def test_large_hunk_is_split_without_losing_added_line_numbers(self) -> None:
        body = "".join(f"+line_{index:03d} = '{'x' * 20}'\n" for index in range(1, 101))
        diff = (
            "diff --git a/large.py b/large.py\n"
            "--- a/large.py\n"
            "+++ b/large.py\n"
            "@@ -0,0 +1,100 @@\n"
            f"{body}"
        )
        chunks = chunk_diff(diff, max_chars=500)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(
            set().union(*(chunk.added_lines for chunk in chunks)), set(range(1, 101))
        )


if __name__ == "__main__":
    unittest.main()
