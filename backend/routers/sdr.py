"""AI SDR endpoints.

Follows the house router conventions exactly (see any of the 25 existing
routers): own full /api prefix, Pydantic DTOs declared inline at the top,
guard as the last parameter named `user: dict`, serialize_doc/serialize_list
on the way out, no response_model, log_audit on writes that matter.

Business logic does not live here - this file is auth, validation and shape.
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from auth_utils import log_audit, require_admin, require_module
from sdr import errors
from sdr.agents import registry as agent_registry
from sdr.agents.base.agent import AgentContext
from sdr.config import benchmarks as benchmarks_config
from sdr.config import countries as countries_config
from sdr.domain import detect, pipeline, quota, roi, scoring, signals
from sdr.domain import sequence as sequence_domain
from sdr.dto.filters import DiscoveryFilters
from sdr.providers import csv_import, registry
from sdr.providers.osm_overpass import NICHES as OSM_NICHES
from sdr.repositories import agent_runs as runs_repo
from sdr.repositories import audits as audits_repo
from sdr.repositories import campaigns as campaigns_repo
from sdr.repositories import companies as companies_repo
from sdr.repositories import identities as identities_repo
from sdr.repositories import inbound as inbound_repo
from sdr.repositories import suppression as suppression_repo
from sdr.repositories import leads as leads_repo
from sdr.repositories import overview as overview_repo
from sdr.repositories import settings as settings_repo
from sdr.services import campaigns as campaigns_service
from sdr.services import discovery as discovery_service
from sdr.services import inbound as inbound_service
from sdr.services import meetings as meetings_service
from sdr.services import dns_check
from sdr.services import enrich_chain
from sdr.services import preflight as preflight_service
from sdr.services import jobs as jobs_service

router = APIRouter(prefix="/api/sdr", tags=["ai-sdr"])

#: Matches the "ai_sdr" entry added to auth_utils.PERMISSION_MODULES, so an
#: admin can scope a team member to (or away from) this module exactly as
#: they already can for finance, vault and emails.
require_sdr = require_module("ai_sdr")


# --- DTOs ---------------------------------------------------------------------

class SettingsUpdate(BaseModel):
    module_enabled: Optional[bool] = None
    channels: Optional[dict] = None
    require_approval_before_first_send: Optional[bool] = None
    provider_plan: Optional[str] = None
    daily_new_leads_cap: Optional[int] = Field(default=None, ge=0, le=10000)
    monthly_send_cap: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    touches_per_lead: Optional[int] = Field(default=None, ge=1, le=20)
    daily_send_cap: Optional[int] = Field(default=None, ge=0, le=10000)
    per_domain_daily_cap: Optional[int] = Field(default=None, ge=0, le=500)
    max_touches_per_lead: Optional[int] = Field(default=None, ge=1, le=20)
    cooldown_days_between_campaigns: Optional[int] = Field(default=None, ge=0, le=365)
    daily_llm_spend_cap_usd: Optional[float] = Field(default=None, ge=0)
    default_country_code: Optional[str] = None
    open_tracking_enabled: Optional[bool] = None
    click_tracking_enabled: Optional[bool] = None
    send_mode: Optional[str] = None
    brand_voice: Optional[str] = None
    do_not_say: Optional[list] = None


class KillSwitchUpdate(BaseModel):
    enabled: bool
    reason: Optional[str] = None


class DiscoveryRequest(BaseModel):
    filters: DiscoveryFilters
    #: Off by default. Discovering companies is cheap and reversible; creating
    #: CRM leads puts rows on the pipeline board that someone has to clean up.
    create_leads: bool = False
    icp_profile_id: Optional[str] = None


class StageTransition(BaseModel):
    stage: str
    reason: Optional[str] = None


class QualificationUpdate(BaseModel):
    status: str
    reason: Optional[str] = None


class BulkAssign(BaseModel):
    lead_ids: list = Field(..., min_length=1, max_length=500)
    owner_id: str


class AgentRunRequest(BaseModel):
    payload: dict = Field(default_factory=dict)


class ProcessBatch(BaseModel):
    lead_ids: list = Field(..., min_length=1, max_length=500)
    batch_key: Optional[str] = None


class IdentityCreate(BaseModel):
    identity: str
    channel: str = "email"
    label: Optional[str] = None
    daily_cap_target: int = Field(default=200, ge=1, le=5000)
    dkim_selector: Optional[str] = None


class PauseRequest(BaseModel):
    reason: Optional[str] = None


class SuppressionCreate(BaseModel):
    value: str
    value_type: str = "email"
    reason: str = "manual"


class CampaignCreate(BaseModel):
    name: str
    sequence: Optional[list] = None       # None -> the shipped default
    approval_mode: Optional[str] = None   # None -> settings decide


class CampaignLaunch(BaseModel):
    lead_ids: list = Field(..., min_length=1, max_length=1000)


class CampaignStatusChange(BaseModel):
    status: str


class MessageApprove(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None


class MessageReject(BaseModel):
    regenerate: bool = True


class QuotaSimulate(BaseModel):
    daily_new_leads_cap: int = Field(..., ge=0, le=10000)
    touches_per_lead: Optional[int] = Field(default=None, ge=1, le=20)
    monthly_send_cap: Optional[int] = Field(default=None, ge=0)
    provider_plan: Optional[str] = None


class EnqueueRequest(BaseModel):
    agent_key: str
    entity_ids: list = Field(..., min_length=1, max_length=1000)
    #: Which payload key the entity id goes into - "company_id" for
    #: enrichment, "lead_id" for scoring, and so on.
    entity_field: str = "company_id"
    shared_payload: dict = Field(default_factory=dict)
    #: Distinguishes deliberate re-runs from accidental double submits. Same
    #: batch_key means the second enqueue is a no-op.
    batch_key: Optional[str] = None


def _http(error: errors.SDRError) -> HTTPException:
    """Map a typed domain error onto the HTTP layer."""
    return HTTPException(status_code=error.status_code, detail=error.message)


# --- Overview -----------------------------------------------------------------

@router.get("/overview")
async def get_overview(user: dict = Depends(require_sdr)):
    """KPI payload for the Overview page. Returns an object, not a list."""
    return await overview_repo.get_overview()


@router.get("/health")
async def health(user: dict = Depends(require_sdr)):
    """Module health for the agents page and uptime monitoring."""
    settings = await settings_repo.get_settings()
    stats = await overview_repo.get_overview()
    return {
        "module_enabled": settings["module_enabled"],
        "kill_switch": settings["kill_switch"],
        "channels": settings["channels"],
        "jobs_queued": stats["health"]["jobs_queued"],
        "jobs_dead_letter": stats["health"]["jobs_dead_letter"],
        "agent_runs_failed": stats["health"]["agent_runs_failed"],
    }


# --- Settings -----------------------------------------------------------------

@router.get("/settings")
async def get_settings(user: dict = Depends(require_sdr)):
    return await settings_repo.get_settings()


@router.put("/settings")
async def update_settings(payload: SettingsUpdate, user: dict = Depends(require_admin)):
    patch = payload.model_dump(exclude_none=True)

    if "default_country_code" in patch and patch["default_country_code"]:
        code = patch["default_country_code"].upper()
        if code not in countries_config.supported_country_codes():
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No country profile for '{code}'. Supported: "
                    f"{', '.join(countries_config.supported_country_codes())}."
                ),
            )
        patch["default_country_code"] = code

    if "channels" in patch:
        known = set(settings_repo.DEFAULTS["channels"].keys())
        unknown = set(patch["channels"]) - known
        if unknown:
            raise HTTPException(
                status_code=400, detail=f"Unknown channel(s): {', '.join(sorted(unknown))}"
            )

    if "send_mode" in patch:
        if patch["send_mode"] not in ("live", "simulate"):
            raise HTTPException(status_code=400, detail="send_mode must be 'live' or 'simulate'.")
        # Going live is the consequential direction; make it unmistakable in
        # the audit trail rather than folded into a generic settings write.
        await log_audit(
            user["id"],
            "sdr_send_mode_live" if patch["send_mode"] == "live" else "sdr_send_mode_simulate",
            "sdr_settings", "main",
        )

    if "reply_to_address" in patch:
        address = (patch["reply_to_address"] or "").strip() or None
        # A malformed Reply-To silently swallows every reply the campaign
        # earns, so it is checked here rather than discovered later.
        if address and ("@" not in address or " " in address):
            raise HTTPException(
                status_code=400,
                detail="reply_to_address must be a single email address, or empty.",
            )
        patch["reply_to_address"] = address

    result = await settings_repo.update_settings(patch)
    await log_audit(user["id"], "update_sdr_settings", "sdr_settings", "main")

    # Return the plan-fit verdict alongside, so raising the lead rate past
    # what the email plan supports is visible immediately rather than three
    # weeks later when the quota runs out mid-sequence.
    plan = quota.get_plan(result.get("provider_plan"))
    result["quota_fit"] = quota.check_plan_fit(
        new_leads_per_day=result.get("daily_new_leads_cap") or 0,
        monthly_limit=result.get("monthly_send_cap") or plan.get("monthly_limit"),
        daily_limit=plan.get("daily_limit"),
        touches_per_lead=result.get("touches_per_lead") or 3,
    )
    return result


@router.post("/kill-switch")
async def set_kill_switch(payload: KillSwitchUpdate, user: dict = Depends(require_admin)):
    """Halt or resume all outbound sending.

    Checked by the send pre-flight on every message rather than cached,
    because Vercel invocations share no memory - a cached flag would not
    propagate and the switch would not actually stop anything.
    """
    result = await settings_repo.set_kill_switch(payload.enabled, payload.reason)
    await log_audit(
        user["id"],
        "sdr_kill_switch_on" if payload.enabled else "sdr_kill_switch_off",
        "sdr_settings",
        "main",
    )
    return result


# --- Configuration reference --------------------------------------------------
#
# The UI builds its filter panels and explanatory copy from these rather than
# duplicating the registries in JavaScript, so adding a country or a signal
# needs no frontend change.

@router.get("/config/countries")
async def list_countries(user: dict = Depends(require_sdr)):
    return {
        "countries": [
            countries_config.get_country(code)
            for code in countries_config.supported_country_codes()
        ],
        "default": countries_config.DEFAULT_COUNTRY,
    }


@router.get("/config/compliance/{country_code}")
async def get_compliance(country_code: str, user: dict = Depends(require_sdr)):
    profile = countries_config.get_compliance_profile(country_code)
    permitted_by_channel = {
        channel: dict(
            zip(
                ("permitted", "reason"),
                countries_config.is_cold_outreach_permitted(country_code, channel),
            )
        )
        for channel in ("email", "whatsapp", "sms", "voice", "linkedin")
    }
    return {"profile": profile, "channels": permitted_by_channel}


@router.get("/config/signals")
async def list_signals(user: dict = Depends(require_sdr)):
    return {
        "signals": [
            {
                "key": s.key,
                "label": s.label,
                "description": s.description,
                "severity": s.severity,
                "capture_uplift": s.capture_uplift,
                "services": list(s.services),
            }
            for s in signals.SIGNALS
        ]
    }


@router.get("/config/pipeline")
async def get_pipeline_config(user: dict = Depends(require_sdr)):
    """Stage graph, so the Kanban can disable illegal drop targets client-side.

    The server re-validates every transition regardless - this is UX only.
    """
    return {
        "stages": pipeline.STAGES,
        "open_stages": pipeline.OPEN_STAGES,
        "terminal_stages": pipeline.TERMINAL_STAGES,
        "transitions": {
            stage: sorted(pipeline.allowed_transitions(stage))
            for stage in pipeline.STAGES
        },
        "lost_reasons": pipeline.LOST_REASONS,
        "qualification_threshold": scoring.QUALIFICATION_THRESHOLD,
        "scoring_version": scoring.SCORING_VERSION,
        "scoring_weights": scoring.DEFAULT_WEIGHTS,
    }


@router.get("/config/benchmarks")
async def get_benchmarks(
    industry: Optional[str] = Query(default=None),
    country_code: Optional[str] = Query(default=None),
    user: dict = Depends(require_sdr),
):
    """Resolved benchmark set, so an ROI figure's basis can be inspected."""
    return benchmarks_config.resolve(industry, country_code)


@router.get("/config/filters")
async def get_filter_schema(user: dict = Depends(require_sdr)):
    """JSON Schema for DiscoveryFilters. The UI filter panel renders from
    this, so adding a filter needs no frontend change."""
    from sdr.dto.filters import describe
    return describe()


# --- Providers ----------------------------------------------------------------

@router.get("/providers")
async def list_providers(user: dict = Depends(require_sdr)):
    """Static provider metadata. No network calls."""
    return {"providers": registry.describe(), "niches": sorted(OSM_NICHES)}


@router.get("/providers/health")
async def providers_health(user: dict = Depends(require_sdr)):
    """Live health check. Hits each provider, so it is slow by design -
    do not call it on page load."""
    return {"providers": await registry.health_report()}


# --- Discovery ----------------------------------------------------------------

@router.post("/discovery/run")
async def run_discovery(payload: DiscoveryRequest, user: dict = Depends(require_sdr)):
    """Search configured providers, dedupe, and store the results.

    Runs inline rather than queued: the provider timeouts are tuned to fit
    inside the 60-second serverless ceiling, and an operator triggering a
    search expects to see results. Scheduled discovery moves to the job
    runner in Phase 3.
    """
    try:
        result = await discovery_service.run_discovery(
            payload.filters,
            user=user,
            create_leads=payload.create_leads,
            icp_profile_id=payload.icp_profile_id,
        )
    except errors.SDRError as exc:
        raise _http(exc)

    await log_audit(user["id"], "sdr_discovery_run", "sdr_discovery_run",
                    result["discovery_run_id"])
    return result


@router.get("/discovery/runs")
async def list_discovery_runs(
    limit: int = Query(default=25, ge=1, le=100),
    user: dict = Depends(require_sdr),
):
    return {"runs": await discovery_service.list_runs(limit)}


@router.post("/discovery/import-csv")
async def import_csv(
    file: UploadFile = File(...),
    create_leads: bool = Query(default=True),
    user: dict = Depends(require_sdr),
):
    """Import companies from a spreadsheet export.

    Column matching is forgiving; anything unrecognised is reported back
    rather than dropped silently, so a mis-mapped export is visible before
    a thousand rows land in the database.
    """
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File is larger than 10 MB.")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            content = raw.decode("latin-1")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Could not read the file as text. Export it as UTF-8 CSV.",
            )

    try:
        parsed = csv_import.parse(content)
        result = await discovery_service.import_companies(
            parsed["records"], user=user, create_leads=create_leads,
            source_label="csv_import",
        )
    except errors.SDRError as exc:
        raise _http(exc)

    await log_audit(user["id"], "sdr_import_csv", "sdr_discovery_run",
                    result["discovery_run_id"])
    return {**result, "parse_report": parsed["report"]}


@router.post("/discovery/preview-csv")
async def preview_csv(file: UploadFile = File(...), user: dict = Depends(require_sdr)):
    """Parse without storing, so the operator can check the column mapping
    before committing a large file."""
    raw = await file.read()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("latin-1", errors="replace")
    try:
        parsed = csv_import.parse(content)
    except errors.SDRError as exc:
        raise _http(exc)
    return {"report": parsed["report"], "sample": parsed["records"][:10]}


# --- Companies ----------------------------------------------------------------

@router.get("/companies")
async def list_companies(
    search: Optional[str] = Query(default=None),
    industry: Optional[str] = Query(default=None),
    country_code: Optional[str] = Query(default=None),
    enrichment_status: Optional[str] = Query(default=None),
    has_website: Optional[bool] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
    user: dict = Depends(require_sdr),
):
    return await companies_repo.list_companies(
        search=search, industry=industry, country_code=country_code,
        enrichment_status=enrichment_status, has_website=has_website,
        limit=limit, cursor=cursor,
    )


@router.get("/companies/{company_id}")
async def get_company(company_id: str, user: dict = Depends(require_sdr)):
    try:
        return await companies_repo.get_company(company_id)
    except errors.SDRError as exc:
        raise _http(exc)


# --- Leads --------------------------------------------------------------------

@router.get("/leads")
async def list_leads(
    stage: Optional[str] = Query(default=None),
    qualification_status: Optional[str] = Query(default=None),
    owner_id: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    min_score: Optional[int] = Query(default=None, ge=0, le=100),
    sdr_only: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
    user: dict = Depends(require_sdr),
):
    try:
        return await leads_repo.list_leads(
            stage=stage, qualification_status=qualification_status,
            owner_id=owner_id, search=search, min_score=min_score,
            sdr_only=sdr_only, limit=limit, cursor=cursor,
        )
    except errors.SDRError as exc:
        raise _http(exc)


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: str, user: dict = Depends(require_sdr)):
    """Lead with its company, timeline and signals - powers the detail drawer."""
    try:
        lead = await leads_repo.get_lead(lead_id)
        company = None
        if lead.get("sdr_company_id"):
            try:
                company = await companies_repo.get_company(lead["sdr_company_id"])
            except errors.NotFoundError:
                company = None
        return {
            "lead": lead,
            "company": company,
            "activities": await leads_repo.activities(lead_id),
        }
    except errors.SDRError as exc:
        raise _http(exc)


@router.patch("/leads/{lead_id}/stage")
async def transition_stage(lead_id: str, payload: StageTransition,
                           user: dict = Depends(require_sdr)):
    """Move a lead through the pipeline. Illegal transitions are rejected."""
    try:
        lead = await leads_repo.transition_stage(
            lead_id, payload.stage, actor="user", actor_id=user["id"],
            reason=payload.reason,
        )
    except errors.SDRError as exc:
        raise _http(exc)
    await log_audit(user["id"], "sdr_lead_stage_change", "lead", lead_id)
    return lead


@router.patch("/leads/{lead_id}/qualification")
async def set_qualification(lead_id: str, payload: QualificationUpdate,
                            user: dict = Depends(require_sdr)):
    try:
        return await leads_repo.set_qualification(lead_id, payload.status, payload.reason)
    except errors.SDRError as exc:
        raise _http(exc)


@router.delete("/leads/{lead_id}")
async def delete_lead(lead_id: str, user: dict = Depends(require_sdr)):
    """Soft delete. The lead stays in the database so audit entries pointing
    at it remain meaningful."""
    try:
        await leads_repo.soft_delete(lead_id)
    except errors.SDRError as exc:
        raise _http(exc)
    await log_audit(user["id"], "sdr_lead_delete", "lead", lead_id)
    return {"deleted": True}


@router.post("/leads/bulk/assign")
async def bulk_assign(payload: BulkAssign, user: dict = Depends(require_sdr)):
    try:
        modified = await leads_repo.bulk_assign(payload.lead_ids, payload.owner_id)
    except errors.SDRError as exc:
        raise _http(exc)
    await log_audit(user["id"], "sdr_lead_bulk_assign", "lead", None)
    return {"modified": modified}


# --- Agents -------------------------------------------------------------------

@router.get("/agents")
async def list_agents(user: dict = Depends(require_sdr)):
    """Registered agents with 24h health, for the Agents page."""
    return {
        "agents": agent_registry.describe(),
        "stats": await runs_repo.agent_stats(hours=24),
        "jobs": await jobs_service.stats(),
        "daily_spend_usd": await runs_repo.daily_spend_usd(),
    }


@router.get("/agents/runs")
async def list_agent_runs(
    agent_key: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    entity_id: Optional[str] = Query(default=None),
    correlation_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
    user: dict = Depends(require_sdr),
):
    return await runs_repo.list_runs(
        agent_key=agent_key, status=status, entity_id=entity_id,
        correlation_id=correlation_id, limit=limit, cursor=cursor,
    )


@router.get("/agents/runs/{run_id}")
async def get_agent_run(run_id: str, user: dict = Depends(require_sdr)):
    """One run with its full input/output, for the inspector.

    Both are stored redacted - see agents/base/guardrails.redact - so this
    endpoint cannot become a way to read the contact database.
    """
    try:
        run = await runs_repo.get_run(run_id)
    except errors.SDRError as exc:
        raise _http(exc)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/agents/trace/{correlation_id}")
async def get_trace(correlation_id: str, user: dict = Depends(require_sdr)):
    """Every run in one lead's journey, oldest first."""
    return {"runs": await runs_repo.get_trace(correlation_id)}


@router.post("/agents/{agent_key}/run")
async def run_agent_now(agent_key: str, payload: AgentRunRequest,
                        user: dict = Depends(require_sdr)):
    """Run an agent immediately against one entity.

    Synchronous, for the "try it on this lead" button. Scheduled and bulk work
    goes through the queue instead - an LLM call plus provider I/O does not
    reliably fit inside the 60-second serverless ceiling at volume.
    """
    agent = agent_registry.get_agent(agent_key)
    if not agent:
        raise HTTPException(status_code=404, detail=f"No agent registered as '{agent_key}'")

    allowed, reason = await _module_ready()
    if not allowed:
        raise HTTPException(status_code=409, detail=reason)

    ctx = AgentContext(user=user, trigger="manual")
    try:
        result = await agent.run(payload.payload, ctx)
    except errors.SDRError as exc:
        # The run row is already recorded as failed by the runner; surface the
        # id so the operator can open the inspector on it.
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"{exc.message} (run {ctx.run_id})",
        )

    await log_audit(user["id"], "sdr_agent_manual_run", "sdr_agent_run", result.run_id)
    return result.as_dict()


# --- Research chain -----------------------------------------------------------

@router.post("/leads/{lead_id}/process")
async def process_lead(lead_id: str, user: dict = Depends(require_sdr)):
    """Run enrich -> audit -> research -> score -> qualify inline for one lead.

    For the "process this lead" button, where someone is watching. Bulk work
    goes through /leads/process-batch, which queues instead - the full chain
    does not reliably fit in one 60-second invocation at volume.
    """
    allowed, reason = await _module_ready()
    if not allowed:
        raise HTTPException(status_code=409, detail=reason)
    try:
        result = await enrich_chain.run_chain_now(lead_id, user=user)
    except errors.SDRError as exc:
        raise _http(exc)
    await log_audit(user["id"], "sdr_lead_processed", "lead", lead_id)
    return result


@router.post("/leads/process-batch")
async def process_leads_batch(payload: ProcessBatch, user: dict = Depends(require_sdr)):
    """Queue the full research chain across many leads."""
    allowed, reason = await _module_ready()
    if not allowed:
        raise HTTPException(status_code=409, detail=reason)
    result = await enrich_chain.enqueue_chain(
        payload.lead_ids, batch_key=payload.batch_key or "chain", user_id=user["id"]
    )
    await log_audit(user["id"], "sdr_leads_batch_processed", "lead", None)
    return result


# --- Audits and signals -------------------------------------------------------

@router.get("/audits")
async def list_audits(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
    user: dict = Depends(require_sdr),
):
    return await audits_repo.list_audits(status=status, limit=limit, cursor=cursor)


@router.get("/audits/summary")
async def audits_summary(user: dict = Depends(require_sdr)):
    """Which gaps are most common across the database.

    Genuinely useful for positioning: if most prospects lack a booking
    system, that is the offer to lead with.
    """
    return {
        "signal_counts": await audits_repo.signal_counts(),
        # Surfaced so a reader knows what an audit does not cover. Omitting
        # this would let a clean audit read as a clean bill of health.
        "unmeasured": list(detect.UNMEASURED_FACTS),
        "audit_version": audits_repo.AUDIT_VERSION,
    }


@router.get("/audits/{audit_id}")
async def get_audit(audit_id: str, user: dict = Depends(require_sdr)):
    try:
        audit = await audits_repo.get_audit(audit_id)
    except errors.SDRError as exc:
        raise _http(exc)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    return audit


@router.get("/companies/{company_id}/audit")
async def get_company_audit(company_id: str, user: dict = Depends(require_sdr)):
    """Latest audit plus derived signals and their ROI estimates."""
    try:
        company = await companies_repo.get_company(company_id)
    except errors.SDRError as exc:
        raise _http(exc)

    audit = await audits_repo.latest_audit(company_id)
    company_signals = await audits_repo.signals_for(company_id)

    opportunity = None
    if company_signals:
        marks = benchmarks_config.resolve(
            company.get("industry"), company.get("country_code")
        )
        facts = (audit or {}).get("facts") or {}
        opportunity = roi.estimate_opportunity(marks, facts, company_signals)

    return {
        "company": company,
        "audit": audit,
        "signals": company_signals,
        "opportunity": opportunity,
        "history": await audits_repo.audit_history(company_id, limit=5),
    }


# --- Campaigns and outreach ---------------------------------------------------

@router.get("/campaigns")
async def list_campaigns(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
    user: dict = Depends(require_sdr),
):
    return await campaigns_repo.list_campaigns(status=status, limit=limit, cursor=cursor)


@router.post("/campaigns")
async def create_campaign(payload: CampaignCreate, user: dict = Depends(require_sdr)):
    settings = await settings_repo.get_settings()
    # A fresh install defaults every campaign to human approval; auto is an
    # explicit choice made per campaign, never inherited silently.
    default_mode = "manual" if settings.get("require_approval_before_first_send", True) else "auto"
    try:
        campaign = await campaigns_repo.create_campaign(
            name=payload.name,
            sequence_steps=payload.sequence or sequence_domain.DEFAULT_SEQUENCE,
            approval_mode=payload.approval_mode or default_mode,
            user=user,
            max_touches=settings.get("max_touches_per_lead") or 5,
        )
    except errors.SDRError as exc:
        raise _http(exc)
    await log_audit(user["id"], "sdr_campaign_created", "sdr_campaign", campaign["id"])
    return campaign


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, user: dict = Depends(require_sdr)):
    try:
        campaign = await campaigns_repo.get_campaign(campaign_id)
    except errors.SDRError as exc:
        raise _http(exc)
    return {
        "campaign": campaign,
        "enrollments": await campaigns_repo.enrollment_summary(campaign_id),
    }


@router.post("/campaigns/{campaign_id}/launch")
async def launch_campaign(campaign_id: str, payload: CampaignLaunch,
                          user: dict = Depends(require_sdr)):
    allowed, reason = await _module_ready()
    if not allowed:
        raise HTTPException(status_code=409, detail=reason)
    try:
        result = await campaigns_service.launch_campaign(
            campaign_id, lead_ids=payload.lead_ids, user=user
        )
    except errors.SDRError as exc:
        raise _http(exc)
    await log_audit(user["id"], "sdr_campaign_launched", "sdr_campaign", campaign_id)
    return result


@router.post("/campaigns/{campaign_id}/status")
async def set_campaign_status(campaign_id: str, payload: CampaignStatusChange,
                              user: dict = Depends(require_sdr)):
    try:
        campaign = await campaigns_repo.set_campaign_status(campaign_id, payload.status)
    except errors.SDRError as exc:
        raise _http(exc)
    await log_audit(user["id"], f"sdr_campaign_{payload.status}", "sdr_campaign", campaign_id)
    return campaign


@router.get("/messages")
async def list_outreach_messages(
    campaign_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
    user: dict = Depends(require_sdr),
):
    return await campaigns_repo.list_messages(
        campaign_id=campaign_id, status=status, limit=limit, cursor=cursor
    )


@router.post("/messages/{message_id}/approve")
async def approve_message(message_id: str, payload: MessageApprove,
                          user: dict = Depends(require_sdr)):
    try:
        message = await campaigns_service.approve_message(
            message_id, user=user, subject=payload.subject, body=payload.body
        )
    except errors.SDRError as exc:
        raise _http(exc)
    await log_audit(user["id"], "sdr_message_approved", "sdr_message", message_id)
    return message


@router.post("/messages/{message_id}/reject")
async def reject_message(message_id: str, payload: MessageReject,
                         user: dict = Depends(require_sdr)):
    try:
        result = await campaigns_service.reject_message(
            message_id, user=user, regenerate=payload.regenerate
        )
    except errors.SDRError as exc:
        raise _http(exc)
    await log_audit(user["id"], "sdr_message_rejected", "sdr_message", message_id)
    return result


@router.post("/leads/{lead_id}/mark-replied")
async def mark_lead_replied(lead_id: str, user: dict = Depends(require_sdr)):
    """Manual reply hook until inbound email exists (Phase 6): stamps the
    lead, stops its sequences, cancels pending drafts."""
    try:
        result = await campaigns_service.mark_lead_replied(lead_id, user=user)
    except errors.SDRError as exc:
        raise _http(exc)
    await log_audit(user["id"], "sdr_lead_marked_replied", "lead", lead_id)
    return result


# --- Inbox: inbound replies ---------------------------------------------------

class InboundReclassify(BaseModel):
    category: str = Field(min_length=1, max_length=40)


@router.get("/inbox")
async def list_inbox(
    category: Optional[str] = Query(default=None),
    lead_id: Optional[str] = Query(default=None),
    needs_human: Optional[bool] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
    user: dict = Depends(require_sdr),
):
    return await inbound_repo.list_inbound(
        category=category, lead_id=lead_id, needs_human=needs_human,
        limit=limit, cursor=cursor,
    )


@router.post("/inbox/poll")
async def poll_inbox(user: dict = Depends(require_admin)):
    """Force an IMAP poll. Normally runs on the tick; exposed so the mailbox
    connection can be tested without waiting for a cron cycle."""
    return await inbound_service.poll_imap()


@router.get("/inbox/summary")
async def inbox_summary(user: dict = Depends(require_sdr)):
    return await inbound_service.summary()


@router.get("/inbox/{inbound_id}")
async def get_inbound(inbound_id: str, user: dict = Depends(require_sdr)):
    """One reply, plus the outbound message it answers.

    Both, because a reply read without the email that provoked it is how a
    human makes the same misjudgement the classifier just did.
    """
    try:
        stored = await inbound_repo.get(inbound_id)
    except errors.SDRError as exc:
        raise _http(exc)

    sent = None
    if stored.get("message_id"):
        try:
            sent = await campaigns_repo.get_message(stored["message_id"])
        except errors.SDRError:
            sent = None   # the outbound row was removed; the reply still stands
    return {**stored, "sent_message": sent}


@router.post("/inbox/{inbound_id}/reclassify")
async def reclassify_inbound(inbound_id: str, payload: InboundReclassify,
                             user: dict = Depends(require_sdr)):
    """Override the category and apply it for real - including restarting a
    sequence that was stopped on a wrong call."""
    try:
        result = await inbound_service.reclassify(
            inbound_id, payload.category, user=user
        )
    except errors.SDRError as exc:
        raise _http(exc)
    await log_audit(user["id"], "sdr_inbound_reclassified", "sdr_inbound", inbound_id)
    return result


@router.post("/inbox/{inbound_id}/reviewed")
async def mark_inbound_reviewed(inbound_id: str, user: dict = Depends(require_sdr)):
    try:
        return await inbound_service.mark_reviewed(inbound_id, user=user)
    except errors.SDRError as exc:
        raise _http(exc)


# --- Meetings -----------------------------------------------------------------

@router.get("/leads/{lead_id}/meeting-slots")
async def lead_meeting_slots(lead_id: str, user: dict = Depends(require_sdr)):
    """Times that work for both the agency and the lead, in the lead's zone."""
    try:
        return await meetings_service.propose_slots(lead_id)
    except errors.SDRError as exc:
        raise _http(exc)


@router.post("/leads/{lead_id}/propose-meeting")
async def propose_meeting(lead_id: str, user: dict = Depends(require_sdr)):
    """Draft the proposal email. Drafts only — it lands in the approval queue
    like every other message, because a message committing real calendar time
    is not where a human gets skipped."""
    agent = agent_registry.get_agent("meeting_proposal")
    if not agent:
        raise HTTPException(status_code=500, detail="meeting_proposal agent is not registered")
    try:
        result = await agent.run({"lead_id": lead_id}, AgentContext(user=user, trigger="manual"))
    except errors.SDRError as exc:
        raise _http(exc)
    await log_audit(user["id"], "sdr_meeting_proposed", "lead", lead_id)
    return result.as_dict()


@router.post("/meetings/sweep-no-shows")
async def sweep_no_shows(user: dict = Depends(require_admin)):
    """Normally runs on the tick; exposed so it can be forced."""
    return await meetings_service.sweep_no_shows()


@router.get("/config/sequence-default")
async def get_default_sequence(user: dict = Depends(require_sdr)):
    return {"steps": sequence_domain.DEFAULT_SEQUENCE,
            "max_steps": sequence_domain.MAX_STEPS}


# --- Deliverability: sending identities ---------------------------------------

@router.get("/identities")
async def list_identities(user: dict = Depends(require_sdr)):
    return {"identities": await identities_repo.list_identities()}


@router.post("/identities")
async def create_identity(payload: IdentityCreate, user: dict = Depends(require_admin)):
    """Register a from-address. Starts paused and unverified.

    Creating an identity must never be enough to start sending - DNS has to
    pass and it has to be explicitly activated.
    """
    try:
        identity = await identities_repo.create_identity(
            identity=payload.identity, channel=payload.channel, label=payload.label,
            daily_cap_target=payload.daily_cap_target,
            dkim_selector=payload.dkim_selector, user_id=user["id"],
        )
    except errors.SDRError as exc:
        raise _http(exc)
    await log_audit(user["id"], "sdr_identity_created", "sdr_identity", identity["id"])
    return identity


@router.post("/identities/{identity_id}/verify-dns")
async def verify_identity_dns(identity_id: str, user: dict = Depends(require_sdr)):
    """Run live SPF, DKIM, DMARC and MX lookups and store the result."""
    try:
        identity = await identities_repo.get_identity(identity_id)
    except errors.SDRError as exc:
        raise _http(exc)

    result = dns_check.verify_domain(identity.get("domain"), identity.get("dkim_selector"))
    updated = await identities_repo.update_dns(identity_id, result)
    ok, reason = dns_check.ready_to_send(result)
    return {"identity": updated, "dns": result, "ready_to_send": ok, "reason": reason}


@router.post("/identities/{identity_id}/activate")
async def activate_identity(identity_id: str, user: dict = Depends(require_admin)):
    """Begin warm-up. Refused unless SPF, DKIM and DMARC all pass."""
    try:
        identity = await identities_repo.activate(identity_id)
    except errors.SDRError as exc:
        raise _http(exc)
    await log_audit(user["id"], "sdr_identity_activated", "sdr_identity", identity_id)
    return identity


@router.post("/identities/{identity_id}/pause")
async def pause_identity(identity_id: str, payload: PauseRequest,
                         user: dict = Depends(require_admin)):
    try:
        identity = await identities_repo.pause(identity_id, payload.reason or "Paused manually")
    except errors.SDRError as exc:
        raise _http(exc)
    await log_audit(user["id"], "sdr_identity_paused", "sdr_identity", identity_id)
    return identity


# --- Deliverability: suppression ----------------------------------------------

@router.get("/suppression")
async def list_suppression(
    value_type: Optional[str] = Query(default=None),
    reason: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
    user: dict = Depends(require_sdr),
):
    return await suppression_repo.list_suppressions(
        value_type=value_type, reason=reason, search=search,
        limit=limit, cursor=cursor,
    )


@router.get("/suppression/summary")
async def suppression_summary(user: dict = Depends(require_sdr)):
    return {"by_reason": await suppression_repo.counts_by_reason()}


@router.post("/suppression")
async def add_suppression(payload: SuppressionCreate, user: dict = Depends(require_sdr)):
    try:
        entry = await suppression_repo.suppress(
            value=payload.value, value_type=payload.value_type,
            reason=payload.reason, source="manual", added_by=user["id"],
        )
    except errors.SDRError as exc:
        raise _http(exc)
    await log_audit(user["id"], "sdr_suppression_added", "sdr_suppression", entry["id"])
    return entry


@router.delete("/suppression")
async def remove_suppression(
    value: str = Query(...),
    value_type: str = Query(default="email"),
    user: dict = Depends(require_admin),
):
    """Remove an entry. Admin only, and audited.

    Possible on purpose - a bounce from a temporarily-down mail server should
    not blocklist a real prospect forever - but never casual.
    """
    removed = await suppression_repo.unsuppress(value, value_type)
    if removed:
        await suppression_repo.record_consent(
            action="rectification", value=value,
            evidence={"removed_by": user["id"]},
        )
        await log_audit(user["id"], "sdr_suppression_removed", "sdr_suppression", None)
    return {"removed": removed}


@router.get("/quota")
async def get_quota(user: dict = Depends(require_sdr)):
    """Provider quota: what is configured, what is spent, what fits.

    The monthly figure is the one that matters on a metered plan - the daily
    limit is rarely the binding constraint.
    """
    settings = await settings_repo.get_settings()
    plan = quota.get_plan(settings.get("provider_plan"))

    monthly_cap = settings.get("monthly_send_cap") or plan.get("monthly_limit")
    daily_cap = settings.get("daily_send_cap") or plan.get("daily_limit")
    touches = settings.get("touches_per_lead") or quota.DEFAULT_TOUCHES_PER_LEAD

    budget = quota.remaining_budget(
        sent_this_month=await identities_repo.org_usage_this_month(),
        monthly_limit=monthly_cap,
        sent_today=await identities_repo.org_usage_today(),
        daily_limit=daily_cap,
    )
    fit = quota.check_plan_fit(
        new_leads_per_day=settings.get("daily_new_leads_cap") or 0,
        monthly_limit=monthly_cap,
        daily_limit=plan.get("daily_limit"),
        touches_per_lead=touches,
    )
    return {"plan": plan, "budget": budget, "fit": fit,
            "daily_new_leads_cap": settings.get("daily_new_leads_cap")}


@router.post("/quota/simulate")
async def simulate_quota(payload: QuotaSimulate, user: dict = Depends(require_sdr)):
    """Check a lead rate against the plan before committing to it."""
    settings = await settings_repo.get_settings()
    plan = quota.get_plan(payload.provider_plan or settings.get("provider_plan"))
    monthly = payload.monthly_send_cap or settings.get("monthly_send_cap") or plan.get("monthly_limit")
    return quota.check_plan_fit(
        new_leads_per_day=payload.daily_new_leads_cap,
        monthly_limit=monthly,
        daily_limit=plan.get("daily_limit"),
        touches_per_lead=payload.touches_per_lead or settings.get("touches_per_lead") or 3,
    )


@router.get("/preflight/check")
async def preflight_check(
    recipient_email: str = Query(...),
    country_code: Optional[str] = Query(default=None),
    channel: str = Query(default="email"),
    user: dict = Depends(require_sdr),
):
    """Dry-run the send gate without sending.

    Every check and its verdict comes back, so "why did nothing send" is
    answerable before a campaign launches rather than after it silently does
    nothing.
    """
    result = await preflight_service.check(
        recipient_email=recipient_email, country_code=country_code,
        channel=channel, respect_send_window=True,
    )
    # A dry run must not consume the allowance it just claimed.
    if result.allowed and result.identity:
        await preflight_service.release_claim(
            result.identity["identity"], recipient_email
        )
    return result.as_dict()


# --- Jobs ---------------------------------------------------------------------

@router.get("/jobs")
async def list_jobs(
    status: Optional[str] = Query(default=None),
    agent_key: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
    user: dict = Depends(require_sdr),
):
    return await jobs_service.list_jobs(
        status=status, agent_key=agent_key, limit=limit, cursor=cursor
    )


@router.get("/jobs/dead-letter")
async def list_dead_letters(user: dict = Depends(require_sdr)):
    """Abandoned work. This is the queue an operator actually needs to watch."""
    return {"jobs": await jobs_service.dead_letters()}


@router.post("/jobs/enqueue")
async def enqueue_jobs(payload: EnqueueRequest, user: dict = Depends(require_sdr)):
    """Queue an agent across many entities - the bulk 'enrich these' action.

    Idempotency keys are derived per entity, so enqueueing the same batch
    twice queues nothing the second time.
    """
    if not agent_registry.get_agent(payload.agent_key):
        raise HTTPException(status_code=404, detail=f"No agent registered as '{payload.agent_key}'")

    allowed, reason = await _module_ready()
    if not allowed:
        raise HTTPException(status_code=409, detail=reason)

    agent = agent_registry.get_agent(payload.agent_key)
    jobs = [
        {
            "agent_key": payload.agent_key,
            "queue": agent.queue,
            "payload": {**payload.shared_payload, payload.entity_field: entity_id},
            "idempotency_key": f"{payload.agent_key}:{entity_id}:{payload.batch_key or 'default'}",
            "user_id": user["id"],
        }
        for entity_id in payload.entity_ids
    ]
    result = await jobs_service.enqueue_many(jobs)
    await log_audit(user["id"], "sdr_jobs_enqueued", "sdr_job", None)
    return result


@router.post("/jobs/{job_id}/replay")
async def replay_job(job_id: str, user: dict = Depends(require_sdr)):
    """Requeue a dead-lettered job with a fresh attempt budget."""
    try:
        job = await jobs_service.replay(job_id)
    except errors.SDRError as exc:
        raise _http(exc)
    await log_audit(user["id"], "sdr_job_replay", "sdr_job", job_id)
    return job


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, user: dict = Depends(require_sdr)):
    try:
        return await jobs_service.cancel(job_id)
    except errors.SDRError as exc:
        raise _http(exc)


@router.post("/jobs/drain")
async def drain_jobs_manually(user: dict = Depends(require_admin)):
    """Tick the campaigns and drain the queue on demand.

    The scheduled path is /api/automations/cron/sdr, guarded by CRON_SECRET.
    This one is admin-only and exists so an operator does not have to wait for
    the next tick.
    """
    allowed, reason = await _module_ready()
    if not allowed:
        raise HTTPException(status_code=409, detail=reason)
    tick_report = await campaigns_service.tick()
    result = await jobs_service.drain()
    result["tick"] = tick_report
    return result


async def _module_ready() -> tuple:
    """Shared precondition: the module is on and not killed.

    Checked on every path that can cause an agent to run, and read from the
    database each time rather than cached - Vercel invocations share no
    memory, so a cached kill switch would not actually stop anything.
    """
    settings = await settings_repo.get_settings()
    if settings["kill_switch"]:
        return False, f"Kill switch is on: {settings.get('kill_switch_reason') or 'no reason given'}"
    if not settings["module_enabled"]:
        return False, "The AI SDR module is disabled. Enable it on the AI SDR page."

    spend = await runs_repo.daily_spend_usd()
    cap = settings.get("daily_llm_spend_cap_usd") or 0
    if cap and spend >= cap:
        return False, (
            f"Daily AI spend cap reached (${spend:.2f} of ${cap:.2f}). "
            "Raise the cap in settings or wait for it to reset at midnight UTC."
        )
    return True, "ok"
