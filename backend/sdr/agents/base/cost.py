"""Token accounting and spend ceilings.

The host app's `routers/ai.py` tracks nothing - it constructs a client per
call and stuffs 20 leads plus 50 invoices into every system prompt. At one
user chatting that is merely wasteful; at 1,000 leads a day through 6 agents
it is a bill nobody predicted. So every agent run records its tokens and
estimated cost, and an org-wide daily cap stops the module rather than
discovering the overspend on an invoice.

**Prices are estimates.** NVIDIA NIM's build endpoint bills in credits rather
than per-token, so the figures below are approximations for budgeting and
relative comparison between agents - not an invoice. Override per deployment
with `SDR_COST_PER_1K_INPUT` / `SDR_COST_PER_1K_OUTPUT`. Everything derived
from them is labelled `cost_usd_estimated` for exactly this reason.

Pure module apart from reading env at import.
"""

import os

#: USD per 1,000 tokens. Defaults are in the region of a hosted 70B model.
DEFAULT_INPUT_PER_1K = 0.0004
DEFAULT_OUTPUT_PER_1K = 0.0008


def _rate(name: str, fallback: float) -> float:
    try:
        return float(os.environ.get(name, fallback))
    except (TypeError, ValueError):
        return fallback


INPUT_PER_1K = _rate("SDR_COST_PER_1K_INPUT", DEFAULT_INPUT_PER_1K)
OUTPUT_PER_1K = _rate("SDR_COST_PER_1K_OUTPUT", DEFAULT_OUTPUT_PER_1K)


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Estimated USD for one LLM call."""
    input_tokens = max(0, int(input_tokens or 0))
    output_tokens = max(0, int(output_tokens or 0))
    cost = (input_tokens / 1000) * INPUT_PER_1K + (output_tokens / 1000) * OUTPUT_PER_1K
    return round(cost, 6)


def approximate_tokens(text: str) -> int:
    """Rough token count for pre-flight budget checks.

    ~4 characters per token is the usual English approximation. Used only to
    refuse a call that is obviously too large *before* paying for it; actual
    accounting always uses the provider's reported usage.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


class CostTracker:
    """Accumulates spend across one agent run and enforces its ceiling.

    Deliberately raises rather than truncating: an agent that silently stops
    mid-way produces a half-enriched record that looks complete, which is
    worse than a failure the operator can see and retry.
    """

    def __init__(self, ceiling_usd: float):
        self.ceiling_usd = ceiling_usd
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0
        self.calls = 0

    def record(self, input_tokens: int, output_tokens: int) -> float:
        from sdr.errors import CostCeilingError

        self.calls += 1
        self.input_tokens += max(0, int(input_tokens or 0))
        self.output_tokens += max(0, int(output_tokens or 0))
        self.cost_usd = estimate_cost(self.input_tokens, self.output_tokens)

        if self.ceiling_usd is not None and self.cost_usd > self.ceiling_usd:
            raise CostCeilingError(
                f"Run exceeded its cost ceiling "
                f"(${self.cost_usd:.4f} of ${self.ceiling_usd:.4f}).",
                detail={"cost_usd": self.cost_usd, "ceiling_usd": self.ceiling_usd},
            )
        return self.cost_usd

    def snapshot(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd_estimated": self.cost_usd,
            "llm_calls": self.calls,
        }
