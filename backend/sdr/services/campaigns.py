"""Campaign orchestration: launch, approval, and the tick.

`tick()` is the heartbeat. It runs at the top of every cron drain and does
three sweeps, all idempotent so overlapping ticks and re-runs are harmless:

1. **Advance** - for every running campaign, stop enrollments whose stop
   condition has arrived, then enqueue personalization jobs for enrollments
   whose next touch is due. Step-1 touches are paced by the daily new-lead
   cap (the 30/day figure the email plan sustains); follow-ups flow freely
   and are bounded by pre-flight's daily and monthly caps instead.
2. **Send** - enqueue send jobs for approved messages whose scheduled time
   has arrived. Skipped entirely while the email channel is off or the kill
   switch is on, so a disabled system does not churn jobs it can never run.
3. **Complete** - campaigns with no active enrollments left are marked
   completed.

Idempotency is layered: job keys block duplicate enqueues, the message
repository's unique (enrollment, step) index blocks duplicate drafts even
after job records expire, and the approved->sending claim blocks duplicate
dispatch. Each layer covers the failure mode the previous one cannot.
"""

import logging

from database import db, now_iso
from sdr.domain import quota as quota_domain
from sdr.domain import sequence as sequence_domain
from sdr.errors import ValidationError
from sdr.repositories import campaigns as campaigns_repo
from sdr.repositories import identities as identities_repo
from sdr.repositories import settings as settings_repo
from sdr.repositories import suppression as suppression_repo
from sdr.repositories.base import object_id, serialize_doc
from sdr.services import jobs as jobs_service

logger = logging.getLogger(__name__)

NEW_LEAD_SCOPE = "new_leads"


async def launch_campaign(campaign_id: str, *, lead_ids: list, user: dict) -> dict:
    """Enroll leads and set the campaign running, with the quota verdict.

    The quota check is advisory at launch (the caps enforce at send time) but
    surfacing it here is the honest moment: "this sequence at this lead count
    will exceed the month" belongs before the button, not in a post-mortem.
    """
    settings = await settings_repo.get_settings()
    campaign = await campaigns_repo.get_campaign(campaign_id)
    if campaign["status"] != "draft":
        raise ValidationError(f"Only a draft campaign can be launched (this one is {campaign['status']}).")
    if not lead_ids:
        raise ValidationError("Pick at least one lead to launch with.")

    enrollment = await campaigns_repo.enroll_leads(
        campaign_id, lead_ids,
        cooldown_days=settings.get("cooldown_days_between_campaigns") or 0,
    )
    if enrollment["enrolled"] == 0:
        reasons = "; ".join(
            f"{row['lead_id'][-6:]}: {row['reason']}" for row in enrollment["skipped"][:5]
        )
        raise ValidationError(f"No leads could be enrolled. {reasons}")

    campaign = await campaigns_repo.set_campaign_status(campaign_id, "running")

    fit = quota_domain.check_plan_fit(
        new_leads_per_day=min(settings.get("daily_new_leads_cap") or 30,
                              enrollment["enrolled"]),
        monthly_limit=settings.get("monthly_send_cap"),
        daily_limit=settings.get("daily_send_cap"),
        touches_per_lead=len(campaign["sequence"]),
    )
    return {"campaign": campaign, "enrollment": enrollment, "quota_fit": fit}


async def tick() -> dict:
    """One heartbeat. Called from the cron drain and the manual drain button."""
    settings = await settings_repo.get_settings()
    report = {
        "campaigns_seen": 0, "stopped": 0, "personalization_queued": 0,
        "new_lead_slots_exhausted": False, "sends_queued": 0,
        "send_sweep_skipped": None, "completed_campaigns": 0,
        "no_shows_marked": 0, "leads_reverted": 0, "replies_ingested": 0,
        "research_queued": 0, "research_leads": 0,
    }
    # Listening is not acting. Replies are ingested before the module gate,
    # because mail already sent keeps earning answers after outbound stops -
    # and the moment you hit the kill switch is exactly when you most need to
    # know somebody replied. Going deaf on pause would also mean a reply
    # arriving during a pause never stops its sequence, so the follow-up goes
    # out the instant you resume.
    report.update(await _ingest_replies())

    if not settings.get("module_enabled") or settings.get("kill_switch"):
        report["send_sweep_skipped"] = "module disabled or kill switch on"
        return report

    # Research sweep. Discovery creates leads; without this nothing ever
    # scores them, so an operator had to open each one and press a button -
    # which is the opposite of autonomous, and the reason a campaign launched
    # against fresh leads found nothing qualified to enrol.
    report.update(await _research_new_leads())

    running = await db[campaigns_repo.CAMPAIGNS].find(
        {"status": "running", "deleted_at": None}
    ).to_list(100)

    new_lead_cap = settings.get("daily_new_leads_cap") or 30

    for campaign_doc in running:
        campaign = serialize_doc(campaign_doc)
        report["campaigns_seen"] += 1
        due = await campaigns_repo.due_enrollments(campaign["id"])

        for enrollment in due:
            lead_doc = await db.leads.find_one(
                {"_id": object_id(enrollment["lead_id"], "lead id")}
            )
            lead = serialize_doc(lead_doc) if lead_doc else {}

            hit = await suppression_repo.is_suppressed(email=lead.get("email"))
            stop = sequence_domain.evaluate_stop(
                lead, suppressed=bool(hit), campaign_status=campaign["status"]
            )
            if stop:
                await campaigns_repo.stop_enrollment(enrollment["id"], stop)
                report["stopped"] += 1
                continue

            step_index = enrollment["current_step"]
            # The unique-index belt: a draft already exists for this step, so
            # the enrollment is waiting on approval or dispatch, not on us.
            if await campaigns_repo.message_for_step(enrollment["id"], step_index):
                continue

            if step_index == 0:
                ok, _ = await identities_repo.claim_scoped_slot(
                    NEW_LEAD_SCOPE, "all", new_lead_cap
                )
                if not ok:
                    # Today's pipeline entry is full. Tomorrow's tick picks
                    # these up - that is the pacing working, not a failure.
                    report["new_lead_slots_exhausted"] = True
                    continue

            regen = enrollment.get("regen_count") or 0
            queued = await jobs_service.enqueue(
                agent_key="outreach_personalization",
                queue="personalization",
                payload={"enrollment_id": enrollment["id"]},
                idempotency_key=(
                    f"personalize:{enrollment['id']}:{step_index}:r{regen}"
                ),
                correlation_id=enrollment.get("correlation_id"),
            )
            if queued.get("duplicate"):
                if step_index == 0:
                    # The slot was claimed for work that already exists;
                    # hand it back so the cap stays honest.
                    await identities_repo.release_scoped_slot(NEW_LEAD_SCOPE, "all")
            else:
                report["personalization_queued"] += 1

        # Completion: enrolled campaigns with nothing active left are done.
        if campaign.get("enrolled_count", 0) > 0:
            summary = await campaigns_repo.enrollment_summary(campaign["id"])
            if summary.get("active", 0) == 0:
                await campaigns_repo.set_campaign_status(campaign["id"], "completed")
                report["completed_campaigns"] += 1

    # No-show sweep. Runs before the email-channel gate on purpose: a meeting
    # that came and went is not a sending concern, and a lead stranded in
    # `meeting_scheduled` looks like a win nobody needs to work.
    try:
        from sdr.services import meetings as meetings_service
        no_shows = await meetings_service.sweep_no_shows()
        report["no_shows_marked"] = no_shows["marked_no_show"]
        report["leads_reverted"] = no_shows["leads_reverted"]
    except Exception:
        # Never let calendar bookkeeping take down the outreach heartbeat.
        logger.exception("No-show sweep failed")
        report["no_shows_marked"] = None

    # Send sweep - pointless while nothing can send, and skipping it keeps
    # the queue free of jobs that would only be held.
    if not settings.get("channels", {}).get("email"):
        report["send_sweep_skipped"] = "email channel is off"
        return report

    for message in await campaigns_repo.approved_due_messages():
        attempt = message.get("send_attempt") or 0
        queued = await jobs_service.enqueue(
            agent_key="outreach_send",
            queue="send",
            payload={"message_id": message["id"]},
            # The attempt counter rotates the key when a message is deferred
            # back to approved, so it can be re-enqueued after its earlier
            # job completed. Without it, a held message would wait 30 days
            # for the old job record to expire.
            idempotency_key=f"send:{message['id']}:a{attempt}",
        )
        if not queued.get("duplicate"):
            report["sends_queued"] += 1

    return report


#: Leads sent through the research chain per tick. The chain is several jobs
#: per lead and the drain shares a 60-second ceiling with everything else, so
#: this stays small - a backlog clears over consecutive ticks rather than
#: timing one out.
RESEARCH_BATCH = 10


async def _research_new_leads() -> dict:
    """Enrich, audit, research, score and qualify leads nobody has processed.

    A lead is "new" here when it has never been scored - `score_version` is
    the marker, written by the scoring agent, so a lead that has been through
    the chain is never queued twice however it was created.

    Idempotency is the chain's own: the batch key is derived from the lead, so
    re-queueing a lead already in flight creates nothing.
    """
    try:
        cursor = db.leads.find(
            {
                "sdr_managed": True,
                "score_version": None,
                "deleted_at": None,
            },
            {"_id": 1},
        ).limit(RESEARCH_BATCH)
        lead_ids = [str(doc["_id"]) async for doc in cursor]

        if not lead_ids:
            return {"research_queued": 0}

        from sdr.services import enrich_chain
        result = await enrich_chain.enqueue_chain(lead_ids, batch_key="auto")
        if len(lead_ids) == RESEARCH_BATCH:
            logger.info("Research backlog: more unscored leads remain after this batch")
        return {"research_queued": result["jobs_queued"],
                "research_leads": len(lead_ids)}
    except Exception:
        # Research is the front of the pipeline; a failure here must not stop
        # the sends and replies behind it.
        logger.exception("Research sweep failed")
        return {"research_queued": None}


async def _ingest_replies() -> dict:
    """Poll for inbound replies, never letting a mailbox problem stop the tick.

    Separated so it can run before the module gate without duplicating the
    error handling: a mailbox that refuses connections must not take the
    heartbeat down with it.
    """
    try:
        from sdr.services import inbound as inbound_service
        polled = await inbound_service.poll_imap()
        if polled.get("truncated"):
            # More is waiting than one poll can carry. Said out loud so a
            # backlog is not mistaken for a quiet inbox.
            logger.info("IMAP backlog: more replies remain after this batch")
        return {"replies_ingested": polled.get("processed", 0)}
    except Exception:
        logger.exception("Inbound poll failed")
        return {"replies_ingested": None}


async def approve_message(message_id: str, *, user: dict,
                          subject: str | None = None,
                          body: str | None = None) -> dict:
    """Human approval, with optional edits. Edited copy re-runs the checks -
    an operator's typo can fail deliverability hygiene as easily as a model's."""
    from sdr.config.countries import get_country, get_holidays
    from sdr.domain import copy_checks, send_window

    message = await campaigns_repo.get_message(message_id)
    if message["status"] != "awaiting_approval":
        raise ValidationError(f"Only a message awaiting approval can be approved (this one is {message['status']}).")

    settings = await settings_repo.get_settings()
    final_subject = (subject or message["subject"]).strip()
    final_body = (body or message["body"]).strip()

    problems = copy_checks.check_copy(
        subject=final_subject, body=final_body,
        do_not_say=settings.get("do_not_say"),
    )
    if problems:
        raise ValidationError("The copy fails pre-send checks: " + " | ".join(problems))

    country = message.get("country_code")
    scheduled = send_window.schedule(
        now_iso(), get_country(country), seed=f"{message['enrollment_id']}:{message['step_index']}",
        holidays=get_holidays(country, int(now_iso()[:4])),
    ).isoformat()

    return await campaigns_repo.update_message(message_id, {
        "status": "approved",
        "subject": final_subject,
        "body": final_body,
        "edited_at_approval": bool(subject or body),
        "scheduled_for": scheduled,
        "send_attempt": 0,
        "approved_by": user.get("id"),
        "approved_at": now_iso(),
    })


async def reject_message(message_id: str, *, user: dict, regenerate: bool) -> dict:
    """Reject a draft. Either ask for a rewrite or stop the sequence.

    Regeneration deletes the draft row (the copy survives in the agent run
    log) and bumps the enrollment's regen counter, which rotates the
    personalization job key so the next tick produces a fresh draft.
    """
    message = await campaigns_repo.get_message(message_id)
    if message["status"] != "awaiting_approval":
        raise ValidationError(f"Only a message awaiting approval can be rejected (this one is {message['status']}).")

    if regenerate:
        await db[campaigns_repo.MESSAGES].delete_one(
            {"_id": object_id(message_id, "message id")}
        )
        await db[campaigns_repo.ENROLLMENTS].update_one(
            {"_id": object_id(message["enrollment_id"], "enrollment id")},
            {"$inc": {"regen_count": 1}},
        )
        return {"rejected": True, "regenerating": True,
                "enrollment_id": message["enrollment_id"]}

    await campaigns_repo.update_message(message_id, {
        "status": "rejected", "rejected_by": user.get("id"),
    })
    await campaigns_repo.stop_enrollment(message["enrollment_id"], "manual")
    return {"rejected": True, "regenerating": False,
            "enrollment_id": message["enrollment_id"]}


async def mark_lead_replied(lead_id: str, *, user: dict) -> dict:
    """The manual reply hook, until inbound email lands in Phase 6.

    A rep who sees a reply in their inbox clicks this: the lead is stamped,
    every active enrollment stops, and pending drafts are cancelled - a
    sequence that keeps writing after an answer reads as a bot that does not
    listen.
    """
    result = await db.leads.update_one(
        {"_id": object_id(lead_id, "lead id")},
        {"$set": {"replied_at": now_iso(), "updated_at": now_iso()}},
    )
    if not result.matched_count:
        raise ValidationError("Lead not found")

    stopped = 0
    active = await db[campaigns_repo.ENROLLMENTS].find(
        {"lead_id": lead_id, "status": sequence_domain.ACTIVE}
    ).to_list(20)
    for enrollment in active:
        await campaigns_repo.stop_enrollment(str(enrollment["_id"]), "replied")
        stopped += 1

    await db.lead_activities.insert_one({
        "lead_id": lead_id, "type": "note",
        "content": "Marked as replied - outreach sequences stopped",
        "created_by": user.get("id"), "created_at": now_iso(),
    })
    return {"lead_id": lead_id, "enrollments_stopped": stopped}
