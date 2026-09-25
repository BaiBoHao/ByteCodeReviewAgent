from __future__ import annotations

import unittest

from bytecode_review_agent.context import select_context
from bytecode_review_agent.diff_parser import chunk_diff
from bytecode_review_agent.models import FileContext
from bytecode_review_agent.utils import sha256_text


BASE = """from decimal import Decimal

def calculate_total(values):
    return sum(values)

def average(values):
    if not values:
        return Decimal("0")
    return calculate_total(values) / len(values)
"""

HEAD = """from decimal import Decimal

def calculate_total(values):
    return sum(values)

def average(values):
    return calculate_total(values) / len(values)
"""

DIFF = (
    "diff --git a/math_service.py b/math_service.py\n"
    "--- a/math_service.py\n"
    "+++ b/math_service.py\n"
    "@@ -5,5 +5,3 @@ def calculate_total(values):\n"
    " \n"
    " def average(values):\n"
    "-    if not values:\n"
    "-        return Decimal(\"0\")\n"
    "     return calculate_total(values) / len(values)\n"
)


class ContextSelectionTests(unittest.TestCase):
    def test_python_deletion_selects_matching_base_and_head_function(self) -> None:
        chunk = chunk_diff(DIFF, max_chars=10_000)[0]
        context = FileContext(
            file_path="math_service.py",
            old_path="math_service.py",
            new_path="math_service.py",
            status="modified",
            base_commit_sha="base",
            head_commit_sha="head",
            base_content=BASE,
            head_content=HEAD,
            base_content_sha256=sha256_text(BASE),
            head_content_sha256=sha256_text(HEAD),
        )

        selected = select_context(chunk, context, max_chars=4_000)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected.strategy, "python-symbol")
        self.assertIn("average", selected.symbols)
        self.assertIn('return Decimal("0")', selected.base_excerpt or "")
        self.assertIn("return calculate_total(values)", selected.head_excerpt or "")
        self.assertNotIn("def calculate_total", selected.head_excerpt or "")

    def test_context_is_truncated_to_budget(self) -> None:
        chunk = chunk_diff(DIFF, max_chars=10_000)[0]
        context = FileContext(
            file_path="math_service.py",
            old_path="math_service.py",
            new_path="math_service.py",
            status="modified",
            base_content=BASE,
            head_content=HEAD,
        )

        selected = select_context(chunk, context, max_chars=60)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertIn("上下文已按预算截断", selected.base_excerpt or "")


if __name__ == "__main__":
    unittest.main()
