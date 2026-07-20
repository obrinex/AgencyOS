"""SDR collection names and index definitions.

Mongo has no migrations in this repo (see the Phase 0 report, section 5), so
`create_sdr_indexes()` is called from `database.create_indexes()` at startup
and is idempotent - creating an index that already exists is a no-op.

The module deliberately adds NO parallel copies of existing entities. Leads,
contacts, activities, tasks, invoices and notifications are the host CRM's,
and the SDR module extends those documents with additive fields rather than
forking them. `SDR_LEAD_FIELDS` documents exactly which fields this module
adds to `leads`, since Mongo will not tell you.
"""

import logging

from database import db

logger = logging.getLogger(__name__)

#: Operators MongoDB accepts inside `partialFilterExpression`. Anything else
#: is rejected at index-creation time with CannotCreateIndex. Enforced by a
#: test, because this exact mistake ($nin) failed startup in production and
#: 500'd every endpoint in the app, not just this module's.
PARTIAL_FILTER_SAFE_OPERATORS = frozenset({
    "$eq", "$exists", "$gt", "$gte", "$lt", "$lte", "$type", "$and",
})

# --- New collections ----------------------------------------------------------

COMPANIES = "sdr_companies"                 # the business; leads point at it
ICP_PROFILES = "sdr_icp_profiles"           # Ideal Customer Profile definitions
WEBSITE_AUDITS = "sdr_website_audits"
OPPORTUNITY_SIGNALS = "sdr_opportunity_signals"
DISCOVERY_RUNS = "sdr_discovery_runs"
JOBS = "sdr_jobs"                           # the queue (see services/jobs.py)
AGENT_RUNS = "sdr_agent_runs"               # observability spine
AGENT_MEMORY = "sdr_agent_memory"
SUPPRESSION = "sdr_suppression"             # never-contact list
SETTINGS = "sdr_settings"                   # singleton: flags, caps, kill switch
SENDING_IDENTITIES = "sdr_sending_identities"   # mailboxes, DNS state, warm-up
SEND_COUNTERS = "sdr_send_counters"         # per-day rate-limit counters
CONSENT = "sdr_consent_records"             # DPDP/GDPR audit trail
CAMPAIGNS = "sdr_campaigns"                 # a sequence pointed at a set of leads
ENROLLMENTS = "sdr_enrollments"             # one lead's journey through one campaign
MESSAGES = "sdr_messages"                   # every outbound message, drafted to delivered
INBOUND = "sdr_inbound_messages"            # replies, matched back to what provoked them

ALL_COLLECTIONS = [
    COMPANIES, ICP_PROFILES, WEBSITE_AUDITS, OPPORTUNITY_SIGNALS,
    DISCOVERY_RUNS, JOBS, AGENT_RUNS, AGENT_MEMORY, SUPPRESSION, SETTINGS,
    SENDING_IDENTITIES, SEND_COUNTERS, CONSENT,
    CAMPAIGNS, ENROLLMENTS, MESSAGES, INBOUND,
]

# --- Fields this module adds to existing collections --------------------------
#
# Additive only. Nothing here replaces or renames an existing field, so the
# CRM pages keep working untouched. Documented because the stored shape is a
# superset of any Pydantic model in this repo and is otherwise undiscoverable.

SDR_LEAD_FIELDS = {
    "sdr_company_id": "str - link to sdr_companies",
    "sdr_managed": "bool - true when the SDR module owns this lead's automation",
    "icp_profile_id": "str - which ICP qualified it",
    "score_version": "str - which scoring model produced leads.score",
    "score_breakdown": "dict - explainability, rendered in the lead drawer",
    "qualification_status": "str - unqualified|qualified|disqualified|needs_review",
    "disqualification_reason": "str",
    "stage_entered_at": "iso str - for time-in-stage analytics",
    "previous_stage": "str",
    "next_action_at": "iso str - drives the work queue",
    "next_action_type": "str",
    "replied_at": "iso str - set when an inbound reply is matched (Phase 6)",
    "meeting_booked_at": "iso str (Phase 7)",
    "deleted_at": "iso str - soft delete, SDR-created leads only",
}

SDR_CONTACT_FIELDS = {
    "seniority": "str",
    "department": "str",
    "is_decision_maker": "bool",
    "email_status": "str - unknown|valid|risky|invalid|catch_all",
    "email_confidence": "float 0-1",
    "phone_e164": "str - E.164 only",
    "consent_status": "str - unknown|opted_in|opted_out|suppressed",
    "do_not_contact": "bool",
    "dnc_reason": "str",
    "preferred_language": "str",
}


async def _safe_index(label: str, collection, *args, **kwargs) -> None:
    """Create one index, logging and continuing on failure.

    Indexes are a performance concern, not a correctness one. A rejected
    index spec must never stop the application from serving requests - and
    must not stop the *other* indexes being created either. Learned the hard
    way: one bad spec here previously aborted startup and took every endpoint
    in the host app down with it.
    """
    try:
        await collection.create_index(*args, **kwargs)
    except Exception as exc:
        logger.error("Could not create SDR index %s: %s", label, exc)


async def create_sdr_indexes():
    """Idempotent, and non-fatal by construction.

    Called from `database.create_indexes()` at startup. Every index goes
    through `_safe_index`, so a rejected spec is logged and skipped rather
    than aborting startup - this module must never be able to take the host
    application down.
    """
    # (collection, label, args, kwargs)
    specs = [
        # Companies. dedupe_key is the multi-signal dedupe result (normalised
        # domain, else registration id, else name+city). Unique so a race
        # between two discovery runs cannot create a duplicate.
        (db[COMPANIES], "companies.dedupe_key", ("dedupe_key",), {"unique": True, "sparse": True}),
        (db[COMPANIES], "companies.domain", ("domain",), {}),
        (db[COMPANIES], "companies.geo_industry", ([("country_code", 1), ("industry", 1)],), {}),
        (db[COMPANIES], "companies.text", ([("name", "text"), ("description", "text")],), {}),
        (db[COMPANIES], "companies.enrichment_status", ("enrichment_status",), {}),

        # Leads - the work queue. Compound index ordered to match the query:
        # equality on stage, then range on next_action_at.
        (db.leads, "leads.stage_next_action", ([("stage", 1), ("next_action_at", 1)],), {}),
        (db.leads, "leads.score", ([("score", -1)],), {}),
        (db.leads, "leads.sdr_company_id", ("sdr_company_id",), {}),
        # Partial index scoped to SDR-managed leads, so it stays small as the
        # host CRM's own leads grow.
        #
        # It filters on `sdr_managed` rather than excluding closed stages
        # because partialFilterExpression accepts only a restricted operator
        # set (see PARTIAL_FILTER_SAFE_OPERATORS). An earlier version used
        # {"stage": {"$nin": [...]}}, which MongoDB rejects outright - and
        # because that threw during startup it 500'd every endpoint in the
        # app, not just this module's.
        (db.leads, "leads.sdr_next_action", ([("next_action_at", 1)],),
         {"name": "sdr_open_leads_next_action",
          "partialFilterExpression": {"sdr_managed": True}}),

        (db[ICP_PROFILES], "icp.is_active", ("is_active",), {}),

        (db[WEBSITE_AUDITS], "audits.company_date", ([("company_id", 1), ("audited_at", -1)],), {}),
        (db[OPPORTUNITY_SIGNALS], "signals.company_severity", ([("company_id", 1), ("severity", 1)],), {}),
        (db[OPPORTUNITY_SIGNALS], "signals.key", ("signal_key",), {}),

        (db[DISCOVERY_RUNS], "discovery_runs.created", ([("created_at", -1)],), {}),

        # Jobs. The claim query is {status, run_after: {$lte: now}} sorted by
        # (priority, run_after), so the index must lead with status.
        (db[JOBS], "jobs.claim", ([("status", 1), ("run_after", 1), ("priority", -1)],), {}),
        # The single most important index in this module: it is what makes job
        # redelivery safe. A duplicate idempotency_key insert fails loudly
        # rather than sending a second email to a real person.
        (db[JOBS], "jobs.idempotency", ("idempotency_key",), {"unique": True, "sparse": True}),
        (db[JOBS], "jobs.correlation", ("correlation_id",), {}),
        # Finished jobs self-expire after 30 days so the collection stays
        # bounded without a cleanup cron. TTL needs a real BSON date, unlike
        # every other timestamp in this codebase which is an ISO string.
        (db[JOBS], "jobs.ttl", ("expires_at",), {"expireAfterSeconds": 0}),

        (db[AGENT_RUNS], "runs.agent_status", ([("agent_key", 1), ("status", 1), ("created_at", -1)],), {}),
        (db[AGENT_RUNS], "runs.correlation", ("correlation_id",), {}),
        (db[AGENT_RUNS], "runs.entity", ([("entity_type", 1), ("entity_id", 1)],), {}),
        (db[AGENT_RUNS], "runs.ttl", ("expires_at",), {"expireAfterSeconds": 0}),

        (db[AGENT_MEMORY], "memory.scope",
         ([("agent_key", 1), ("scope", 1), ("scope_id", 1), ("key", 1)],), {"unique": True}),
        (db[AGENT_MEMORY], "memory.ttl", ("expires_at",), {"expireAfterSeconds": 0}),

        # Suppression is checked on the hot path before every single send and
        # must be exact-match fast. Unique prevents duplicate opt-out rows.
        (db[SUPPRESSION], "suppression.value",
         ([("value_type", 1), ("value_normalized", 1)],), {"unique": True}),

        (db[SENDING_IDENTITIES], "identities.identity", ("identity",), {"unique": True}),
        (db[SENDING_IDENTITIES], "identities.channel_status", ([("channel", 1), ("status", 1)],), {}),

        # Rate-limit counters, keyed per scope per day, so a claim is a single
        # atomic $inc rather than a read-modify-write that races under load.
        (db[SEND_COUNTERS], "counters.key", ([("scope", 1), ("key", 1), ("day", 1)],), {"unique": True}),
        (db[SEND_COUNTERS], "counters.ttl", ("expires_at",), {"expireAfterSeconds": 0}),

        (db[CONSENT], "consent.contact", ([("contact_id", 1), ("created_at", -1)],), {}),
        (db[CONSENT], "consent.value", ("value_normalized",), {}),

        (db[CAMPAIGNS], "campaigns.status", ([("status", 1), ("created_at", -1)],), {}),

        # One enrollment per lead per campaign - the invariant that stops the
        # same person being sequenced twice by the same campaign.
        (db[ENROLLMENTS], "enrollments.unique", ([("campaign_id", 1), ("lead_id", 1)],), {"unique": True}),
        # The tick's scan: active enrollments whose next touch is due.
        (db[ENROLLMENTS], "enrollments.due", ([("status", 1), ("next_touch_at", 1)],), {}),
        (db[ENROLLMENTS], "enrollments.lead", ("lead_id",), {}),

        # One message per enrollment step - the belt alongside the job
        # idempotency braces. Sparse: manual one-offs may lack an enrollment.
        (db[MESSAGES], "messages.step", ([("enrollment_id", 1), ("step_index", 1)],),
         {"unique": True, "sparse": True}),
        (db[MESSAGES], "messages.campaign", ([("campaign_id", 1), ("status", 1)],), {}),
        (db[MESSAGES], "messages.approval", ([("status", 1), ("scheduled_for", 1)],), {}),
        # Webhooks look messages up by the provider's id.
        (db[MESSAGES], "messages.provider", ("provider_message_id",), {"sparse": True}),
        # Inbound replies are matched by the Message-ID we minted.
        (db[MESSAGES], "messages.threading", ("email_message_id",), {"sparse": True}),
        # The parent lookup for a follow-up: earlier sent step in one enrollment.
        (db[MESSAGES], "messages.thread_parent",
         ([("enrollment_id", 1), ("status", 1), ("step_index", -1)],), {}),

        # One stored reply per delivered webhook - the inbound double-process
        # guard, mirroring the outbound (enrollment, step) unique index.
        (db[INBOUND], "inbound.dedupe", ("ingest_key",), {"unique": True, "sparse": True}),
        (db[INBOUND], "inbound.lead", ([("lead_id", 1), ("received_at", -1)],), {}),
        (db[INBOUND], "inbound.review", ([("category", 1), ("received_at", -1)],), {}),
        # The from-address fallback when nothing threads.
        (db[INBOUND], "inbound.sender", ("from_email",), {}),
    ]

    for collection, label, args, kwargs in specs:
        await _safe_index(label, collection, *args, **kwargs)
