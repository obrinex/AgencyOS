import os
import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from openai import AsyncOpenAI

from database import db
from auth_utils import get_current_user, require_staff

router = APIRouter(prefix="/api/ai", tags=["ai"])

# NVIDIA NIM exposes an OpenAI-compatible API at integrate.api.nvidia.com
NVIDIA_BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_MODEL = os.environ.get("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")


def _get_client() -> AsyncOpenAI:
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI assistant is not configured (missing NVIDIA_API_KEY)")
    return AsyncOpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"
    mode: Optional[str] = "general"


class GenerateEmailRequest(BaseModel):
    purpose: str
    recipient_name: Optional[str] = None
    context: Optional[str] = None
    tone: Optional[str] = "professional"


class SummarizeRequest(BaseModel):
    notes: str


class GenerateProposalRequest(BaseModel):
    client_or_lead_name: str
    scope: str
    budget: Optional[str] = None


async def build_crm_context() -> str:
    leads = await db.leads.find({}).sort("updated_at", -1).to_list(20)
    clients = await db.clients.find({}).to_list(20)
    invoices = await db.invoices.find({}).to_list(50)
    revenue = sum(i["total"] for i in invoices if i["status"] == "paid")
    outstanding = sum(i["total"] for i in invoices if i["status"] in ("sent", "overdue", "partial"))
    lines = [f"Total clients: {len(clients)}", f"Paid revenue: INR {revenue:,.2f}", f"Outstanding: INR {outstanding:,.2f}"]
    lines.append("Recent leads: " + ", ".join(f"{ld.get('company')} ({ld.get('stage')})" for ld in leads[:10]))
    return "\n".join(lines)


GUIDE_CONTEXT = """
AgencyOS module guide:
- Dashboard: KPI cards, sales funnel, revenue trend, today's tasks, upcoming meetings, recent activity, quick actions.
- CRM Pipeline: Kanban board for leads; moving a deal to Won creates a client, project, onboarding tasks, notification, and draft invoice.
- AI Lead Finder (/lead-finder): manual prospecting. Pick a business type and city,
  it searches OpenStreetMap (free, no API key) for real businesses, and the "AI Pitch"
  button drafts a cold email and a WhatsApp message. "Add to Pipeline" creates a CRM
  lead with those drafts attached. You press every button.
- AI SDR: the autonomous version of the above. Nine agents run on a schedule:
  discover -> enrich -> website audit -> research -> score -> qualify -> write ->
  approve -> send in the recipient's business hours -> read the reply. Pages:
  /ai-sdr (on/off switch, channel switches, kill switch), /ai-sdr/leads (Lead Database;
  "Enrich, audit & score" is required before a lead can enter a campaign),
  /ai-sdr/campaigns, /ai-sdr/outreach (approval queue; Simulate vs LIVE),
  /ai-sdr/inbox (replies), /ai-sdr/audits, /ai-sdr/deliverability (identities, DNS,
  warm-up, quota, and "Test a send" which shows exactly which gate is blocking).
- Agent Monitor (/ai-agents): every AI capability, success rates, estimated spend,
  queued jobs, and per-run detail. Open this first when something AI-related looks wrong.
- Three switches must all be on before any email can send, in this order:
  Module (AI SDR page) -> Email channel (Outbound channels card, same page) ->
  LIVE mode (Outreach page). All three ship off. Simulate mode runs the whole
  pipeline and stops one step before sending, marking messages as rehearsals.
- Agents vs assistants: an assistant waits for a button press (AI Assistant, email
  writer, proposal writer); an agent runs on a schedule with no one watching.
  Several SDR agents use no AI at all (website audit, scoring, sending, meeting
  proposals) - a model is used for judgement and writing, never for facts the
  system already knows.
- Common cause of "nothing is sending": the lead was never qualified (run
  "Enrich, audit & score"), or one of the three switches is off, or the sending
  identity has not passed its DNS checks. "Test a send" on the Deliverability
  page names the blocking gate directly.
- Contacts: individual people linked to companies/clients.
- Clients: workspace for onboarding checklist, projects, invoices, contacts, tickets, contracts, and portal access.
- Projects/Tasks: delivery tracking with Kanban, list, and timeline views; due tasks appear on Dashboard.
- Finance/Invoices: revenue, expenses, goals, reports, invoices, PDF download, invoice emails, client payment requests, and admin-sent payment links.
- Proposals/Contracts: AI proposal drafts, public proposal signatures, client agreement signatures.
- Calendar: internal meetings and optional Google Calendar sync.
- Support: staff/client ticket threads.
- Knowledge Base, Files, Vault, Notes: team docs, uploads, encrypted shared secrets, private notes.
- Automations/Analytics/Settings: workflow logs, reporting, company/team/security/audit settings.
Answer dashboard usage questions with short steps, name the module/path to open, mention required setup when relevant, and avoid inventing unavailable features.
"""


async def _build_history(user_id: str, session_id: str, limit: int = 10) -> list:
    """Rebuild prior chat turns from the DB (the NVIDIA API is stateless)."""
    msgs = await db.ai_chat_messages.find(
        {"user_id": user_id, "session_id": session_id, "kind": "chat"}
    ).sort("created_at", -1).to_list(limit)
    history = []
    for m in reversed(msgs):
        history.append({"role": "user", "content": m["user_message"]})
        history.append({"role": "assistant", "content": m["assistant_message"]})
    return history


async def _stream_and_save(system: str, history: list, text: str, user_id: str, session_id: str, kind: str):
    client = _get_client()
    messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": text}]
    try:
        stream = await client.chat.completions.create(
            model=NVIDIA_MODEL,
            messages=messages,
            stream=True,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider request failed: {str(exc)}")

    async def gen():
        # Recorded here rather than around the whole handler: a streaming
        # response returns before any tokens exist, so timing it outside the
        # generator would log a few milliseconds and no usage.
        from ai_platform import record_assistant

        full = ""
        async with record_assistant(
            _ASSISTANT_KEYS.get(kind, "crm_assistant"), user_id=user_id
        ) as run:
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    full += delta
                    yield f"data: {json.dumps({'delta': delta})}\n\n"
            # Streaming responses carry no usage object, so tokens are
            # approximated from the text. Flagged as an estimate everywhere
            # it surfaces.
            from sdr.agents.base.cost import approximate_tokens
            run.tokens(approximate_tokens(system + text), approximate_tokens(full))
            run.used(model=NVIDIA_MODEL, provider="nvidia")

        await db.ai_chat_messages.insert_one({
            "user_id": user_id, "session_id": session_id, "kind": kind,
            "user_message": text, "assistant_message": full,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _local_assistant_reply(text: str, mode: str, context: str) -> str:
    if mode == "guide":
        return (
            "I can help with AgencyOS modules from the left menu. Open Dashboard for KPIs, Pipeline for leads, "
            "Lead Finder for prospects, Clients for portal access, Projects/Tasks for delivery, Finance for invoices, "
            "and Settings for team/admin setup. The AI provider is temporarily unavailable, so this is a local guide reply."
        )
    lowered = text.lower()
    if "lead" in lowered or "pipeline" in lowered:
        return "Open Pipeline to review leads by stage, then use AI Lead Finder to discover prospects and import them into CRM."
    if "invoice" in lowered or "payment" in lowered or "revenue" in lowered:
        return "Open Finance or Invoices to review revenue, outstanding amounts, payment links, and invoice status."
    return (
        "I can still help with AgencyOS basics while the AI provider is slow/unavailable. Use the left menu to open the module you need, "
        "or ask a specific question about clients, leads, projects, invoices, tasks, or settings."
    )


#: Which entry in the platform AI monitor each `kind` reports as. Keeps these
#: pre-existing features visible alongside the SDR agents without rewriting
#: them - see ai_platform.py.
#: Keys are the `kind` values the existing handlers already pass through.
_ASSISTANT_KEYS = {
    "generate_email": "email_generator",
    "generate_proposal": "proposal_generator",
    "summarize_meeting": "meeting_summarizer",
    "draft_reply": "lead_reply_drafter",
    "chat": "crm_assistant",
    "guide": "crm_assistant",
}


async def _complete_and_save(system: str, history: list, text: str, user_id: str, session_id: str, kind: str, mode: str = "general"):
    messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": text}]
    from ai_platform import record_assistant

    assistant_key = _ASSISTANT_KEYS.get(kind, "crm_assistant")
    async with record_assistant(assistant_key, user_id=user_id) as run:
        return await _complete_inner(
            messages, system, text, user_id, session_id, kind, mode, run
        )


async def _complete_inner(messages, system, text, user_id, session_id, kind, mode, run):
    try:
        client = _get_client()
        resp = await client.chat.completions.create(
            model=NVIDIA_MODEL,
            messages=messages,
            stream=False,
            timeout=25,
        )
        full = resp.choices[0].message.content.strip()
        usage = getattr(resp, "usage", None)
        if usage:
            run.tokens(getattr(usage, "prompt_tokens", 0), getattr(usage, "completion_tokens", 0))
        run.used(model=NVIDIA_MODEL, provider="nvidia")
    except Exception as exc:
        logger_msg = f"AI provider request failed; using local fallback: {str(exc)}"
        import logging
        logging.getLogger(__name__).warning(logger_msg)
        full = _local_assistant_reply(text, mode, system)
    await db.ai_chat_messages.insert_one({
        "user_id": user_id, "session_id": session_id, "kind": kind,
        "user_message": text, "assistant_message": full,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"message": full}


@router.post("/chat")
async def ai_chat(payload: ChatRequest, user: dict = Depends(get_current_user)):
    context = await build_crm_context() if user["role"] != "client" else "No agency data available for client role."
    if payload.mode == "guide":
        system = (
            "You are the AgencyOS Dashboard Guide AI. Help staff understand how to use the dashboard and every module. "
            "Be concise, practical, and step-by-step. If the question involves business data, use the snapshot. "
            "If the user asks for a sensitive action, tell them where to review settings rather than exposing secrets.\n\n"
            + GUIDE_CONTEXT
            + "\nCurrent agency data snapshot:\n"
            + context
        )
    else:
        system = (
            "You are the AgencyOS AI Assistant for an AI automation agency. You can summarize meetings, "
            "generate emails, write proposals, analyze sales, predict revenue trends, answer questions about the CRM, "
            "suggest follow ups and generate reports. Be concise and actionable.\n\nCurrent agency data snapshot:\n" + context
        )
    history = await _build_history(user["id"], payload.session_id)
    return await _stream_and_save(system, history, payload.message, user["id"], payload.session_id, "chat")


@router.post("/chat-json")
async def ai_chat_json(payload: ChatRequest, user: dict = Depends(get_current_user)):
    context = await build_crm_context() if user["role"] != "client" else "No agency data available for client role."
    if payload.mode == "guide":
        system = (
            "You are the AgencyOS Dashboard Guide AI. Help staff understand how to use the dashboard and every module. "
            "Be concise, practical, and step-by-step.\n\n"
            + GUIDE_CONTEXT
            + "\nCurrent agency data snapshot:\n"
            + context
        )
    else:
        system = (
            "You are the AgencyOS AI Assistant for an AI automation agency. Be concise and actionable.\n\n"
            "Current agency data snapshot:\n" + context
        )
    history = await _build_history(user["id"], payload.session_id)
    return await _complete_and_save(system, history, payload.message, user["id"], payload.session_id, "chat", payload.mode)


@router.post("/summarize-meeting")
async def summarize_meeting(payload: SummarizeRequest, user: dict = Depends(require_staff)):
    system = "You are an assistant that writes clear, structured meeting summaries with key decisions, action items, and next steps."
    return await _stream_and_save(system, [], f"Summarize these meeting notes:\n{payload.notes}", user["id"], "summarize", "summarize_meeting")


@router.post("/generate-email")
async def generate_email(payload: GenerateEmailRequest, user: dict = Depends(require_staff)):
    system = f"You write {payload.tone} business emails for an AI automation agency. Return only the email body, no subject line labels."
    prompt = f"Write an email for the purpose: {payload.purpose}."
    if payload.recipient_name:
        prompt += f" Recipient name: {payload.recipient_name}."
    if payload.context:
        prompt += f" Additional context: {payload.context}"
    return await _stream_and_save(system, [], prompt, user["id"], "email", "generate_email")


@router.post("/generate-proposal")
async def generate_proposal(payload: GenerateProposalRequest, user: dict = Depends(require_staff)):
    system = "You are a proposal writer for an AI automation agency. Write clear, persuasive, well-structured proposals in markdown with sections: Overview, Scope of Work, Timeline, Investment, Next Steps."
    prompt = f"Write a proposal for {payload.client_or_lead_name}. Scope: {payload.scope}."
    if payload.budget:
        prompt += f" Budget: {payload.budget}."
    return await _stream_and_save(system, [], prompt, user["id"], "proposal", "generate_proposal")


async def generate_lead_reply(lead: dict) -> str:
    """Non-streaming helper: draft a reply email for an inbound lead. Returns the draft text."""
    client = _get_client()
    contact_name = (lead.get("custom_fields") or {}).get("contact_name") or "there"
    prompt = (
        f"An inbound lead just submitted our agency's contact form.\n"
        f"Contact name: {contact_name}\nCompany: {lead.get('company')}\n"
        f"Budget: {lead.get('revenue') or 'not specified'}\n"
        f"Their message/notes: {lead.get('notes') or '(none)'}\n\n"
        f"Draft a warm, personalized reply email from our agency (Obrinex, an AI automation agency). "
        f"Reference their specific needs, briefly suggest how we can help, and propose a quick intro call. "
        f"Keep it under 150 words. Return ONLY the email body, no subject line."
    )
    resp = await client.chat.completions.create(
        model=NVIDIA_MODEL,
        messages=[{"role": "system", "content": "You write concise, warm, effective sales replies for an AI automation agency."},
                  {"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()


@router.post("/leads/{lead_id}/draft-reply")
async def draft_lead_reply(lead_id: str, user: dict = Depends(require_staff)):
    from bson import ObjectId
    lead = await db.leads.find_one({"_id": ObjectId(lead_id)})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    draft = await generate_lead_reply(lead)
    await db.leads.update_one({"_id": lead["_id"]}, {"$set": {"ai_draft_reply": draft}})
    return {"draft": draft}


@router.get("/history")
async def chat_history(session_id: str = "default", user: dict = Depends(get_current_user)):
    msgs = await db.ai_chat_messages.find({"user_id": user["id"], "session_id": session_id, "kind": "chat"}).sort("created_at", 1).to_list(100)
    for m in msgs:
        m["_id"] = str(m["_id"])
    return msgs
