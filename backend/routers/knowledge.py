from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from database import db, serialize_doc, serialize_list, to_object_id
from auth_utils import require_staff

router = APIRouter(prefix="/api/kb", tags=["knowledge_base"])


class ArticleCreate(BaseModel):
    title: str
    content: str
    category: str
    tags: Optional[List[str]] = []


class ArticleUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None


@router.get("")
async def list_articles(category: Optional[str] = None, search: Optional[str] = None, user: dict = Depends(require_staff)):
    query = {}
    if category:
        query["category"] = category
    if search:
        query["title"] = {"$regex": search, "$options": "i"}
    articles = await db.kb_articles.find(query).sort("created_at", -1).to_list(500)
    return serialize_list(articles)


@router.post("")
async def create_article(payload: ArticleCreate, user: dict = Depends(require_staff)):
    now = datetime.now(timezone.utc).isoformat()
    doc = payload.model_dump()
    doc.update({"created_by": user["id"], "created_at": now, "updated_at": now})
    res = await db.kb_articles.insert_one(doc)
    article = await db.kb_articles.find_one({"_id": res.inserted_id})
    return serialize_doc(article)


@router.get("/{article_id}")
async def get_article(article_id: str, user: dict = Depends(require_staff)):
    article = await db.kb_articles.find_one({"_id": to_object_id(article_id)})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return serialize_doc(article)


@router.put("/{article_id}")
async def update_article(article_id: str, payload: ArticleUpdate, user: dict = Depends(require_staff)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.kb_articles.update_one({"_id": to_object_id(article_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Article not found")
    article = await db.kb_articles.find_one({"_id": to_object_id(article_id)})
    return serialize_doc(article)


@router.delete("/{article_id}")
async def delete_article(article_id: str, user: dict = Depends(require_staff)):
    await db.kb_articles.delete_one({"_id": to_object_id(article_id)})
    return {"message": "Article deleted"}
