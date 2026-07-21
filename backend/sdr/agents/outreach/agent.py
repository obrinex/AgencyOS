"""The personalization and send agents.

Split into two agents rather than one because they fail differently. A
personalization failure costs a retry token; a send failure can cost a real
email to a real person, so the send agent is built around one question: *can
this path ever dispatch the same message twice?* The answers, in order:

- The message row is claimed `approved -> sending` atomically before any
  provider call. A concurrent job loses the claim and does nothing.
- A retry that finds a message already in `sending` does NOT call the
  provider - a previous attempt crashed mid-call and the outcome is unknown,
  so the message parks in `needs_review` for a human. Uncomfortable and
  correct: the alternative is guessing, and a wrong guess is a duplicate
  email or a silently lost one.
- Provider refusals we can *classify* as not-sent (rate limit, quota) release
  their claims and go back to `approved`. Anything ambiguous (timeouts,
  unknown errors) is treated as possibly-sent: `needs_review`, claim kept.

Stop conditions are re-evaluated at both stages, because the world moves
between draft and dispatch: a reply, an unsubscribe or a closed deal that
arrives after approval must still stop the send.
"""

import logging
import os

from pydantic import BaseModel, Field

from database import db, now_iso, serialize_doc
from sdr.agents.base.agent import Agent, AgentContext
from sdr.agents.base.guardrails import check_grounding, collect_grounding_facts
from sdr.agents.outreach.prompts import PROMPT_VERSION, SYSTEM, build_user_prompt
from sdr.config.countries import get_country, get_holidays, is_cold_outreach_permitted
from sdr.domain import copy_checks, send_window
from sdr.domain import email_threading as threading_domain
from sdr.domain import sequence as sequence_domain
from sdr.errors import DraftRejectedError, NotFoundError, ProviderError, ValidationError
from sdr.providers import email_resend
from sdr.repositories import audits as audits_repo
from sdr.repositories.base import object_id
from sdr.repositories import campaigns as campaigns_repo
from sdr.repositories import companies as companies_repo
from sdr.repositories import identities as identities_repo
from sdr.repositories import settings as settings_repo
from sdr.repositories import suppression as suppression_repo
from sdr.services import preflight as preflight_service

logger = logging.getLogger(__name__)


class DraftOutput(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)
    cited_facts: list[str] = Field(default_factory=list, max_length=10)


async def _load_context(enrollment_id: str) -> tuple:
    enrollment = await campaigns_repo.get_enrollment(enrollment_id)
    campaign = await campaigns_repo.get_campaign(enrollment["campaign_id"])
    lead_doc = await db.leads.find_one(
        {"_id": object_id(
            enrollment["lead_id"], "lead id")}
    )
    if not lead_doc:
        raise NotFoundError("Lead not found for enrollment")
    lead = serialize_doc(lead_doc)

    company, signals = {}, []
    if lead.get("sdr_company_id"):
        try:
            company = await companies_repo.get_company(lead["sdr_company_id"])
            signals = await audits_repo.signals_for(lead["sdr_company_id"])
        except NotFoundError:
            company = {}
    return enrollment, campaign, lead, company, signals


async def _check_stop(enrollment: dict, campaign: dict, lead: dict) -> str | None:
    hit = await suppression_repo.is_suppressed(email=lead.get("email"))
    reason = sequence_domain.evaluate_stop(
        lead, suppressed=bool(hit), campaign_status=campaign["status"]
    )
    if reason:
        await campaigns_repo.stop_enrollment(enrollment["id"], reason)
    return reason


async def _sender_name(campaign: dict) -> str:
    """Sign-off name: the campaign creator, falling back to the brand."""
    creator_id = campaign.get("created_by")
    if creator_id:
        from sdr.repositories.base import object_id
        try:
            user = await db.users.find_one({"_id": object_id(creator_id, "user id")})
            if user and user.get("name"):
                return str(user["name"]).split()[0]
        except ValidationError:
            pass
    company = await db.company_settings.find_one({"key": "main"}) or {}
    return company.get("company_name") or "The team"


class PersonalizationAgent(Agent):
    key = "outreach_personalization"
    version = f"1.0.0+prompt{PROMPT_VERSION}"
    description = "Drafts one grounded, checked sequence email for one lead."
    category = "sales"
    surface = "AI SDR → Outreach"
    output_schema = DraftOutput
    queue = "personalization"
    cost_ceiling_usd = 0.03
    timeout_ms = 45_000
    max_tokens = 700
    temperature = 0.5   # copy wants some voice; facts are guarded downstream

    async def execute(self, payload: dict, ctx: AgentContext) -> dict:
        enrollment_id = payload.get("enrollment_id")
        if not enrollment_id:
            raise ValidationError("enrollment_id is required")

        enrollment, campaign, lead, company, signals = await _load_context(enrollment_id)

        if enrollment["status"] != sequence_domain.ACTIVE:
            return {"skipped": True, "reason": f"enrollment is {enrollment['status']}"}
        if sequence_domain.is_on_hold(campaign["status"]):
            return {"skipped": True, "reason": "campaign is paused"}

        stop = await _check_stop(enrollment, campaign, lead)
        if stop:
            return {"stopped": True, "reason": stop, "enrollment_id": enrollment_id}

        settings = await settings_repo.get_settings()

        # Compliance is decided before spending a token: a lead we may not
        # lawfully email gets stopped here, not discovered at send time.
        country_code = company.get("country_code")
        permitted, why = is_cold_outreach_permitted(
            country_code, "email",
            allow_unlisted=settings.get("allow_unlisted_countries", False),
        )
        if not permitted:
            await campaigns_repo.stop_enrollment(enrollment_id, "compliance")
            ctx.flag("compliance_stop", why)
            return {"stopped": True, "reason": "compliance", "detail": why}

        step_index = enrollment["current_step"]
        steps = campaign["sequence"]
        if step_index >= len(steps):
            return {"skipped": True, "reason": "sequence already finished"}

        existing = await campaigns_repo.message_for_step(enrollment_id, step_index)
        if existing:
            return {"skipped": True, "reason": "draft already exists",
                    "message_id": existing["id"]}

        draft = await self.complete_validated(
            system=SYSTEM,
            user=build_user_prompt(
                step=steps[step_index], step_number=step_index + 1,
                total_steps=len(steps), lead=lead, company=company,
                signals=signals, brand_voice=settings.get("brand_voice") or "",
                do_not_say=settings.get("do_not_say") or [],
                sender_name=await _sender_name(campaign),
            ),
            ctx=ctx,
        )

        # Deterministic enforcement, after the model has been *asked* nicely.
        problems = copy_checks.check_copy(
            subject=draft.subject, body=draft.body,
            do_not_say=settings.get("do_not_say"),
        )
        facts = collect_grounding_facts(company, lead, {"signals": signals})
        grounded, unsupported = check_grounding(draft.cited_facts, facts)
        if not grounded:
            problems.append(f"Ungrounded claims: {'; '.join(unsupported[:3])}")
        if problems:
            ctx.flag("draft_rejected", problems[:5])
            raise DraftRejectedError(
                "The draft failed pre-send checks: " + " | ".join(problems)
            )

        # Manual mode drafts wait for a human; auto mode schedules straight
        # into the recipient's next business-hours window.
        auto = campaign.get("approval_mode") == "auto"
        scheduled_for = None
        if auto:
            scheduled_for = send_window.schedule(
                now_iso(), get_country(country_code), seed=f"{enrollment_id}:{step_index}",
                holidays=get_holidays(country_code, int(now_iso()[:4])),
            ).isoformat()

        message = await campaigns_repo.create_message(
            campaign_id=campaign["id"], enrollment_id=enrollment_id,
            lead_id=lead["id"], step_index=step_index,
            to_email=lead["email"], country_code=country_code,
            subject=draft.subject.strip(), body=draft.body.strip(),
            cited_facts=draft.cited_facts,
            status="approved" if auto else "awaiting_approval",
            scheduled_for=scheduled_for,
            generation_meta={
                "prompt_version": PROMPT_VERSION,
                "provider": ctx.provider_used,
                "model": ctx.model_used,
                "step_goal": steps[step_index].get("goal"),
            },
        )
        return {
            "message_id": message["id"],
            "enrollment_id": enrollment_id,
            "step": step_index + 1,
            "status": message["status"],
            "duplicate": message.get("duplicate", False),
            "subject": draft.subject,
        }


def _build_footer_text(*, company_name: str, postal_address: str | None,
                       unsubscribe_url: str, country_code: str | None) -> tuple:
    """Plain-text legal footer. Returns (footer, missing_elements)."""
    _, missing = preflight_service.required_footer(
        country_code, company_name=company_name,
        postal_address=postal_address, unsubscribe_url=unsubscribe_url,
    )
    lines = ["--", company_name]
    if postal_address:
        lines.append(postal_address)
    lines.append(f"Unsubscribe (one click, permanent): {unsubscribe_url}")
    return "\n".join(lines), missing


class OutreachSendAgent(Agent):
    key = "outreach_send"
    version = "1.0.0"
    description = "Runs pre-flight and dispatches one approved message. Double-send-proof."
    category = "sales"
    surface = "AI SDR → Outreach"
    queue = "send"
    cost_ceiling_usd = 0.001   # no LLM; ceiling machinery still exercised
    timeout_ms = 30_000

    async def execute(self, payload: dict, ctx: AgentContext) -> dict:
        message_id = payload.get("message_id")
        if not message_id:
            raise ValidationError("message_id is required")

        message = await campaigns_repo.get_message(message_id)

        # A previous attempt crashed between claim and outcome. The provider
        # may or may not have the email. Nobody guesses.
        if message["status"] == "sending":
            await campaigns_repo.update_message(message_id, {
                "status": "needs_review",
                "error": "A previous send attempt did not record an outcome. "
                         "Check the provider dashboard before replaying.",
            })
            ctx.flag("ambiguous_send_outcome", message_id)
            raise ValidationError(  # non-retryable -> dead-letter, visibly
                "Send outcome unknown from a prior attempt; parked in needs_review."
            )

        if message["status"] != "approved":
            return {"skipped": True, "reason": f"message is {message['status']}"}

        enrollment = await campaigns_repo.get_enrollment(message["enrollment_id"])
        campaign = await campaigns_repo.get_campaign(message["campaign_id"])
        lead_doc = await db.leads.find_one(
            {"_id": object_id(
                message["lead_id"], "lead id")}
        )
        lead = serialize_doc(lead_doc) if lead_doc else {}

        # The world may have moved since approval.
        stop = await _check_stop(enrollment, campaign, lead)
        if stop:
            await campaigns_repo.update_message(message_id, {
                "status": "cancelled", "cancel_reason": stop,
            })
            return {"stopped": True, "reason": stop}
        if sequence_domain.is_on_hold(campaign["status"]):
            return {"held": True, "reason": "campaign is paused"}

        settings = await settings_repo.get_settings()

        result = await preflight_service.check(
            recipient_email=message["to_email"],
            country_code=message.get("country_code"),
            channel="email",
            lead_id=message["lead_id"],
        )

        if not result.allowed:
            return await self._handle_refusal(message, enrollment, result, ctx)

        identity = result.identity
        claimed = await campaigns_repo.claim_message_for_send(message_id)
        if not claimed:
            # Lost the race to a concurrent job; give the slots back.
            await preflight_service.release_claim(
                identity["identity"], message["to_email"]
            )
            return {"skipped": True, "reason": "claimed by a concurrent attempt"}

        # Footer and headers are applied at dispatch, against the approved
        # copy - the human approved the words, the law requires the frame.
        company_settings = await db.company_settings.find_one({"key": "main"}) or {}
        backend_url = (os.environ.get("BACKEND_URL") or "").rstrip("/")
        token = suppression_repo.unsubscribe_token(message["to_email"])
        unsubscribe_url = (
            f"{backend_url}/api/public/sdr/unsubscribe"
            f"?email={message['to_email']}&token={token}"
        )
        footer, missing = _build_footer_text(
            company_name=company_settings.get("company_name") or "Obrinex",
            postal_address=company_settings.get("address"),
            unsubscribe_url=unsubscribe_url,
            country_code=message.get("country_code"),
        )
        if missing:
            # A config gap, not a transient - retrying cannot conjure a
            # postal address. Released and parked, loudly.
            await preflight_service.release_claim(identity["identity"], message["to_email"])
            await campaigns_repo.update_message(message_id, {
                "status": "needs_review",
                "error": f"Legally required footer element(s) missing: {', '.join(missing)}. "
                         "Fill them in Settings → Company, then replay.",
            })
            raise ValidationError(f"Footer incomplete: {', '.join(missing)}")

        full_body = f"{message['body']}\n\n{footer}"
        headers = preflight_service.unsubscribe_headers(
            unsubscribe_url, mailto=identity["identity"]
        )

        # Threading identity. Minted here rather than at draft time because
        # the Message-ID's domain must match the sending identity, and
        # pre-flight only picks one at this point. Stored on the row in the
        # same write that records the send, so an inbound reply months later
        # can be matched to the message that provoked it. This is the one
        # thing here that cannot be retrofitted - a message sent without a
        # Message-ID we chose is permanently unmatchable.
        own_message_id = threading_domain.message_id_for(
            message_id, identity["identity"]
        )
        parent = await campaigns_repo.threading_ancestor(
            message["enrollment_id"], message["step_index"]
        )
        in_reply_to, references = threading_domain.chain(parent)
        headers.update(threading_domain.headers(
            own_message_id=own_message_id,
            in_reply_to=in_reply_to,
            references=references,
        ))
        threading_fields = {
            "email_message_id": own_message_id,
            "in_reply_to": in_reply_to,
            "references": references,
        }
        # None unless an address has been configured - see the note on
        # `reply_to_address` in the settings defaults.
        reply_to = settings.get("reply_to_address") or None

        # Simulate mode: the entire pipeline has now run - checks, claims,
        # footer - and stops one call short of the wire. Claims are returned
        # so rehearsals never consume real allowance or warm-up counters.
        if settings.get("send_mode") != "live":
            await preflight_service.release_claim(identity["identity"], message["to_email"])
            sent_at = now_iso()
            await campaigns_repo.update_message(message_id, {
                "status": "sent", "simulated": True, "sent_at": sent_at,
                "identity": identity["identity"],
                # Recorded so a rehearsal shows the exact headers that would
                # have gone out. `threading_ancestor` still refuses to thread
                # a real follow-up under a simulated parent.
                **threading_fields,
            })
            await campaigns_repo.bump_stat(message["campaign_id"], "sent")
            await campaigns_repo.advance_enrollment(
                message["enrollment_id"], sent_at=sent_at, steps=campaign["sequence"],
            )
            return {"sent": True, "simulated": True, "message_id": message_id,
                    "identity": identity["identity"]}

        try:
            outcome = await email_resend.send(
                from_identity=identity["identity"],
                from_label=identity.get("label"),
                to_email=message["to_email"],
                subject=message["subject"],
                text_body=full_body,
                headers=headers,
                idempotency_ref=f"sdr-msg-{message_id}",
                reply_to=reply_to,
            )
        except (ProviderError,) as exc:
            return await self._handle_provider_failure(
                message, identity, exc, ctx
            )

        sent_at = now_iso()
        await campaigns_repo.update_message(message_id, {
            "status": "sent", "sent_at": sent_at,
            "identity": identity["identity"],
            "provider_message_id": outcome["provider_message_id"],
            **threading_fields,
        })
        await campaigns_repo.bump_stat(message["campaign_id"], "sent")
        await campaigns_repo.advance_enrollment(
            message["enrollment_id"], sent_at=sent_at, steps=campaign["sequence"],
        )
        await identities_repo.record_outcome(identity["identity"], sent=1)

        return {"sent": True, "simulated": False, "message_id": message_id,
                "provider_message_id": outcome["provider_message_id"],
                "identity": identity["identity"]}

    async def _handle_refusal(self, message: dict, enrollment: dict,
                              result, ctx: AgentContext) -> dict:
        """Map a pre-flight refusal onto the message's fate."""
        code = result.code

        if code == "suppressed":
            await campaigns_repo.update_message(message["id"], {
                "status": "cancelled", "cancel_reason": "suppressed",
            })
            await campaigns_repo.stop_enrollment(enrollment["id"], "unsubscribed")
            return {"stopped": True, "reason": "suppressed"}

        if code == "compliance_blocked":
            await campaigns_repo.update_message(message["id"], {
                "status": "cancelled", "cancel_reason": result.reason,
            })
            await campaigns_repo.stop_enrollment(enrollment["id"], "compliance")
            return {"stopped": True, "reason": "compliance"}

        if code == "outside_send_window":
            # Not a failure - reschedule into the window pre-flight computed.
            await campaigns_repo.update_message(message["id"], {
                "status": "approved",
                "scheduled_for": result.as_dict()["scheduled_for"],
            })
            await db[campaigns_repo.MESSAGES].update_one(
                {"_id": object_id(
                    message["id"], "message id")},
                {"$inc": {"send_attempt": 1}},
            )
            return {"rescheduled": True, "scheduled_for": result.as_dict()["scheduled_for"]}

        # Caps, kill switch, no identity, DNS: temporary conditions. The
        # message stays approved and the next tick tries again; send_attempt
        # changes the job key so re-enqueueing works.
        await db[campaigns_repo.MESSAGES].update_one(
            {"_id": object_id(
                message["id"], "message id")},
            {"$inc": {"send_attempt": 1}},
        )
        ctx.flag("send_held", {"code": code, "reason": result.reason})
        return {"held": True, "code": code, "reason": result.reason}

    async def _handle_provider_failure(self, message: dict, identity: dict,
                                       exc: Exception, ctx: AgentContext) -> dict:
        """Classify a provider exception by what we *know* happened."""
        from sdr.errors import QuotaExceededError, RateLimitError

        if isinstance(exc, (RateLimitError, QuotaExceededError)):
            # A refusal is a definite not-sent: safe to release and retry.
            await preflight_service.release_claim(identity["identity"], message["to_email"])
            await campaigns_repo.update_message(message["id"], {"status": "approved"})
            await db[campaigns_repo.MESSAGES].update_one(
                {"_id": object_id(
                    message["id"], "message id")},
                {"$inc": {"send_attempt": 1}},
            )
            raise exc  # retryable; the run records the refusal

        # Anything else - timeout, connection reset, unknown 5xx - is
        # ambiguous: the provider may have the email. Claim kept, human asked.
        await campaigns_repo.update_message(message["id"], {
            "status": "needs_review",
            "error": f"Provider outcome unknown: {exc}. Check the Resend "
                     "dashboard for this recipient before replaying.",
        })
        ctx.flag("ambiguous_send_outcome", str(exc)[:200])
        raise ValidationError(f"Send outcome ambiguous, parked in needs_review: {exc}")
