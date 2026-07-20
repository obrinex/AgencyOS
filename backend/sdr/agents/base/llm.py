"""LLM access for agents.

Reuses the host app's NVIDIA NIM client (`routers/ai.py`) rather than opening
a second provider relationship - one API key, one place to rotate it. The
import is lazy and in-function, matching the pattern `leadfinder.py:242` and
`emails.py:32` already use to avoid a circular import.

Structured output is done by prompting for strict JSON and validating the
result, not by tool-calling: NVIDIA NIM's Llama deployments do not expose
reliable function-calling, and pretending otherwise would produce failures
that look random. `routers/leadfinder.py` already takes this approach - this
just makes it rigorous, with a repair attempt and schema validation.
"""

import json
import logging
import re

from sdr.agents.base import providers as provider_registry
from sdr.errors import ProviderError, SDRError

logger = logging.getLogger(__name__)


class LLMNotConfiguredError(SDRError):
    """No LLM credentials. A configuration problem, so retrying cannot help."""

    retryable = False
    status_code = 503

#: Models sometimes wrap JSON in markdown fences despite being told not to.
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def get_client_and_model():
    """The host app's configured client.

    `routers.ai._get_client()` raises a FastAPI HTTPException when
    NVIDIA_API_KEY is missing - correct for a request handler, wrong here: it
    would escape the agent layer untyped and be recorded as an unexpected
    crash. Converted to a non-retryable typed error so a missing key
    dead-letters immediately instead of burning five attempts against a
    configuration problem no retry can fix.
    """
    from fastapi import HTTPException

    from routers.ai import NVIDIA_MODEL, _get_client

    try:
        return _get_client(), NVIDIA_MODEL
    except HTTPException as exc:
        raise LLMNotConfiguredError(
            f"The AI assistant is not configured: {exc.detail}"
        )


def extract_json(text: str) -> dict:
    """Parse a model response that is supposed to be a JSON object.

    Tolerates markdown fences and leading prose, because models produce both
    regardless of instructions. Raises ValueError when there is genuinely no
    object - the caller turns that into a repair attempt.
    """
    if not text:
        raise ValueError("Empty response")

    cleaned = _FENCE.sub("", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Fall back to the outermost brace pair.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object in response")
    return json.loads(cleaned[start:end + 1])


def _is_rate_limit(exc: Exception) -> bool:
    """Whether an error is worth trying the next provider for.

    Rate limits and quota exhaustion are the whole reason the chain exists -
    they are the normal failure mode of a free tier, not an outage.
    """
    text = str(exc).lower()
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status in (429, 402, 503, 529):
        return True
    return any(
        marker in text for marker in
        ("rate limit", "rate_limit", "quota", "too many requests",
         "429", "capacity", "overloaded", "insufficient")
    )


async def complete_json(*, system: str, user: str, tracker,
                        temperature: float = 0.2, max_tokens: int = 1200,
                        ctx=None) -> tuple:
    """One JSON completion, walking the free-provider chain. Returns (parsed, raw).

    On a rate limit or quota refusal it moves to the next configured provider
    rather than failing - which is what makes free tiers usable in practice.
    Any other error fails immediately, because retrying a bad request against
    a different vendor just wastes another call.

    Which provider actually served the request is recorded on the run, so a
    quality or latency shift can be attributed to a provider change.
    """
    providers = provider_registry.chain()
    if not providers:
        raise LLMNotConfiguredError(
            "No LLM provider is configured. Set at least one of: "
            + ", ".join(p["api_key_env"] for p in provider_registry.describe())
        )

    attempts = []
    for key, make_client, model in providers:
        try:
            client = make_client()
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            attempts.append(f"{key}: {exc}")
            if _is_rate_limit(exc) and len(providers) > 1:
                logger.warning("Provider %s rate-limited, trying the next: %s", key, exc)
                if ctx is not None:
                    ctx.flag("provider_fallback", {"from": key, "reason": str(exc)[:200]})
                continue
            raise ProviderError(f"LLM call failed via {key}: {exc}")

        usage = getattr(response, "usage", None)
        tracker.record(
            getattr(usage, "prompt_tokens", 0) if usage else 0,
            getattr(usage, "completion_tokens", 0) if usage else 0,
        )
        if ctx is not None:
            ctx.provider_used = key
            ctx.model_used = model

        raw = (response.choices[0].message.content or "").strip()
        return extract_json(raw), raw

    raise ProviderError(
        "Every configured LLM provider refused the request. "
        + " | ".join(attempts[:4])
    )
