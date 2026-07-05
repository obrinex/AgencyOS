from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from database import db, serialize_doc, serialize_list, to_object_id
from auth_utils import get_current_user, require_staff, log_audit

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


class ContractUpdate(BaseModel):
    status: Optional[str] = None
    end_date: Optional[str] = None
    renewal_date: Optional[str] = None
    signed_at: Optional[str] = None


@router.get("/proposals")
async def list_proposals(client_id: Optional[str] = None, lead_id: Optional[str] = None, user: dict = Depends(get_current_user)):
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
    doc.update({"status": "draft", "version": 1, "versions": [], "created_by": user["id"], "created_at": now, "updated_at": now})
    res = await db.proposals.insert_one(doc)
    proposal = await db.proposals.find_one({"_id": res.inserted_id})
    return serialize_doc(proposal)


@router.get("/proposals/{proposal_id}")
async def get_proposal(proposal_id: str, user: dict = Depends(get_current_user)):
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


# ---------------- Contracts ----------------

@router.get("/contracts")
async def list_contracts(client_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {}
    if client_id:
        query["client_id"] = client_id
    contracts = await db.contracts.find(query).sort("created_at", -1).to_list(500)
    return serialize_list(contracts)


@router.post("/contracts")
async def create_contract(payload: ContractCreate, user: dict = Depends(require_staff)):
    now = datetime.now(timezone.utc).isoformat()
    doc = payload.model_dump()
    doc.update({"status": "draft", "signed_at": None, "created_at": now, "updated_at": now})
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
