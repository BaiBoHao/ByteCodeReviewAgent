from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_UP

from bytecode_review_agent.errors import BudgetExceeded


_ONE_MILLION = Decimal(1_000_000)


@dataclass(frozen=True, slots=True)
class Pricing:
    input_cny_per_million: Decimal
    output_cny_per_million: Decimal

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        value = (
            Decimal(input_tokens) * self.input_cny_per_million
            + Decimal(output_tokens) * self.output_cny_per_million
        ) / _ONE_MILLION
        return value.quantize(Decimal("0.000001"), rounding=ROUND_UP)


@dataclass(frozen=True, slots=True)
class BudgetGuard:
    limit_cny: Decimal
    spent_cny: Decimal
    pricing: Pricing

    def reserve(self, estimated_input_tokens: int, max_output_tokens: int) -> Decimal:
        estimated = self.pricing.cost(estimated_input_tokens, max_output_tokens)
        if self.spent_cny + estimated > self.limit_cny:
            raise BudgetExceeded(
                "LLM call skipped: estimated total cost "
                f"{self.spent_cny + estimated} CNY exceeds budget {self.limit_cny} CNY"
            )
        return estimated
