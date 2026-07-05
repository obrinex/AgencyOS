import os
import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from database import db
from auth_utils import get_current_user, require_staff

from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone

router = APIRouter(prefix="/api/ai", tags=["ai"])


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"


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
    lines = [f"Total clients: {len(clients)}", f"Paid revenue: ${revenue:,.2f}", f"Outstanding: ${outstanding:,.2f}"]
    lines.append("Recent leads: " + ", ".join(f"{ld.get('company')} ({ld.get('stage')})" for ld in leads[:10]))
    return "\n".join(lines)


def _get_chat(session_id: str, system_message: str) -> LlmChat:
    return LlmChat(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        session_id=session_id,
        system_message=system_message,
    ).with_model("openai", "gpt-5.4")


async def _stream_and_save(chat: LlmChat, text: str, user_id: str, session_id: str, kind: str):
    async def gen():
        full = ""
        async for event in chat.stream_message(UserMessage(text=text)):
            if isinstance(event, TextDelta):
                full += event.content
                yield f"data: {json.dumps({'delta': event.content})}\n\n"
            elif isinstance(event, StreamDone):
                break
        await db.ai_chat_messages.insert_one({
            "user_id": user_id, "session_id": session_id, "kind": kind,
            "user_message": text, "assistant_message": full,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/chat")
async def ai_chat(payload: ChatRequest, user: dict = Depends(get_current_user)):
    context = await build_crm_context() if user["role"] != "client" else "No agency data available for client role."
    system = (
        "You are the AgencyOS AI Assistant for an AI automation agency. You can summarize meetings, "
        "generate emails, write proposals, analyze sales, predict revenue trends, answer questions about the CRM, "
        "suggest follow ups and generate reports. Be concise and actionable.\n\nCurrent agency data snapshot:\n" + context
    )
    chat = _get_chat(f"assistant-{user['id']}-{payload.session_id}", system)
    return await _stream_and_save(chat, payload.message, user["id"], payload.session_id, "chat")


@router.post("/summarize-meeting")
async def summarize_meeting(payload: SummarizeRequest, user: dict = Depends(require_staff)):
    system = "You are an assistant that writes clear, structured meeting summaries with key decisions, action items, and next steps."
    chat = _get_chat(f"summarize-{user['id']}", system)
    return await _stream_and_save(chat, f"Summarize these meeting notes:\n{payload.notes}", user["id"], "summarize", "summarize_meeting")


@router.post("/generate-email")
async def generate_email(payload: GenerateEmailRequest, user: dict = Depends(require_staff)):
    system = f"You write {payload.tone} business emails for an AI automation agency. Return only the email body, no subject line labels."
    prompt = f"Write an email for the purpose: {payload.purpose}."
    if payload.recipient_name:
        prompt += f" Recipient name: {payload.recipient_name}."
    if payload.context:
        prompt += f" Additional context: {payload.context}"
    chat = _get_chat(f"email-{user['id']}", system)
    return await _stream_and_save(chat, prompt, user["id"], "email", "generate_email")


@router.post("/generate-proposal")
async def generate_proposal(payload: GenerateProposalRequest, user: dict = Depends(require_staff)):
    system = "You are a proposal writer for an AI automation agency. Write clear, persuasive, well-structured proposals in markdown with sections: Overview, Scope of Work, Timeline, Investment, Next Steps."
    prompt = f"Write a proposal for {payload.client_or_lead_name}. Scope: {payload.scope}."
    if payload.budget:
        prompt += f" Budget: {payload.budget}."
    chat = _get_chat(f"proposal-{user['id']}", system)
    return await _stream_and_save(chat, prompt, user["id"], "proposal", "generate_proposal")


@router.get("/history")
async def chat_history(session_id: str = "default", user: dict = Depends(get_current_user)):
    msgs = await db.ai_chat_messages.find({"user_id": user["id"], "session_id": session_id, "kind": "chat"}).sort("created_at", 1).to_list(100)
    for m in msgs:
        m["_id"] = str(m["_id"])
    return msgs
