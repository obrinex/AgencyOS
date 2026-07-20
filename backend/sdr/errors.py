"""Typed errors for the SDR module.

Every error carries `retryable`, which the job runner consults to decide
between re-queueing with backoff and dead-lettering immediately. Raising a
bare Exception from a job handler is treated as retryable=True, so prefer
these when the distinction matters.
"""


class SDRError(Exception):
    """Base for everything this module raises."""

    retryable = False
    status_code = 500

    def __init__(self, message: str, *, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class ValidationError(SDRError):
    """Input failed a business rule. Retrying with the same input cannot help."""

    retryable = False
    status_code = 400


class NotFoundError(SDRError):
    retryable = False
    status_code = 404


class ForbiddenError(SDRError):
    retryable = False
    status_code = 403


class IllegalTransitionError(ValidationError):
    """A lead stage move that the pipeline state machine forbids."""

    def __init__(self, from_stage: str, to_stage: str):
        super().__init__(
            f"Cannot move a lead from '{from_stage}' to '{to_stage}'.",
            detail={"from_stage": from_stage, "to_stage": to_stage},
        )
        self.from_stage = from_stage
        self.to_stage = to_stage


class ProviderError(SDRError):
    """A third-party API failed. Usually worth another attempt."""

    retryable = True
    status_code = 502


class RateLimitError(ProviderError):
    """Provider asked us to slow down. Retryable, but back off harder."""

    retryable = True
    status_code = 429


class QuotaExceededError(ProviderError):
    """Provider quota is spent. Retrying before the reset window is pointless."""

    retryable = False
    status_code = 402


class UnsupportedCapabilityError(SDRError):
    """The provider genuinely cannot do this - do not fake it, surface it.

    Used when a compliant API path does not exist (e.g. LinkedIn automation
    that would require ToS-violating scraping). The UI shows this honestly
    rather than presenting a broken feature.
    """

    retryable = False
    status_code = 501


class ComplianceBlockError(SDRError):
    """A send was refused by the pre-flight compliance check.

    Never retryable: suppression, opt-out and DNC decisions are permanent
    until a human changes the underlying record.
    """

    retryable = False
    status_code = 409


class DraftRejectedError(SDRError):
    """A generated draft failed grounding or copy checks.

    Retryable: a fresh generation may pass. The personalization queue caps
    attempts at two, because each retry is a paid LLM call and a draft that
    failed twice needs a human reading the dead-letter, not a fifth invoice.
    """

    retryable = True
    status_code = 422


class CostCeilingError(SDRError):
    """An agent run or an org's daily spend hit its configured cap."""

    retryable = False
    status_code = 429


class AgentTimeoutError(SDRError):
    retryable = True
    status_code = 504
