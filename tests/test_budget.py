from __future__ import annotations

import unittest
from decimal import Decimal

from bytecode_review_agent.budget import BudgetGuard, Pricing
from bytecode_review_agent.errors import BudgetExceeded


class BudgetTests(unittest.TestCase):
    def test_reservation_rejects_call_before_budget_is_exceeded(self) -> None:
        pricing = Pricing(Decimal("10"), Decimal("20"))
        guard = BudgetGuard(Decimal("0.001"), Decimal("0"), pricing)
        with self.assertRaises(BudgetExceeded):
            guard.reserve(100, 100)

    def test_cost_uses_separate_input_and_output_prices(self) -> None:
        pricing = Pricing(Decimal("10"), Decimal("20"))
        self.assertEqual(pricing.cost(1_000, 500), Decimal("0.020000"))


if __name__ == "__main__":
    unittest.main()
