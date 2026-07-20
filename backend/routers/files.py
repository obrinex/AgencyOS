import os
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from motor.motor_asyncio import AsyncIOMotorGridFSBucket

from database import db, serialize_doc, serialize_list, to_object_id
from auth_utils import get_current_user, log_audit

router = APIRouter(prefix="/api/files", tags=["files"])

UPLOAD_DIR = Path(os.environ.get(
    "FILE_UPLOAD_DIR",
    "/tmp/agencyos_uploads" if os.environ.get("VERCEL") else str(Path(__file__).parent.parent / "uploads"),
))
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_UPLOAD_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "text/plain",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

def get_gridfs_bucket() -> AsyncIOMotorGridFSBucket:
    return AsyncIOMotorGridFSBucket(db, bucket_name="uploads")
ALLOWED_UPLOAD_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".webp", ".txt", ".csv", ".docx", ".xlsx"
}


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
    original_name = Path(file.filename or "upload").name
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=415, detail="File type is not allowed.")
    if file.content_type not in ALLOWED_UPLOAD_MIME_TYPES:
        raise HTTPException(status_code=415, detail="File MIME type is not allowed.")
    stored_name = f"{uuid.uuid4().hex}{ext}"
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large. Maximum upload size is 25 MB.")
    gridfs_bucket = get_gridfs_bucket()
    gridfs_id = await gridfs_bucket.upload_from_stream(
        stored_name,
        content,
        metadata={"original_name": original_name, "mime_type": file.content_type},
    )
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "filename": stored_name, "original_name": original_name, "size": len(content),
        "mime_type": file.content_type, "related_type": related_type, "related_id": related_id,
        "uploaded_by": user["id"], "tags": [], "created_at": now,
        "storage": "gridfs", "gridfs_id": str(gridfs_id),
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
    if doc.get("storage") == "gridfs" and doc.get("gridfs_id"):
        try:
            gridfs_bucket = get_gridfs_bucket()
            stream = await gridfs_bucket.open_download_stream(to_object_id(doc["gridfs_id"]))
        except Exception:
            raise HTTPException(status_code=404, detail="File missing from storage")

        async def chunks():
            while True:
                data = await stream.readchunk()
                if not data:
                    break
                yield data

        return StreamingResponse(
            chunks(),
            media_type=doc.get("mime_type"),
            headers={"Content-Disposition": f'attachment; filename="{doc["original_name"]}"'},
        )
    path = (UPLOAD_DIR / doc["filename"]).resolve()
    if UPLOAD_DIR.resolve() not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid file path")
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(path, filename=doc["original_name"], media_type=doc.get("mime_type"))


@router.delete("/{file_id}")
async def delete_file(file_id: str, user: dict = Depends(get_current_user)):
    doc = await db.files.find_one({"_id": to_object_id(file_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")
    if user["role"] == "client":
        owns_file = doc.get("uploaded_by") == user["id"]
        linked_to_client = doc.get("related_type") == "client" and doc.get("related_id") == user.get("client_id")
        if not (owns_file and linked_to_client):
            raise HTTPException(status_code=403, detail="Not authorized")
    if doc.get("storage") == "gridfs" and doc.get("gridfs_id"):
        try:
            gridfs_bucket = get_gridfs_bucket()
            await gridfs_bucket.delete(to_object_id(doc["gridfs_id"]))
        except Exception:
            pass
    else:
        path = (UPLOAD_DIR / doc["filename"]).resolve()
        if UPLOAD_DIR.resolve() not in path.parents:
            raise HTTPException(status_code=400, detail="Invalid file path")
        if path.exists():
            path.unlink()
    await db.files.delete_one({"_id": doc["_id"]})
    return {"message": "File deleted"}
