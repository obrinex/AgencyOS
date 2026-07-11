from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from database import db, serialize_doc, to_object_id

router = APIRouter(prefix="/api/public", tags=["public"])


class ProposalSignRequest(BaseModel):
    signature_name: str
    signer_email: EmailStr
    accept: bool = True


@router.get("/proposals/{token}")
async def get_public_proposal(token: str):
    proposal = await db.proposals.find_one({"share_token": token})
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal["status"] == "sent":
        await db.proposals.update_one({"_id": proposal["_id"]}, {"$set": {"status": "viewed"}})
        proposal["status"] = "viewed"
    data = serialize_doc(proposal)
    data.pop("versions", None)
    return data


# ---------------- Public project status ----------------

@router.get("/projects/{token}")
async def get_public_project_status(token: str):
    project = await db.projects.find_one({"share_token": token})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    pid = str(project["_id"])
    milestones = await db.milestones.find({"project_id": pid}).to_list(100)
    tasks = await db.tasks.find({"related_type": "project", "related_id": pid}).to_list(500)
    company = await db.company_settings.find_one({"key": "main"})
    client = await db.clients.find_one({"_id": to_object_id(project["client_id"])}) if project.get("client_id") else None

    done_tasks = len([t for t in tasks if t.get("status") == "done"])
    done_milestones = len([m for m in milestones if m.get("completed")])
    total_units = len(tasks) + len(milestones)
    done_units = done_tasks + done_milestones
    progress = round(done_units / total_units * 100) if total_units else 0

    return {
        "name": project.get("name"),
        "status": project.get("status"),
        "health": project.get("health"),
        "description": project.get("description"),
        "start_date": project.get("start_date"),
        "end_date": project.get("end_date"),
        "updated_at": project.get("updated_at"),
        "progress": progress,
        "agency_name": (company or {}).get("company_name") or "Obrinex",
        "client_name": (client or {}).get("company_name"),
        "milestones": [{"title": m.get("title"), "completed": bool(m.get("completed"))} for m in milestones],
        "tasks_summary": {
            "total": len(tasks), "done": done_tasks,
            "in_progress": len([t for t in tasks if t.get("status") == "in_progress"]),
        },
        "recent_completed": [t.get("title") for t in tasks if t.get("status") == "done"][-5:],
    }


# ---------------- Public agreements (e-sign) ----------------

@router.get("/agreements/{token}")
async def get_public_agreement(token: str):
    contract = await db.contracts.find_one({"share_token": token})
    if not contract:
        raise HTTPException(status_code=404, detail="Agreement not found")
    client = await db.clients.find_one({"_id": to_object_id(contract["client_id"])})
    company = await db.company_settings.find_one({"key": "main"})
    data = serialize_doc(contract)
    data["client_name"] = (client or {}).get("company_name") or "Client"
    data["agency_name"] = (company or {}).get("company_name") or "Obrinex"
    return data


@router.post("/agreements/{token}/sign")
async def sign_public_agreement(token: str, payload: ProposalSignRequest):
    contract = await db.contracts.find_one({"share_token": token})
    if not contract:
        raise HTTPException(status_code=404, detail="Agreement not found")
    if contract.get("status") == "signed":
        raise HTTPException(status_code=400, detail="Agreement already signed")
    now = datetime.now(timezone.utc).isoformat()
    await db.contracts.update_one({"_id": contract["_id"]}, {"$set": {
        "status": "signed", "signature_name": payload.signature_name,
        "signer_email": payload.signer_email, "signed_at": now,
    }})
    admins = await db.users.find({"role": "admin"}).to_list(20)
    for a in admins:
        await db.notifications.insert_one({
            "user_id": str(a["_id"]), "type": "contract_signed",
            "title": "Agreement signed",
            "message": f"{payload.signature_name} signed \"{contract['title']}\".",
            "link": "/contracts", "read": False, "created_at": now,
        })
    updated = await db.contracts.find_one({"_id": contract["_id"]})
    return serialize_doc(updated)


@router.get("/agreements/{token}/pdf")
async def public_agreement_pdf(token: str):
    contract = await db.contracts.find_one({"share_token": token})
    if not contract:
        raise HTTPException(status_code=404, detail="Agreement not found")
    from routers.documents import build_agreement_pdf
    return await build_agreement_pdf(contract)


@router.post("/proposals/{token}/sign")
async def sign_public_proposal(token: str, payload: ProposalSignRequest):
    proposal = await db.proposals.find_one({"share_token": token})
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal["status"] in ("accepted", "rejected"):
        raise HTTPException(status_code=400, detail="Proposal already finalized")
    now = datetime.now(timezone.utc).isoformat()
    new_status = "accepted" if payload.accept else "rejected"
    await db.proposals.update_one({"_id": proposal["_id"]}, {"$set": {
        "status": new_status, "signature_name": payload.signature_name,
        "signer_email": payload.signer_email, "signed_at": now,
    }})
    updated = await db.proposals.find_one({"_id": proposal["_id"]})
    return serialize_doc(updated)
