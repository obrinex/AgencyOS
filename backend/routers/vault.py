import os
from datetime import datetime, timezone
from typing import Optional
from cryptography.fernet import Fernet
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from database import db, serialize_doc, serialize_list, to_object_id
from auth_utils import get_current_user, require_staff, require_admin, log_audit, require_module
require_vault = require_module("vault")

router = APIRouter(prefix="/api/vault", tags=["vault"])


def get_cipher():
    return Fernet(os.environ["VAULT_ENCRYPTION_KEY"].encode())


class VaultEntryCreate(BaseModel):
    title: str
    type: str
    username: Optional[str] = None
    password: Optional[str] = None
    url: Optional[str] = None
    notes: Optional[str] = None
    client_id: Optional[str] = None


class VaultEntryUpdate(BaseModel):
    title: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    url: Optional[str] = None
    notes: Optional[str] = None


@router.get("")
async def list_entries(client_id: Optional[str] = None, user: dict = Depends(require_vault)):
    query = {}
    if client_id:
        query["client_id"] = client_id
    entries = await db.vault_entries.find(query).sort("created_at", -1).to_list(500)
    result = []
    for e in entries:
        e = serialize_doc(e)
        e.pop("encrypted_password", None)
        e["has_password"] = bool(e.get("has_password"))
        result.append(e)
    return result


@router.post("")
async def create_entry(payload: VaultEntryCreate, user: dict = Depends(require_vault)):
    cipher = get_cipher()
    now = datetime.now(timezone.utc).isoformat()
    doc = payload.model_dump()
    pwd = doc.pop("password", None)
    doc["encrypted_password"] = cipher.encrypt(pwd.encode()).decode() if pwd else None
    doc["has_password"] = bool(pwd)
    doc.update({"created_by": user["id"], "created_at": now, "updated_at": now})
    res = await db.vault_entries.insert_one(doc)
    await log_audit(user["id"], "create_vault_entry", "vault_entry", str(res.inserted_id))
    entry = await db.vault_entries.find_one({"_id": res.inserted_id})
    entry = serialize_doc(entry)
    entry.pop("encrypted_password", None)
    return entry


@router.put("/{entry_id}")
async def update_entry(entry_id: str, payload: VaultEntryUpdate, user: dict = Depends(require_vault)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None and k != "password"}
    if payload.password:
        cipher = get_cipher()
        updates["encrypted_password"] = cipher.encrypt(payload.password.encode()).decode()
        updates["has_password"] = True
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.vault_entries.update_one({"_id": to_object_id(entry_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Entry not found")
    entry = await db.vault_entries.find_one({"_id": to_object_id(entry_id)})
    entry = serialize_doc(entry)
    entry.pop("encrypted_password", None)
    return entry


@router.post("/{entry_id}/reveal")
async def reveal_password(entry_id: str, user: dict = Depends(require_vault)):
    entry = await db.vault_entries.find_one({"_id": to_object_id(entry_id)})
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if not entry.get("encrypted_password"):
        return {"password": None}
    cipher = get_cipher()
    decrypted = cipher.decrypt(entry["encrypted_password"].encode()).decode()
    await log_audit(user["id"], "reveal_vault_password", "vault_entry", entry_id)
    return {"password": decrypted}


@router.delete("/{entry_id}")
async def delete_entry(entry_id: str, user: dict = Depends(require_admin)):
    await db.vault_entries.delete_one({"_id": to_object_id(entry_id)})
    return {"message": "Entry deleted"}
