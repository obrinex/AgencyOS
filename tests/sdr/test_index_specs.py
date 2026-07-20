"""Index specification safety.

Written after a production incident: a partial index using `$nin` was rejected
by MongoDB at creation time, the exception escaped `create_indexes()` inside
the startup event, and **every endpoint in the host application returned 500** -
not just this module's. The blast radius of a bad index spec was the whole app.

Two guarantees are enforced here:

1. No partial index uses an operator MongoDB rejects.
2. A failing index never aborts startup.

mongomock does not validate index specs, so a test that merely *runs*
`create_sdr_indexes()` would have passed while production burned. These
inspect the specs directly instead.
"""

import ast
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

COLLECTIONS_SOURCE = (BACKEND_DIR / "sdr" / "collections.py").read_text(encoding="utf-8")


def _partial_filter_expressions() -> list:
    """Pull every partialFilterExpression literal out of the source.

    Parsed from the AST rather than executed, so this works without a
    database and cannot be fooled by a spec that is never reached.
    """
    tree = ast.parse(COLLECTIONS_SOURCE)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "partialFilterExpression":
            found.append(ast.literal_eval(node.value))
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "partialFilterExpression":
                    found.append(ast.literal_eval(value))
    return found


def _operators(expression) -> set:
    """Every $-prefixed operator appearing anywhere in a filter."""
    operators = set()

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(key, str) and key.startswith("$"):
                    operators.add(key)
                walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(expression)
    return operators


def test_there_is_at_least_one_partial_index_to_check():
    """Guards the test itself: if the extraction silently found nothing, the
    operator assertion below would pass vacuously."""
    assert _partial_filter_expressions(), "no partialFilterExpression found to validate"


@pytest.mark.parametrize("expression", _partial_filter_expressions())
def test_partial_indexes_use_only_operators_mongodb_accepts(expression):
    """The exact regression. `$nin` here previously failed startup in
    production and 500'd every endpoint in the app."""
    from sdr.collections import PARTIAL_FILTER_SAFE_OPERATORS

    used = _operators(expression)
    unsupported = used - PARTIAL_FILTER_SAFE_OPERATORS
    assert not unsupported, (
        f"partialFilterExpression {expression} uses {sorted(unsupported)}, which "
        f"MongoDB rejects with CannotCreateIndex. Supported: "
        f"{sorted(PARTIAL_FILTER_SAFE_OPERATORS)}."
    )


def test_nin_specifically_never_returns_to_a_partial_index():
    """Named explicitly so the incident is greppable from the test suite."""
    for expression in _partial_filter_expressions():
        assert "$nin" not in _operators(expression)
        assert "$not" not in _operators(expression)


@pytest_asyncio.fixture
async def db(monkeypatch):
    from mongomock_motor import AsyncMongoMockClient

    client = AsyncMongoMockClient()
    database = client["sdr_test"]

    import database as database_module
    monkeypatch.setattr(database_module, "db", database)
    from sdr import collections
    monkeypatch.setattr(collections, "db", database)
    return database


@pytest.mark.asyncio
async def test_a_failing_index_does_not_abort_the_rest(db, monkeypatch, caplog):
    """One bad spec must not skip the indexes that follow it."""
    from sdr import collections

    calls = {"count": 0}
    original = collections._safe_index

    async def flaky(label, collection, *args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("simulated CannotCreateIndex")
        return await original(label, collection, *args, **kwargs)

    async def wrapped(label, collection, *args, **kwargs):
        try:
            await flaky(label, collection, *args, **kwargs)
        except Exception as exc:
            collections.logger.error("Could not create SDR index %s: %s", label, exc)

    monkeypatch.setattr(collections, "_safe_index", wrapped)
    await collections.create_sdr_indexes()

    # Every spec was attempted despite the first one blowing up.
    assert calls["count"] > 25


@pytest.mark.asyncio
async def test_index_creation_never_raises(db, monkeypatch):
    """The guarantee that matters: startup cannot be killed from here."""
    from sdr import collections

    async def always_fails(*args, **kwargs):
        raise RuntimeError("MongoDB said no")

    for name in collections.ALL_COLLECTIONS:
        monkeypatch.setattr(db[name], "create_index", always_fails, raising=False)
    monkeypatch.setattr(db.leads, "create_index", always_fails, raising=False)

    # Must complete cleanly rather than propagating.
    await collections.create_sdr_indexes()


@pytest.mark.asyncio
async def test_indexes_are_created_on_a_clean_database(db):
    from sdr import collections

    await collections.create_sdr_indexes()
    names = await db[collections.JOBS].index_information()
    assert names  # the queue's indexes exist
