"""The inbound reply classifier.

One job: decide what a reply *is*. It does not act on that decision - the
service layer does - because the wiring (stop, suppress, defer) has to run
identically whether the category came from this agent or from deterministic
header detection, and only one of those two paths involves a model.

Deliberately cheap and cold: a low ceiling and temperature 0, because this is
a labelling task with a closed answer set. Nothing here is creative.
"""

import logging

from pydantic import BaseModel, Field

from sdr.agents.base.agent import Agent, AgentContext
from sdr.agents.inbound.prompts import PROMPT_VERSION, SYSTEM, build_user_prompt
from sdr.domain import inbound as inbound_domain
from sdr.errors import ValidationError

logger = logging.getLogger(__name__)


class ClassificationOutput(BaseModel):
    category: str = Field(description="One of the eight inbound categories")
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(default="", max_length=400)


class InboundClassifierAgent(Agent):
    key = "inbound_classifier"
    version = f"1.0.0+prompt{PROMPT_VERSION}"
    description = "Classifies one inbound reply into a closed category set."
    category = "sales"
    surface = "AI SDR → Inbox"
    output_schema = ClassificationOutput
    queue = "personalization"
    cost_ceiling_usd = 0.01
    timeout_ms = 30_000
    max_tokens = 300
    temperature = 0.0   # a labelling task; there is nothing to be creative about

    async def execute(self, payload: dict, ctx: AgentContext) -> dict:
        reply_body = payload.get("reply_body")
        if reply_body is None:
            raise ValidationError("reply_body is required")

        result = await self.complete_validated(
            system=SYSTEM,
            user=build_user_prompt(
                sent_subject=payload.get("sent_subject") or "",
                sent_body=payload.get("sent_body") or "",
                reply_subject=payload.get("reply_subject") or "",
                reply_body=reply_body,
                from_email=payload.get("from_email") or "",
            ),
            ctx=ctx,
        )

        category = (result.category or "").strip().lower()
        if category not in inbound_domain.CATEGORIES:
            # The schema cannot enforce the closed set without brittle enums
            # across model providers, so it is enforced here. An unrecognised
            # label is treated as an unknown human reply rather than guessed
            # at: it goes to a person, and it does not stop anything.
            ctx.flag("unknown_inbound_category", category)
            logger.warning("Classifier returned unknown category %r", category)
            return {"category": "objection", "confidence": 0.0,
                    "reasoning": f"Unrecognised label {category!r}; routed for review.",
                    "needs_human": True}

        return {
            "category": category,
            "confidence": float(result.confidence),
            "reasoning": result.reasoning,
            # Low confidence never acts silently. The threshold is the same
            # one the prompt tells the model about.
            "needs_human": float(result.confidence) < 0.6,
        }
