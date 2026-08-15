import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from database import db
from auth_utils import get_current_user, require_staff

# The staff assistant. Everything in this router sees the whole agency, so every
# endpoint in it is staff-only.
#
# `/chat`, `/chat-json` and `/history` took `get_current_user`, which is any
# signed-in account — including a client. `build_crm_context()` was skipped for
# the client role, so the business snapshot never leaked, but `mode: "guide"`
# still returned GUIDE_CONTEXT: a full description of the internal CRM's modules
# to anyone with a portal login who sent the right JSON. Clients and members now
# have their own assistant at /api/me/assistant, scoped to their own data.

router = APIRouter(prefix="/api/ai", tags=["ai"])

def _select_provider():
    """(client, model, provider_key) from the platform provider chain.

    One registry, one fallback order, one place to rotate a key. With only
    NVIDIA_API_KEY set the chain resolves to NVIDIA.
    """
    import llm_providers as registry

    chain = registry.chain()
    if not chain:
        raise HTTPException(
            status_code=503,
            detail="AI is not configured. Set one of: "
                   + ", ".join(p["api_key_env"] for p in registry.describe()),
        )
    key, make_client, model = chain[0]
    return make_client(), model, key


def response_text(resp) -> str:
    """The assistant's text, or a 502 saying there wasn't any.

    `message.content` is None whenever a provider *filters* a response rather
    than answering it - a normal outcome, not an error, and one Gemini's
    safety filters produce far more readily than the Llama deployments this
    ran on before. The prompts here are cold sales copy naming a real
    business, which is exactly the shape that trips a classifier.

    `.strip()` on None is an AttributeError and a 500 with no explanation.

    Failing loudly beats the alternative: an empty string stored as
    `ai_draft_reply` reads as a successful draft right up until someone
    opens it.
    """
    choices = getattr(resp, "choices", None) or []
    text = ((choices[0].message.content or "") if choices else "").strip()
    if not text:
        raise HTTPException(
            status_code=502,
            detail="The AI provider returned no text - the response was most "
                   "likely filtered. Retry, or reorder providers with "
                   "LLM_PROVIDERS.",
        )
    return text


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
    # Soft-deleted leads excluded: this text goes into the model's prompt, and
    # describing a deleted lead as current is a wrong answer with a confident
    # tone attached.
    leads = await db.leads.find({"deleted_at": None}).sort("updated_at", -1).to_list(20)
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
- There is no autonomous outreach system. Every AI feature here waits for a
  button press: the AI Assistant, the email and proposal writers, the meeting
  summariser, the Lead Finder's "AI Pitch". Nothing sends on a schedule and
  nothing runs unattended. If someone asks about automated outreach, campaigns,
  sequences, an agent monitor or an SDR, say plainly that the feature is not in
  the product - do not guess at a page for it.
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
    client, model, provider_key = _select_provider()
    messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": text}]
    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider request failed: {str(exc)}")

    async def gen():
        # Per-call run recording used to wrap this loop, writing token counts
        # and estimated cost to the agent monitor. That monitor belonged to the
        # agent layer and went with it; the transcript written below is now the
        # only record that a call happened.
        full = ""
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                full += delta
                yield f"data: {json.dumps({'delta': delta})}\n\n"

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


async def _complete_and_save(system: str, history: list, text: str, user_id: str, session_id: str, kind: str, mode: str = "general"):
    messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": text}]
    return await _complete_inner(
        messages, system, text, user_id, session_id, kind, mode
    )


async def _complete_inner(messages, system, text, user_id, session_id, kind, mode):
    try:
        client, model, provider_key = _select_provider()
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=False,
            timeout=25,
        )
        full = response_text(resp)
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
async def ai_chat(payload: ChatRequest, user: dict = Depends(require_staff)):
    context = await build_crm_context()
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
async def ai_chat_json(payload: ChatRequest, user: dict = Depends(require_staff)):
    context = await build_crm_context()
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
    client, model, _ = _select_provider()
    contact_name = (lead.get("custom_fields") or {}).get("contact_name") or "there"
    prompt = (
        f"An inbound lead just submitted our agency's contact form.\n"
        f"Contact name: {contact_name}\nCompany: {lead.get('company')}\n"
        # Currency-stamped: an unlabelled number invites the model to guess,
        # and it guesses dollars.
        f"Budget: {('INR %s' % format(lead['revenue'], ',.0f')) if lead.get('revenue') else 'not specified'}\n"
        f"Their message/notes: {lead.get('notes') or '(none)'}\n\n"
        f"Draft a warm, personalized reply email from our agency (Obrinex, an AI automation agency). "
        f"Reference their specific needs, briefly suggest how we can help, and propose a quick intro call. "
        f"Keep it under 150 words. Return ONLY the email body, no subject line."
    )
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": "You write concise, warm, effective sales replies for an AI automation agency."},
                  {"role": "user", "content": prompt}],
    )
    return response_text(resp)


@router.post("/leads/{lead_id}/draft-reply")
async def draft_lead_reply(lead_id: str, user: dict = Depends(require_staff)):
    # to_object_id, not a bare ObjectId(): a malformed id raised InvalidId out
    # of bson and surfaced as a 500. Every other lead lookup in the app uses
    # this helper, which turns it into the 404 it actually is.
    from database import to_object_id
    lead = await db.leads.find_one({"_id": to_object_id(lead_id), "deleted_at": None})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    draft = await generate_lead_reply(lead)
    await db.leads.update_one({"_id": lead["_id"]}, {"$set": {"ai_draft_reply": draft}})
    return {"draft": draft}


@router.get("/history")
async def chat_history(session_id: str = "default", user: dict = Depends(require_staff)):
    msgs = await db.ai_chat_messages.find({"user_id": user["id"], "session_id": session_id, "kind": "chat"}).sort("created_at", 1).to_list(100)
    for m in msgs:
        m["_id"] = str(m["_id"])
    return msgs
