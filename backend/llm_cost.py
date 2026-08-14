"""Token accounting for LLM calls.

Extracted from the deleted AI SDR module alongside `llm_providers`, because
`routers/ai.py` estimates spend with it and it is not an agent.

**Prices are estimates.** NVIDIA NIM's build endpoint bills in credits rather
than per-token, so the figures below are approximations for budgeting and
relative comparison - not an invoice. Override per deployment with
`SDR_COST_PER_1K_INPUT` / `SDR_COST_PER_1K_OUTPUT` (names kept: they are set in
the live environment). Everything derived from them is labelled
`cost_usd_estimated` for exactly this reason.

The per-run recording and the org-wide daily cap that used to consume this
lived in the agent runtime and went with it. What survives is the arithmetic.

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
