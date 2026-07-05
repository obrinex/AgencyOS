import os
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import FileResponse

from database import db, serialize_doc, serialize_list, to_object_id
from auth_utils import get_current_user, log_audit

router = APIRouter(prefix="/api/files", tags=["files"])

UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


@router.get("")
async def list_files(related_type: Optional[str] = None, related_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {}
    if related_type:
        query["related_type"] = related_type
    if related_id:
        query["related_id"] = related_id
    if user["role"] == "client":
        query["related_type"] = "client"
        query["related_id"] = user.get("client_id")
    files = await db.files.find(query).sort("created_at", -1).to_list(500)
    return serialize_list(files)


@router.post("/upload")
async def upload_file(related_type: str, related_id: Optional[str] = None, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if user["role"] == "client":
        related_type = "client"
        related_id = user.get("client_id")
    ext = Path(file.filename).suffix
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / stored_name
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "filename": stored_name, "original_name": file.filename, "size": len(content),
        "mime_type": file.content_type, "related_type": related_type, "related_id": related_id,
        "uploaded_by": user["id"], "tags": [], "created_at": now,
    }
    res = await db.files.insert_one(doc)
    await log_audit(user["id"], "upload_file", "file", str(res.inserted_id))
    saved = await db.files.find_one({"_id": res.inserted_id})
    return serialize_doc(saved)


@router.get("/{file_id}/download")
async def download_file(file_id: str, user: dict = Depends(get_current_user)):
    doc = await db.files.find_one({"_id": to_object_id(file_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")
    if user["role"] == "client" and (doc.get("related_type") != "client" or doc.get("related_id") != user.get("client_id")):
        raise HTTPException(status_code=403, detail="Not authorized")
    path = UPLOAD_DIR / doc["filename"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(path, filename=doc["original_name"], media_type=doc.get("mime_type"))


@router.delete("/{file_id}")
async def delete_file(file_id: str, user: dict = Depends(get_current_user)):
    doc = await db.files.find_one({"_id": to_object_id(file_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")
    path = UPLOAD_DIR / doc["filename"]
    if path.exists():
        path.unlink()
    await db.files.delete_one({"_id": doc["_id"]})
    return {"message": "File deleted"}
