"""Free LLM provider registry with automatic fallback.

Every provider here has a genuinely free tier, and all of them speak the
OpenAI chat-completions protocol - so one client library covers the lot and
switching is a base-URL change, not a rewrite.

**Why a chain rather than one provider.** Free tiers rate-limit aggressively
and inconsistently: Groq gives you a handful of requests per minute, Gemini
resets daily, NVIDIA's credits run down. Any single one will refuse you at
some point. Chaining means a 429 moves to the next provider instead of
failing the job, which is the difference between "free tier" being a viable
default and being a demo toy.

Order is configured by `SDR_LLM_PROVIDERS` (comma-separated keys). Whichever
providers have keys set are used, in that order; the rest are skipped. With
nothing configured the module falls back to the host app's existing NVIDIA
setup, so this changes no behaviour until a key is added.

Adding a provider is one entry here plus an env var. No other file changes.
"""

import logging
import os

logger = logging.getLogger(__name__)

#: Every entry is OpenAI-protocol compatible.
#:
#: `free_note` is shown in the UI so an operator can see what they are
#: actually getting before wiring a key in. Limits move constantly - these are
#: indicative, not contractual, and are labelled as such in the UI.
PROVIDERS = {
    "nvidia": {
        "label": "NVIDIA NIM",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_env": "NVIDIA_API_KEY",
        "default_model": "meta/llama-3.3-70b-instruct",
        "model_env": "NVIDIA_MODEL",
        "free_note": "Free credits on signup. Large models, moderate speed.",
        "good_for": ["reasoning", "long_context", "generation"],
    },
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
        "model_env": "GROQ_MODEL",
        "free_note": "Free tier, per-minute rate limits. By far the fastest.",
        "good_for": ["classification", "extraction", "fast_generation"],
    },
    "gemini": {
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "default_model": "gemini-2.0-flash",
        "model_env": "GEMINI_MODEL",
        "free_note": "Generous free daily quota. Very large context window.",
        "good_for": ["long_context", "summarisation", "generation"],
    },
    "cerebras": {
        "label": "Cerebras",
        "base_url": "https://api.cerebras.ai/v1",
        "api_key_env": "CEREBRAS_API_KEY",
        "default_model": "llama-3.3-70b",
        "model_env": "CEREBRAS_MODEL",
        "free_note": "Free tier with daily token limits. Extremely fast.",
        "good_for": ["classification", "fast_generation"],
    },
    "openrouter": {
        "label": "OpenRouter",
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
        "base_url": "https://api.mistral.ai/v1",
        "api_key_env": "MISTRAL_API_KEY",
        "default_model": "mistral-small-latest",
        "model_env": "MISTRAL_MODEL",
        "free_note": "Free experimental tier with rate limits.",
        "good_for": ["generation", "classification"],
    },
}

#: Tried in this order unless SDR_LLM_PROVIDERS overrides it. Groq and
#: Cerebras lead because they are fastest and their limits reset per minute -
#: so a refusal costs seconds, not a day.
DEFAULT_ORDER = ("groq", "cerebras", "gemini", "nvidia", "openrouter", "mistral")


def configured_order() -> list:
    raw = os.environ.get("SDR_LLM_PROVIDERS", "")
    requested = [key.strip() for key in raw.split(",") if key.strip()]
    return [key for key in (requested or DEFAULT_ORDER) if key in PROVIDERS]


def is_configured(key: str) -> bool:
    provider = PROVIDERS.get(key)
    return bool(provider and os.environ.get(provider["api_key_env"]))


def model_for(key: str) -> str:
    provider = PROVIDERS[key]
    return os.environ.get(provider["model_env"], provider["default_model"])


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
            "priority": order.index(key) if key in order else None,
        }
        for key in PROVIDERS
    ]


def build_client(key: str):
    """An AsyncOpenAI client pointed at this provider.

    Constructed per call rather than cached, matching how the host app's
    `routers/ai.py` already does it - a cached client would hold a stale key
    after rotation.
    """
    from openai import AsyncOpenAI

    provider = PROVIDERS[key]
    api_key = os.environ.get(provider["api_key_env"])
    if not api_key:
        raise LookupError(f"{provider['label']} has no API key ({provider['api_key_env']})")
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
