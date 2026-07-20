import secrets
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from database import db, serialize_doc, serialize_list, to_object_id
from auth_utils import get_current_user, require_staff, log_audit
from email_service import send_proposal_share_email

router = APIRouter(prefix="/api", tags=["documents"])


class ProposalCreate(BaseModel):
    title: str
    lead_id: Optional[str] = None
    client_id: Optional[str] = None
    content: str
    ai_generated: Optional[bool] = False


class ProposalUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None


class ContractCreate(BaseModel):
    title: str
    client_id: str
    file_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    renewal_date: Optional[str] = None
    # Agreement generator fields (all optional — plain contracts still work)
    scope: Optional[str] = None
    payment_terms: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = "INR"
    client_signatory: Optional[str] = None
    agency_signatory: Optional[str] = None
    extra_clauses: Optional[str] = None


class ContractUpdate(BaseModel):
    status: Optional[str] = None
    end_date: Optional[str] = None
    renewal_date: Optional[str] = None
    signed_at: Optional[str] = None


class ShareEmailRequest(BaseModel):
    email: str


class ShareContractRequest(BaseModel):
    email: Optional[str] = None


class SignRequest(BaseModel):
    signature_name: str


@router.get("/proposals")
async def list_proposals(client_id: Optional[str] = None, lead_id: Optional[str] = None, user: dict = Depends(require_staff)):
    query = {}
    if client_id:
        query["client_id"] = client_id
    if lead_id:
        query["lead_id"] = lead_id
    proposals = await db.proposals.find(query).sort("created_at", -1).to_list(500)
    return serialize_list(proposals)


@router.post("/proposals")
async def create_proposal(payload: ProposalCreate, user: dict = Depends(require_staff)):
    now = datetime.now(timezone.utc).isoformat()
    doc = payload.model_dump()
    doc.update({
        "status": "draft", "version": 1, "versions": [], "created_by": user["id"], "created_at": now, "updated_at": now,
        "share_token": secrets.token_urlsafe(16), "signature_name": None, "signed_at": None, "signer_email": None,
    })
    res = await db.proposals.insert_one(doc)
    proposal = await db.proposals.find_one({"_id": res.inserted_id})
    return serialize_doc(proposal)


@router.get("/proposals/{proposal_id}")
async def get_proposal(proposal_id: str, user: dict = Depends(require_staff)):
    proposal = await db.proposals.find_one({"_id": to_object_id(proposal_id)})
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return serialize_doc(proposal)


@router.put("/proposals/{proposal_id}")
async def update_proposal(proposal_id: str, payload: ProposalUpdate, user: dict = Depends(require_staff)):
    proposal = await db.proposals.find_one({"_id": to_object_id(proposal_id)})
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "content" in updates and updates["content"] != proposal.get("content"):
        versions = proposal.get("versions", [])
        versions.append({"content": proposal.get("content"), "version": proposal.get("version", 1), "saved_at": datetime.now(timezone.utc).isoformat()})
        updates["versions"] = versions
        updates["version"] = proposal.get("version", 1) + 1
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.proposals.update_one({"_id": proposal["_id"]}, {"$set": updates})
    updated = await db.proposals.find_one({"_id": proposal["_id"]})
    return serialize_doc(updated)


@router.delete("/proposals/{proposal_id}")
async def delete_proposal(proposal_id: str, user: dict = Depends(require_staff)):
    await db.proposals.delete_one({"_id": to_object_id(proposal_id)})
    return {"message": "Proposal deleted"}


@router.post("/proposals/{proposal_id}/share-email")
async def share_proposal_email(proposal_id: str, payload: ShareEmailRequest, user: dict = Depends(require_staff)):
    proposal = await db.proposals.find_one({"_id": to_object_id(proposal_id)})
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if not proposal.get("share_token"):
        token = secrets.token_urlsafe(16)
        await db.proposals.update_one({"_id": proposal["_id"]}, {"$set": {"share_token": token}})
        proposal["share_token"] = token
    if proposal["status"] == "draft":
        await db.proposals.update_one({"_id": proposal["_id"]}, {"$set": {"status": "sent"}})
    pdf_bytes = None
    try:
        pdf_bytes = await build_proposal_pdf_bytes(proposal)
    except Exception:
        pass  # never block the share email on PDF rendering
    await send_proposal_share_email(payload.email, proposal["title"], proposal["share_token"], pdf_bytes=pdf_bytes)
    await log_audit(user["id"], "share_proposal", "proposal", proposal_id)
    return {"message": "Proposal shared", "share_token": proposal["share_token"]}


# ---------------- Contracts ----------------

@router.get("/contracts")
async def list_contracts(client_id: Optional[str] = None, user: dict = Depends(require_staff)):
    query = {}
    if client_id:
        query["client_id"] = client_id
    contracts = await db.contracts.find(query).sort("created_at", -1).to_list(500)
    return serialize_list(contracts)


@router.post("/contracts")
async def create_contract(payload: ContractCreate, user: dict = Depends(require_staff)):
    now = datetime.now(timezone.utc).isoformat()
    doc = payload.model_dump()
    doc.update({"status": "draft", "signed_at": None, "created_at": now, "updated_at": now,
                "share_token": secrets.token_urlsafe(16), "signature_name": None, "signer_email": None})
    res = await db.contracts.insert_one(doc)
    await log_audit(user["id"], "create_contract", "contract", str(res.inserted_id))
    contract = await db.contracts.find_one({"_id": res.inserted_id})
    return serialize_doc(contract)


@router.put("/contracts/{contract_id}")
async def update_contract(contract_id: str, payload: ContractUpdate, user: dict = Depends(require_staff)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.contracts.update_one({"_id": to_object_id(contract_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Contract not found")
    contract = await db.contracts.find_one({"_id": to_object_id(contract_id)})
    return serialize_doc(contract)


@router.delete("/contracts/{contract_id}")
async def delete_contract(contract_id: str, user: dict = Depends(require_staff)):
    await db.contracts.delete_one({"_id": to_object_id(contract_id)})
    return {"message": "Contract deleted"}


def _proposal_pdf_bytes(proposal: dict, agency_name: str, client_name: str = None) -> bytes:
    """Render a proposal's markdown-ish content into a clean PDF."""
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from xml.sax.saxutils import escape
    import re as _re

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=18, spaceAfter=4)
    meta = ParagraphStyle("meta", parent=styles["Normal"], fontSize=9, textColor=colors.grey)
    sec = ParagraphStyle("sec", parent=styles["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=4)
    sub = ParagraphStyle("sub", parent=styles["Heading3"], fontSize=11, spaceBefore=10, spaceAfter=3)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=15, spaceAfter=4)
    bullet = ParagraphStyle("bullet", parent=body, leftIndent=14, bulletIndent=4)

    def fmt(text):
        text = escape(text)
        text = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        text = _re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
        return text

    story = [
        Paragraph("PROPOSAL", meta),
        Paragraph(fmt(proposal.get("title", "Proposal")), h1),
        Paragraph(f"Prepared by {agency_name}" + (f" for {client_name}" if client_name else "") +
                  f" · {datetime.now(timezone.utc).strftime('%B %d, %Y')}", meta),
        Spacer(1, 6),
        HRFlowable(width="100%", thickness=1, color=colors.black),
        Spacer(1, 8),
    ]
    for line in (proposal.get("content") or "").split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("### "):
            story.append(Paragraph(fmt(s[4:]), sub))
        elif s.startswith("## "):
            story.append(Paragraph(fmt(s[3:]), sec))
        elif s.startswith("# "):
            story.append(Paragraph(fmt(s[2:]), sec))
        elif s.startswith(("- ", "* ")):
            story.append(Paragraph(fmt(s[2:]), bullet, bulletText="•"))
        else:
            story.append(Paragraph(fmt(s), body))

    if proposal.get("status") == "accepted" and proposal.get("signature_name"):
        story += [Spacer(1, 16), HRFlowable(width="100%", thickness=0.5, color=colors.grey),
                  Paragraph(f"Accepted by {proposal['signature_name']} on {(proposal.get('signed_at') or '')[:10]}", meta)]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=20 * mm,
                            title=proposal.get("title", "Proposal"))
    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


async def build_proposal_pdf_bytes(proposal: dict) -> bytes:
    company = await db.company_settings.find_one({"key": "main"})
    client_name = None
    if proposal.get("client_id"):
        client = await db.clients.find_one({"_id": to_object_id(proposal["client_id"])})
        client_name = (client or {}).get("company_name")
    elif proposal.get("lead_id"):
        lead = await db.leads.find_one({"_id": to_object_id(proposal["lead_id"])})
        client_name = (lead or {}).get("company")
    return _proposal_pdf_bytes(proposal, (company or {}).get("company_name") or "Obrinex", client_name)


@router.get("/proposals/{proposal_id}/pdf")
async def proposal_pdf(proposal_id: str, user: dict = Depends(get_current_user)):
    from fastapi.responses import StreamingResponse
    import io
    proposal = await db.proposals.find_one({"_id": to_object_id(proposal_id)})
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    pdf = await build_proposal_pdf_bytes(proposal)
    safe = "".join(ch if ch.isalnum() or ch in "-_ " else "" for ch in proposal.get("title", "proposal")).strip().replace(" ", "_") or "proposal"
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename={safe}.pdf"})


async def build_agreement_pdf_bytes(contract: dict):
    """Render an agreement PDF for a contract document. Returns (bytes, safe_filename)."""
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

    client = await db.clients.find_one({"_id": to_object_id(contract["client_id"])})
    company = await db.company_settings.find_one({"key": "main"})
    agency_name = (company or {}).get("company_name") or "Obrinex"
    client_name = (client or {}).get("company_name") or "Client"

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=18, spaceAfter=4)
    meta = ParagraphStyle("meta", parent=styles["Normal"], fontSize=9, textColor=colors.grey)
    section = ParagraphStyle("section", parent=styles["Heading2"], fontSize=12, spaceBefore=14, spaceAfter=4)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=15)

    symbol = "Rs. " if (contract.get("currency") or "INR") == "INR" else "$"
    story = [
        Paragraph("SERVICE AGREEMENT", h1),
        Paragraph(contract.get("title", ""), styles["Heading3"]),
        Paragraph(f"Generated {datetime.now(timezone.utc).strftime('%B %d, %Y')}", meta),
        Spacer(1, 6),
        HRFlowable(width="100%", thickness=1, color=colors.black),
        Paragraph("1. Parties", section),
        Paragraph(
            f"This Service Agreement (the “Agreement”) is entered into between <b>{agency_name}</b> "
            f"(the “Service Provider”) and <b>{client_name}</b> (the “Client”), collectively the “Parties”.",
            body,
        ),
    ]

    if contract.get("start_date") or contract.get("end_date"):
        term_txt = "This Agreement takes effect on "
        term_txt += f"<b>{(contract.get('start_date') or '')[:10] or 'the date of signature'}</b>"
        if contract.get("end_date"):
            term_txt += f" and remains in force until <b>{contract['end_date'][:10]}</b>, unless terminated earlier in accordance with this Agreement."
        else:
            term_txt += " and remains in force until terminated in accordance with this Agreement."
        story += [Paragraph("2. Term", section), Paragraph(term_txt, body)]
    else:
        story += [Paragraph("2. Term", section), Paragraph("This Agreement takes effect on the date of signature and remains in force until terminated in accordance with this Agreement.", body)]

    story += [Paragraph("3. Scope of Work", section)]
    scope = contract.get("scope") or "The Service Provider will deliver the services described in the accompanying proposal or statement of work agreed between the Parties."
    for para in scope.split("\n"):
        if para.strip():
            story.append(Paragraph(para.strip(), body))

    story += [Paragraph("4. Fees & Payment", section)]
    fee_txt = ""
    if contract.get("amount"):
        fee_txt += f"The Client agrees to pay the Service Provider <b>{symbol}{contract['amount']:,.2f}</b> ({contract.get('currency', 'INR')}). "
    fee_txt += contract.get("payment_terms") or "Invoices are payable within 14 days of issue. Late payments may pause ongoing work."
    story.append(Paragraph(fee_txt, body))

    standard = [
        ("5. Confidentiality", "Each Party agrees to keep confidential all non-public information disclosed by the other Party and to use it solely for the purposes of this Agreement."),
        ("6. Intellectual Property", "Upon receipt of full payment, all deliverables created specifically for the Client under this Agreement are assigned to the Client. The Service Provider retains ownership of its pre-existing tools, frameworks, and know-how."),
        ("7. Termination", "Either Party may terminate this Agreement with 14 days' written notice. The Client remains liable for all work completed up to the effective date of termination."),
        ("8. Limitation of Liability", "Neither Party is liable for indirect or consequential damages. The Service Provider's total liability under this Agreement is limited to the fees paid in the preceding 3 months."),
        ("9. Governing Law", "This Agreement is governed by the laws of India. Disputes will be resolved through good-faith negotiation before any legal proceedings."),
    ]
    for title_txt, txt in standard:
        story += [Paragraph(title_txt, section), Paragraph(txt, body)]

    if contract.get("extra_clauses"):
        story.append(Paragraph("10. Additional Terms", section))
        for para in contract["extra_clauses"].split("\n"):
            if para.strip():
                story.append(Paragraph(para.strip(), body))

    story += [Spacer(1, 24), Paragraph("Signatures", section)]
    signed_note = ""
    if contract.get("status") == "signed" and contract.get("signature_name"):
        signed_note = f"Signed by {contract['signature_name']} on {(contract.get('signed_at') or '')[:10]}"
    sig_data = [
        [Paragraph(f"<b>{agency_name}</b>", body), Paragraph(f"<b>{client_name}</b>", body)],
        [Paragraph("_" * 30, body), Paragraph("_" * 30, body)],
        [Paragraph(f"Name: {contract.get('agency_signatory') or ''}", body), Paragraph(f"Name: {contract.get('client_signatory') or signed_note or ''}", body)],
        [Paragraph("Date:", body), Paragraph(f"Date: {(contract.get('signed_at') or '')[:10]}", body)],
    ]
    sig_table = Table(sig_data, colWidths=[85 * mm, 85 * mm])
    sig_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 1), (-1, 1), 18)]))
    story.append(sig_table)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=20 * mm, title=contract.get("title", "Agreement"))
    doc.build(story)
    buf.seek(0)
    safe_name = "".join(ch if ch.isalnum() or ch in "-_ " else "" for ch in contract.get("title", "agreement")).strip().replace(" ", "_") or "agreement"
    return buf.getvalue(), safe_name


async def build_agreement_pdf(contract: dict):
    """StreamingResponse wrapper around build_agreement_pdf_bytes (used by download endpoints)."""
    import io
    from fastapi.responses import StreamingResponse
    pdf, safe_name = await build_agreement_pdf_bytes(contract)
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename={safe_name}.pdf"})


@router.get("/contracts/{contract_id}/pdf")
async def contract_pdf(contract_id: str, user: dict = Depends(get_current_user)):
    contract = await db.contracts.find_one({"_id": to_object_id(contract_id)})
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    if user["role"] == "client" and contract["client_id"] != user.get("client_id"):
        raise HTTPException(status_code=403, detail="Not authorized")
    return await build_agreement_pdf(contract)


@router.post("/contracts/{contract_id}/share")
async def share_contract(contract_id: str, payload: Optional[ShareContractRequest] = None, user: dict = Depends(require_staff)):
    contract = await db.contracts.find_one({"_id": to_object_id(contract_id)})
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    token = contract.get("share_token")
    if not token:
        token = secrets.token_urlsafe(16)
        await db.contracts.update_one({"_id": contract["_id"]}, {"$set": {"share_token": token}})
    if contract.get("status") == "draft":
        await db.contracts.update_one({"_id": contract["_id"]}, {"$set": {"status": "sent"}})
    if payload and payload.email:
        from email_service import send_agreement_share_email
        pdf_bytes = None
        try:
            pdf_bytes, _ = await build_agreement_pdf_bytes(contract)
        except Exception:
            pass
        await send_agreement_share_email(payload.email, contract["title"], token, pdf_bytes=pdf_bytes)
    await log_audit(user["id"], "share_contract", "contract", contract_id)
    return {"share_token": token}


@router.post("/contracts/{contract_id}/sign")
async def sign_contract_staff(contract_id: str, payload: SignRequest, user: dict = Depends(require_staff)):
    contract = await db.contracts.find_one({"_id": to_object_id(contract_id)})
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    now = datetime.now(timezone.utc).isoformat()
    await db.contracts.update_one({"_id": contract["_id"]}, {"$set": {
        "status": "signed", "signature_name": payload.signature_name, "signed_at": now,
    }})
    await log_audit(user["id"], "sign_contract", "contract", contract_id)
    updated = await db.contracts.find_one({"_id": contract["_id"]})
    return serialize_doc(updated)
