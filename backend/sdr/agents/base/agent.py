"""The agent contract and its runner.

Written once. Every agent subclasses `Agent` and implements `execute()`;
everything that must not be skipped - run recording, output validation, cost
ceilings, timeouts, guardrail flags, correlation - lives in `run()` and is not
the agent author's responsibility.

That split is deliberate. The spec lists 21 agents. If each one had to
remember to open an `agent_runs` row and validate its own output, some of them
would not, and the ones that did not would be the ones that failed silently.
"""

import asyncio
import logging
import time

from pydantic import BaseModel, ValidationError as PydanticValidationError

from sdr.agents.base.cost import CostTracker
from sdr.agents.base.llm import complete_json
from sdr.errors import (
    AgentTimeoutError, CostCeilingError, SDRError, ValidationError,
)
from sdr.repositories import agent_runs as runs_repo

logger = logging.getLogger(__name__)


class AgentContext:
    """Everything an agent needs about the world it is running in."""

    def __init__(self, *, user: dict | None = None, correlation_id: str | None = None,
                 parent_run_id: str | None = None, trigger: str = "manual",
                 attempt: int = 1, max_attempts: int = 1):
        self.user = user or {}
        self.correlation_id = correlation_id
        self.parent_run_id = parent_run_id
        self.trigger = trigger
        self.attempt = attempt
        self.max_attempts = max_attempts
        self.run_id: str | None = None
        self.tracker: CostTracker | None = None
        #: Which provider actually served the call. Set by the LLM layer,
        #: which may fall back across the free-tier chain, so the model on the
        #: run is the one used rather than the one requested.
        self.provider_used: str | None = None
        self.model_used: str | None = None
        #: Guardrail observations worth persisting on the run - injection
        #: attempts, ungrounded claims, repaired outputs.
        self.flags: list = []

    def flag(self, kind: str, detail=None) -> None:
        self.flags.append({"kind": kind, "detail": detail})


class AgentResult:
    def __init__(self, output, *, run_id: str, cost: dict, flags: list):
        self.output = output
        self.run_id = run_id
        self.cost = cost
        self.flags = flags

    def as_dict(self) -> dict:
        return {
            "output": self.output,
            "run_id": self.run_id,
            "cost": self.cost,
            "flags": self.flags,
        }


class Agent:
    """Base class. Subclasses set the class attributes and implement execute()."""

    key: str = ""
    version: str = "1.0.0"
    description: str = ""
    #: What this agent is used *for*, independent of which module
    #: implements it. Drives grouping in the platform AI monitor.
    category: str = "insight"
    #: Where in the app it shows up, for the monitor's "surface" column.
    surface: str = ""
    #: Pydantic models. The output schema is enforced - unvalidated LLM output
    #: never reaches the database.
    input_schema: type[BaseModel] | None = None
    output_schema: type[BaseModel] | None = None
    model: str | None = None
    max_tokens: int = 1200
    temperature: float = 0.2
    cost_ceiling_usd: float = 0.05
    timeout_ms: int = 45_000
    #: Which queue this agent's jobs run on; drives the retry budget.
    queue: str = "default"

    async def execute(self, payload: dict, ctx: AgentContext):
        """The agent's actual work. Subclass responsibility."""
        raise NotImplementedError

    # -- the runner ------------------------------------------------------------

    async def run(self, payload: dict, ctx: AgentContext | None = None) -> AgentResult:
        ctx = ctx or AgentContext()
        ctx.tracker = CostTracker(self.cost_ceiling_usd)

        entity_type, entity_id = self._entity(payload)
        ctx.run_id = await runs_repo.start_run(
            agent_key=self.key,
            version=self.version,
            trigger=ctx.trigger,
            entity_type=entity_type,
            entity_id=entity_id,
            correlation_id=ctx.correlation_id,
            parent_run_id=ctx.parent_run_id,
            attempt=ctx.attempt,
            max_attempts=ctx.max_attempts,
            payload=payload,
        )
        ctx.correlation_id = ctx.correlation_id or ctx.run_id

        started = time.monotonic()
        try:
            if self.input_schema:
                try:
                    self.input_schema.model_validate(payload)
                except PydanticValidationError as exc:
                    raise ValidationError(f"Invalid input for {self.key}: {exc}")

            output = await asyncio.wait_for(
                self.execute(payload, ctx), timeout=self.timeout_ms / 1000
            )

            duration_ms = int((time.monotonic() - started) * 1000)
            await runs_repo.finish_run(
                ctx.run_id, status="succeeded", output=output,
                model_used=ctx.model_used or self.model,
                provider_used=ctx.provider_used,
                cost=ctx.tracker.snapshot(),
                duration_ms=duration_ms, guardrail_flags=ctx.flags,
            )
            return AgentResult(
                output, run_id=ctx.run_id,
                cost=ctx.tracker.snapshot(), flags=ctx.flags,
            )

        except asyncio.TimeoutError:
            await self._fail(ctx, started, AgentTimeoutError(
                f"{self.key} exceeded its {self.timeout_ms}ms timeout."
            ))
            raise AgentTimeoutError(f"{self.key} exceeded its {self.timeout_ms}ms timeout.")

        except SDRError as exc:
            await self._fail(ctx, started, exc)
            raise

        except Exception as exc:
            logger.exception("Agent %s crashed", self.key)
            await self._fail(ctx, started, exc)
            raise

    async def _fail(self, ctx: AgentContext, started: float, exc: Exception) -> None:
        await runs_repo.finish_run(
            ctx.run_id,
            status="failed",
            model_used=ctx.model_used or self.model,
            provider_used=ctx.provider_used,
            cost=ctx.tracker.snapshot() if ctx.tracker else None,
            duration_ms=int((time.monotonic() - started) * 1000),
            error_type=type(exc).__name__,
            error_message=str(exc),
            guardrail_flags=ctx.flags,
        )

    def _entity(self, payload: dict) -> tuple:
        """Best guess at what this run is about, for the run inspector."""
        for key, kind in (("lead_id", "lead"), ("company_id", "company"),
                          ("contact_id", "contact")):
            if payload.get(key):
                return kind, str(payload[key])
        return None, None

    # -- helper for LLM-backed agents -----------------------------------------

    async def complete_validated(self, *, system: str, user: str, ctx: AgentContext,
                                 schema: type[BaseModel] | None = None):
        """One JSON completion, validated, with a single repair attempt.

        The repair pass appends the validation error and asks again. One
        attempt, not a loop: a model that cannot produce the shape twice is
        not going to on the fifth try, and each attempt costs real money.
        """
        schema = schema or self.output_schema
        if not schema:
            raise ValidationError(f"{self.key} has no output schema to validate against.")

        try:
            parsed, _raw = await complete_json(
                system=system, user=user, tracker=ctx.tracker,
                temperature=self.temperature, max_tokens=self.max_tokens,
                ctx=ctx,
            )
            return schema.model_validate(parsed)
        except CostCeilingError:
            raise
        except (PydanticValidationError, ValueError) as exc:
            # Python unbinds `exc` at the end of the except block, so the
            # message has to be captured here to be used below.
            first_error = str(exc)[:500]
            ctx.flag("output_repair_attempted", first_error[:300])
            logger.warning("%s produced invalid output, repairing: %s", self.key, first_error)

        repair_user = (
            f"{user}\n\n"
            f"Your previous response was rejected: {first_error}\n"
            f"Respond again with ONLY a valid JSON object matching the required "
            f"schema. No prose, no markdown fences."
        )
        try:
            parsed, _ = await complete_json(
                system=system, user=repair_user, tracker=ctx.tracker,
                temperature=0.0,  # deterministic on the retry
                max_tokens=self.max_tokens, ctx=ctx,
            )
            return schema.model_validate(parsed)
        except CostCeilingError:
            raise
        except (PydanticValidationError, ValueError) as exc:
            ctx.flag("output_repair_failed", str(exc)[:300])
            raise ValidationError(
                f"{self.key} could not produce output matching its schema.",
                detail={"error": str(exc)[:500]},
            )
