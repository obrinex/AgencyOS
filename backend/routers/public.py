from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from database import db, serialize_doc

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
