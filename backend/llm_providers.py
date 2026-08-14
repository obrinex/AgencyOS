"""LLM provider registry with automatic fallback.

Most providers here speak the OpenAI chat-completions protocol - so one client
library covers the lot and switching is a base-URL change, not a rewrite.
Anthropic does not, and is handled by an adapter (see `_AnthropicAdapter`);
that is the only exception, and it is deliberate.

**Why a chain rather than one provider.** Free tiers rate-limit aggressively
and inconsistently: Groq gives you a handful of requests per minute, Gemini
resets daily, NVIDIA's credits run down. Any single one will refuse you at
some point. Chaining means a 429 moves to the next provider instead of
failing the job, which is the difference between "free tier" being a viable
default and being a demo toy.

Order is configured by `LLM_PROVIDERS` (comma-separated keys). Whichever
providers have keys set are used, in that order; the rest are skipped. With
nothing configured the module falls back to the host app's existing NVIDIA
setup, so this changes no behaviour until a key is added.

`SDR_LLM_PROVIDERS` is still read as a fallback. This module was extracted from
the deleted AI SDR module - it is provider plumbing, not an agent, and
`routers/ai.py` (the CRM assistant, email and proposal writers, meeting
summariser, lead reply drafter) and the Lead Finder all depend on it. The old
variable name is honoured because it is set in the live deployment's
environment, and silently changing which provider answers is not something a
refactor gets to do.

**Free and paid providers are both listed, and `tier` says which.** A paid
provider will happily bill you for the traffic a free one refuses, so the
chain must never silently promote one. Paid providers are absent from
`DEFAULT_ORDER` on purpose: they only run when `SDR_LLM_PROVIDERS` names
them, which makes spending an explicit act rather than a fallback.

Adding an OpenAI-protocol provider is one entry here plus an env var. No
other file changes.
"""

import logging
import os

logger = logging.getLogger(__name__)

#: Wire protocols. `openai` covers everything reachable with the `openai`
#: client library by changing `base_url`. `anthropic` is Claude's own API,
#: which is a genuinely different request and response shape.
OPENAI_PROTOCOL = "openai"
ANTHROPIC_PROTOCOL = "anthropic"

#: `free_note` is shown in the UI so an operator can see what they are
#: actually getting before wiring a key in. Limits and prices move constantly -
#: these are indicative, not contractual, and are labelled as such in the UI.
PROVIDERS = {
    "nvidia": {
        "label": "NVIDIA NIM",
        "protocol": OPENAI_PROTOCOL,
        "tier": "free",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_env": "NVIDIA_API_KEY",
        "default_model": "meta/llama-3.3-70b-instruct",
        "model_env": "NVIDIA_MODEL",
        "free_note": "Free credits on signup. Large models, moderate speed.",
        "good_for": ["reasoning", "long_context", "generation"],
    },
    "groq": {
        "label": "Groq",
        "protocol": OPENAI_PROTOCOL,
        "tier": "free",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
        "model_env": "GROQ_MODEL",
        "free_note": "Free tier, per-minute rate limits. By far the fastest.",
        "good_for": ["classification", "extraction", "fast_generation"],
    },
    "gemini": {
        "label": "Google Gemini",
        "protocol": OPENAI_PROTOCOL,
        "tier": "free",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "default_model": "gemini-2.0-flash",
        "model_env": "GEMINI_MODEL",
        "free_note": "Generous free daily quota. Very large context window.",
        "good_for": ["long_context", "summarisation", "generation"],
    },
    "cerebras": {
        "label": "Cerebras",
        "protocol": OPENAI_PROTOCOL,
        "tier": "free",
        "base_url": "https://api.cerebras.ai/v1",
        "api_key_env": "CEREBRAS_API_KEY",
        "default_model": "llama-3.3-70b",
        "model_env": "CEREBRAS_MODEL",
        "free_note": "Free tier with daily token limits. Extremely fast.",
        "good_for": ["classification", "fast_generation"],
    },
    "openrouter": {
        "label": "OpenRouter",
        "protocol": OPENAI_PROTOCOL,
        "tier": "free",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        # Models suffixed `:free` cost nothing but are heavily rate-limited.
        "default_model": "meta-llama/llama-3.3-70b-instruct:free",
        "model_env": "OPENROUTER_MODEL",
        "free_note": "Aggregates many providers; `:free` models cost nothing.",
        "good_for": ["fallback", "generation"],
    },
    "mistral": {
        "label": "Mistral",
        "protocol": OPENAI_PROTOCOL,
        "tier": "free",
        "base_url": "https://api.mistral.ai/v1",
        "api_key_env": "MISTRAL_API_KEY",
        "default_model": "mistral-small-latest",
        "model_env": "MISTRAL_MODEL",
        "free_note": "Free experimental tier with rate limits.",
        "good_for": ["generation", "classification"],
    },
    # --- Paid. Absent from DEFAULT_ORDER; opt in via SDR_LLM_PROVIDERS. ------
    "openai": {
        "label": "OpenAI",
        "protocol": OPENAI_PROTOCOL,
        "tier": "paid",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "default_model": "gpt-4o-mini",
        "model_env": "OPENAI_MODEL",
        "free_note": "Paid per token. No free tier - billed from the first call.",
        "good_for": ["generation", "classification", "extraction"],
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "protocol": ANTHROPIC_PROTOCOL,
        "tier": "paid",
        "base_url": "https://api.anthropic.com",
        "api_key_env": "ANTHROPIC_API_KEY",
        # Opus is the strongest model and the right default for outreach copy,
        # which is the one thing in this pipeline nobody has verified is any
        # good. Set ANTHROPIC_MODEL=claude-haiku-4-5 once volume matters more
        # than prose quality.
        "default_model": "claude-opus-4-8",
        "model_env": "ANTHROPIC_MODEL",
        "free_note": "Paid per token. Strongest writing; no free tier.",
        "good_for": ["generation", "reasoning", "long_context"],
    },
}

#: Tried in this order unless LLM_PROVIDERS overrides it. Groq and Cerebras
#: lead because they are fastest and their limits reset per minute - so a
#: refusal costs seconds, not a day.
#:
#: Only free providers appear here. A paid provider reached by fallback would
#: turn "the free tier is busy" into a bill, silently, so paid keys are used
#: only when LLM_PROVIDERS names them.
DEFAULT_ORDER = ("groq", "cerebras", "gemini", "nvidia", "openrouter", "mistral")

#: New name first, old name second. See the module docstring.
ORDER_ENV_VARS = ("LLM_PROVIDERS", "SDR_LLM_PROVIDERS")


def configured_order() -> list:
    raw = next((os.environ[name] for name in ORDER_ENV_VARS if os.environ.get(name)), "")
    requested = [key.strip() for key in raw.split(",") if key.strip()]
    return [key for key in (requested or DEFAULT_ORDER) if key in PROVIDERS]


def is_configured(key: str) -> bool:
    provider = PROVIDERS.get(key)
    return bool(provider and os.environ.get(provider["api_key_env"]))


def model_for(key: str) -> str:
    provider = PROVIDERS[key]
    return os.environ.get(provider["model_env"], provider["default_model"])


def protocol_for(key: str) -> str:
    return PROVIDERS[key].get("protocol", OPENAI_PROTOCOL)


def is_billable(key: str) -> bool:
    """Whether using this provider, as currently configured, costs money.

    Distinct from `tier`, because OpenRouter is both. It aggregates many
    vendors: models suffixed `:free` cost nothing, everything else on the same
    key bills normally. So the tier is a property of the *model*, not the
    provider, and an OPENROUTER_MODEL override is all it takes to turn a free
    provider into a paid one without touching any of the cost controls.

    The UI badge reads from this rather than from `tier`, so it reports what
    will actually be charged instead of what the catalogue intended.
    """
    if PROVIDERS[key].get("tier") == "paid":
        return True
    if key == "openrouter":
        return not model_for(key).endswith(":free")
    return False


def available() -> list:
    """Providers with a key set, in the order they will be tried."""
    return [key for key in configured_order() if is_configured(key)]


def describe() -> list:
    """Full catalogue for the UI, including unconfigured providers.

    Showing what is *not* set up is the point - it is how someone discovers
    they could add a free Groq key and get a faster fallback.
    """
    order = configured_order()
    return [
        {
            "key": key,
            "label": PROVIDERS[key]["label"],
            "configured": is_configured(key),
            "model": model_for(key),
            "free_note": PROVIDERS[key]["free_note"],
            "good_for": PROVIDERS[key]["good_for"],
            "api_key_env": PROVIDERS[key]["api_key_env"],
            "tier": "paid" if is_billable(key) else "free",
            "declared_tier": PROVIDERS[key].get("tier", "free"),
            "protocol": protocol_for(key),
            "priority": order.index(key) if key in order else None,
        }
        for key in PROVIDERS
    ]


# --- Anthropic adapter --------------------------------------------------------
#
# Claude's API is not OpenAI-shaped: the system prompt is a top-level argument
# rather than a message, `max_tokens` is required, usage counts are named
# differently, and on Opus 4.8 a `temperature` argument is rejected outright
# with a 400.
#
# Rather than branch every caller on provider, this adapter calls the official
# `anthropic` SDK and normalises the result into the shape the rest of this
# codebase already reads. It is NOT the OpenAI client pointed at Anthropic -
# that would break in exactly the ways listed above.


class _Usage:
    def __init__(self, prompt_tokens: int, completion_tokens: int):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _Message:
    def __init__(self, content: str):
        self.content = content


class _Choice:
    def __init__(self, content: str):
        self.message = _Message(content)
        self.delta = _Message(content)


class _Completion:
    def __init__(self, content: str, prompt_tokens: int = 0, completion_tokens: int = 0):
        self.choices = [_Choice(content)]
        self.usage = _Usage(prompt_tokens, completion_tokens)


class _AnthropicAdapter:
    """Exposes `.chat.completions.create()` over the native Anthropic SDK."""

    def __init__(self, api_key: str):
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover - depends on install
            raise LookupError(
                "The `anthropic` package is not installed, so ANTHROPIC_API_KEY "
                "cannot be used. Add `anthropic` to backend/requirements.txt."
            ) from exc
        self._client = AsyncAnthropic(api_key=api_key)
        self.chat = self  # so callers can write `client.chat.completions`

    @property
    def completions(self):
        return self

    @staticmethod
    def _split(messages: list) -> tuple:
        """Claude takes the system prompt separately from the turns."""
        system = "\n\n".join(
            m["content"] for m in messages if m.get("role") == "system"
        )
        turns = [
            {"role": m["role"], "content": m["content"]}
            for m in messages if m.get("role") in ("user", "assistant")
        ]
        return system, turns

    async def create(self, *, model: str, messages: list, max_tokens: int = 4096,
                     stream: bool = False, **ignored):
        # `temperature` and `timeout` arrive from the OpenAI-shaped call sites.
        # Opus 4.8 rejects temperature with a 400, so it is dropped here rather
        # than at every caller - which is the entire reason this adapter exists.
        system, turns = self._split(messages)
        request = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": turns or [{"role": "user", "content": ""}],
        }
        if system:
            request["system"] = system

        if stream:
            return self._stream(request)

        response = await self._client.messages.create(**request)
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined this request (stop_reason=refusal)")
        text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        return _Completion(
            text,
            getattr(response.usage, "input_tokens", 0),
            getattr(response.usage, "output_tokens", 0),
        )

    async def _stream(self, request: dict):
        async with self._client.messages.stream(**request) as stream:
            async for chunk in stream.text_stream:
                yield _Completion(chunk)


def build_client(key: str):
    """A client for this provider, speaking whichever protocol it uses.

    Constructed per call rather than cached - a cached client would hold a
    stale key after rotation.
    """
    provider = PROVIDERS[key]
    api_key = os.environ.get(provider["api_key_env"])
    if not api_key:
        raise LookupError(f"{provider['label']} has no API key ({provider['api_key_env']})")

    if protocol_for(key) == ANTHROPIC_PROTOCOL:
        return _AnthropicAdapter(api_key)

    from openai import AsyncOpenAI
    return AsyncOpenAI(base_url=provider["base_url"], api_key=api_key)


def chain() -> list:
    """(key, client_factory, model) for each usable provider, in order.

    Falls back to the host app's NVIDIA configuration when nothing else is
    set, so this is a strict superset of the previous behaviour.
    """
    usable = available()
    if usable:
        return [(key, lambda k=key: build_client(k), model_for(key)) for key in usable]

    if os.environ.get("NVIDIA_API_KEY"):
        return [("nvidia", lambda: build_client("nvidia"), model_for("nvidia"))]
    return []
