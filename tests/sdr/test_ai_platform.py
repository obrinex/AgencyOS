"""The platform AI layer: free-provider chain, categories, and the catalogue.

Two things under test:

1. **The fallback chain.** Free tiers rate-limit constantly; a chain that does
   not actually fall through on a 429 is just one provider with extra steps.
2. **The catalogue is platform-wide.** A monitor that only lists the newest
   module is a module page, not a monitor - so the host app's pre-existing AI
   features must appear too.
"""

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "sdr_test")

import ai_platform  # noqa: E402
from sdr.agents.base import providers  # noqa: E402

ALL_KEYS = [p["api_key_env"] for p in providers.PROVIDERS.values()]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ALL_KEYS + ["SDR_LLM_PROVIDERS"]:
        monkeypatch.delenv(key, raising=False)


# --- Provider registry --------------------------------------------------------

def test_every_provider_is_openai_protocol_compatible():
    """One client library covers all of them - that is the whole design."""
    for key, provider in providers.PROVIDERS.items():
        assert provider["base_url"].startswith("https://"), key
        assert provider["api_key_env"], key
        assert provider["default_model"], key


def test_nothing_is_configured_without_keys():
    assert providers.available() == []
    assert providers.chain() == []


def test_a_provider_becomes_available_when_its_key_is_set(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    assert providers.available() == ["groq"]


def test_the_default_order_puts_the_fastest_first():
    """Groq and Cerebras lead because their limits reset per minute - a
    refusal there costs seconds, not a day."""
    assert providers.DEFAULT_ORDER[0] == "groq"
    assert "cerebras" in providers.DEFAULT_ORDER[:2]


def test_the_order_is_configurable(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "a")
    monkeypatch.setenv("GEMINI_API_KEY", "b")
    monkeypatch.setenv("SDR_LLM_PROVIDERS", "gemini,groq")
    assert providers.available() == ["gemini", "groq"]


def test_an_unknown_provider_in_the_order_is_ignored(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "a")
    monkeypatch.setenv("SDR_LLM_PROVIDERS", "nonsense,groq")
    assert providers.available() == ["groq"]


def test_models_are_overridable(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "llama-3.1-8b-instant")
    assert providers.model_for("groq") == "llama-3.1-8b-instant"


def test_describe_shows_unconfigured_providers_too():
    """Showing what is missing is how someone discovers a free key they could add."""
    described = providers.describe()
    assert len(described) == len(providers.PROVIDERS)
    assert all(entry["configured"] is False for entry in described)
    assert all(entry["free_note"] for entry in described)


def test_it_falls_back_to_the_hosts_existing_nvidia_setup(monkeypatch):
    """Strict superset of the previous behaviour - no key means no change."""
    monkeypatch.setenv("NVIDIA_API_KEY", "existing")
    chain = providers.chain()
    assert [key for key, _, _ in chain] == ["nvidia"]


# --- Fallback behaviour -------------------------------------------------------

@pytest.mark.parametrize("message", [
    "429 Too Many Requests", "rate limit exceeded", "quota exhausted",
    "Service is overloaded", "insufficient credits",
])
def test_rate_limit_errors_are_recognised(message):
    from sdr.agents.base.llm import _is_rate_limit
    assert _is_rate_limit(Exception(message))


def test_other_errors_are_not_treated_as_rate_limits():
    """Retrying a malformed request against another vendor just wastes a call."""
    from sdr.agents.base.llm import _is_rate_limit
    assert not _is_rate_limit(Exception("invalid model name"))
    assert not _is_rate_limit(Exception("401 unauthorized"))


@pytest.mark.asyncio
async def test_a_rate_limited_provider_falls_through_to_the_next(monkeypatch):
    from sdr.agents.base import llm
    from sdr.agents.base.cost import CostTracker

    calls = []

    class _Response:
        class _Choice:
            class _Message:
                content = '{"ok": true}'
            message = _Message()
        choices = [_Choice()]
        usage = type("U", (), {"prompt_tokens": 10, "completion_tokens": 5})()

    def make_client(name, fail):
        class _Client:
            class chat:
                class completions:
                    @staticmethod
                    async def create(**kwargs):
                        calls.append(name)
                        if fail:
                            raise Exception("429 rate limit exceeded")
                        return _Response()
        return _Client()

    monkeypatch.setattr(llm.provider_registry, "chain", lambda: [
        ("groq", lambda: make_client("groq", True), "m1"),
        ("gemini", lambda: make_client("gemini", False), "m2"),
    ])

    parsed, _ = await llm.complete_json(
        system="s", user="u", tracker=CostTracker(1.0)
    )
    assert parsed == {"ok": True}
    assert calls == ["groq", "gemini"]  # fell through, in order


@pytest.mark.asyncio
async def test_exhausting_every_provider_reports_all_of_them(monkeypatch):
    from sdr.agents.base import llm
    from sdr.agents.base.cost import CostTracker
    from sdr.errors import ProviderError

    def make_client(name):
        class _Client:
            class chat:
                class completions:
                    @staticmethod
                    async def create(**kwargs):
                        raise Exception(f"429 rate limit on {name}")
        return _Client()

    monkeypatch.setattr(llm.provider_registry, "chain", lambda: [
        ("groq", lambda: make_client("groq"), "m"),
        ("gemini", lambda: make_client("gemini"), "m"),
    ])

    with pytest.raises(ProviderError) as exc:
        await llm.complete_json(system="s", user="u", tracker=CostTracker(1.0))
    assert "groq" in str(exc.value) and "gemini" in str(exc.value)


@pytest.mark.asyncio
async def test_no_provider_configured_raises_a_clear_error(monkeypatch):
    from sdr.agents.base import llm
    from sdr.agents.base.cost import CostTracker
    from sdr.agents.base.llm import LLMNotConfiguredError

    monkeypatch.setattr(llm.provider_registry, "chain", lambda: [])
    with pytest.raises(LLMNotConfiguredError) as exc:
        await llm.complete_json(system="s", user="u", tracker=CostTracker(1.0))
    assert "GROQ_API_KEY" in str(exc.value)


# --- Catalogue ----------------------------------------------------------------

def test_the_catalogue_covers_agents_and_the_hosts_own_ai_features():
    """The point of the whole exercise: this is a platform monitor, not an
    SDR page."""
    keys = {entry["key"] for entry in ai_platform.catalogue()}
    assert "lead_enrichment" in keys        # an SDR agent
    assert "crm_assistant" in keys          # the host app's chat assistant
    assert "proposal_generator" in keys     # the host app's proposal writer
    assert "meeting_summarizer" in keys     # the host app's meeting summariser


def test_capabilities_span_more_than_one_use_case():
    categories = {entry["category"] for entry in ai_platform.catalogue()}
    assert len(categories) >= 3
    assert "sales" in categories
    assert "content" in categories


def test_every_capability_declares_a_known_category():
    for entry in ai_platform.catalogue():
        assert entry["category"] in ai_platform.CATEGORIES, entry["key"]


def test_agents_and_assistants_are_distinguishable():
    kinds = {entry["key"]: entry["kind"] for entry in ai_platform.catalogue()}
    assert kinds["lead_enrichment"] == "agent"
    assert kinds["crm_assistant"] == "assistant"


def test_grouping_drops_empty_categories():
    groups = ai_platform.grouped_catalogue()
    assert groups
    assert all(group["items"] for group in groups)


def test_every_capability_has_a_description_and_surface():
    """Both are shown in the monitor; a blank one is a broken row."""
    for entry in ai_platform.catalogue():
        assert entry["description"], entry["key"]
        assert entry.get("surface"), entry["key"]


# --- Assistant run recording --------------------------------------------------

@pytest_asyncio.fixture
async def db(monkeypatch):
    from mongomock_motor import AsyncMongoMockClient

    client = AsyncMongoMockClient()
    database = client["sdr_test"]

    import database as database_module
    monkeypatch.setattr(database_module, "db", database)
    from sdr.repositories import agent_runs, base
    for module in (agent_runs, base):
        monkeypatch.setattr(module, "db", database)
    return database


@pytest.mark.asyncio
async def test_an_assistant_invocation_is_recorded(db):
    from sdr.repositories import agent_runs

    async with ai_platform.record_assistant("email_generator", user_id="u1") as run:
        run.tokens(120, 60)
        run.used(model="llama-3.3", provider="groq")

    runs = await agent_runs.list_runs(agent_key="email_generator")
    assert len(runs["items"]) == 1
    row = runs["items"][0]
    assert row["status"] == "succeeded"
    assert row["input_tokens"] == 120
    assert row["provider_used"] == "groq"
    assert row["cost_usd_estimated"] > 0


@pytest.mark.asyncio
async def test_a_failing_assistant_is_recorded_and_still_raises(db):
    from sdr.repositories import agent_runs

    with pytest.raises(RuntimeError):
        async with ai_platform.record_assistant("proposal_generator") as run:
            run.tokens(10, 0)
            raise RuntimeError("provider exploded")

    runs = await agent_runs.list_runs(agent_key="proposal_generator")
    assert runs["items"][0]["status"] == "failed"
    assert "provider exploded" in runs["items"][0]["error_message"]


@pytest.mark.asyncio
async def test_recording_failure_never_breaks_the_feature(db, monkeypatch):
    """Monitoring must not be able to turn a working AI feature into a 500."""
    from sdr.repositories import agent_runs

    async def explode(*args, **kwargs):
        raise RuntimeError("database is down")

    monkeypatch.setattr(agent_runs, "start_run", explode)
    monkeypatch.setattr(agent_runs, "finish_run", explode)

    async with ai_platform.record_assistant("crm_assistant") as run:
        run.tokens(5, 5)
    # Reaching here at all is the assertion.
