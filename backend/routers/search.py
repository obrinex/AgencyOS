from fastapi import APIRouter, Depends
from database import db, serialize_list
from auth_utils import get_current_user

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
async def global_search(q: str, user: dict = Depends(get_current_user)):
    if not q or len(q) < 1:
        return {"leads": [], "clients": [], "projects": [], "tasks": [], "invoices": [], "contacts": [], "kb_articles": []}
    rx = {"$regex": q, "$options": "i"}
    if user["role"] == "client":
        client_id = user.get("client_id")
        projects = await db.projects.find({"client_id": client_id, "name": rx}).to_list(20)
        invoices = await db.invoices.find({"client_id": client_id, "invoice_number": rx}).to_list(20)
        return {"leads": [], "clients": [], "projects": serialize_list(projects), "tasks": [], "invoices": serialize_list(invoices), "contacts": [], "kb_articles": []}

    leads = await db.leads.find({"company": rx}).to_list(10)
    clients = await db.clients.find({"company_name": rx}).to_list(10)
    projects = await db.projects.find({"name": rx}).to_list(10)
    tasks = await db.tasks.find({"title": rx}).to_list(10)
    invoices = await db.invoices.find({"invoice_number": rx}).to_list(10)
    contacts = await db.contacts.find({"name": rx}).to_list(10)
    kb_articles = await db.kb_articles.find({"title": rx}).to_list(10)

    return {
        "leads": serialize_list(leads), "clients": serialize_list(clients),
        "projects": serialize_list(projects), "tasks": serialize_list(tasks),
        "invoices": serialize_list(invoices), "contacts": serialize_list(contacts),
        "kb_articles": serialize_list(kb_articles),
    }
