"""Typed contract for the enrichment agent.

The output schema is the thing standing between a model's imagination and the
companies collection. Every field is optional because partial enrichment is
the normal outcome - a model that cannot determine headcount should omit it,
not guess. `confidence` and `evidence` exist so a low-quality inference can be
kept out of the record downstream.
"""

from typing import Optional

from pydantic import BaseModel, Field


class EnrichmentInput(BaseModel):
    company_id: str
    #: Skip a company enriched more recently than this many days ago.
    freshness_days: int = 30
    force: bool = False


class EnrichedFields(BaseModel):
    """What the model may infer. Deliberately a narrow surface.

    Contact details are absent on purpose: a hallucinated email address gets
    sent to a real stranger, so emails and phone numbers may only come from a
    provider or a verified source, never from a language model.
    """

    industry: Optional[str] = Field(
        default=None, description="Normalised industry key"
    )
    sub_industry: Optional[str] = None
    description: Optional[str] = Field(
        default=None, max_length=600,
        description="One or two sentences on what the business actually does",
    )
    employee_count_estimate: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    founded_year: Optional[int] = Field(default=None, ge=1800, le=2100)
    tech_stack: list[str] = Field(default_factory=list, max_length=25)
    #: Free-text observations that later agents can use as pitch angles.
    buying_signals: list[str] = Field(default_factory=list, max_length=10)


class EnrichmentOutput(BaseModel):
    fields: EnrichedFields
    confidence: float = Field(ge=0.0, le=1.0)
    #: Verbatim snippets the inference rests on. The grounding guardrail
    #: checks these against stored data.
    evidence: list[str] = Field(default_factory=list, max_length=10)
    reasoning: Optional[str] = Field(default=None, max_length=800)
