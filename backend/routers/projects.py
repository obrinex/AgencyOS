from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends

from database import db, serialize_doc, serialize_list, to_object_id
from auth_utils import get_current_user, require_staff, log_audit
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["projects"])

PROJECT_STATUSES = ["planning", "onboarding", "development", "automation", "testing", "review", "waiting_client", "completed", "archived"]
TASK_STATUSES = ["todo", "in_progress", "review", "done", "blocked"]


class ProjectCreate(BaseModel):
    name: str
    client_id: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = "planning"
    budget: Optional[float] = 0
    cost: Optional[float] = 0
    members: Optional[List[str]] = []
    deliverables: Optional[List[str]] = []
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    budget: Optional[float] = None
    cost: Optional[float] = None
    members: Optional[List[str]] = None
    deliverables: Optional[List[str]] = None
    risks: Optional[List[str]] = None
    ai_notes: Optional[str] = None
    health: Optional[str] = None
    end_date: Optional[str] = None


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    related_type: Optional[str] = "personal"
    related_id: Optional[str] = None
    assignee_id: Optional[str] = None
    status: Optional[str] = "todo"
    priority: Optional[str] = "medium"
    due_date: Optional[str] = None
    recurring: Optional[str] = "none"
    dependencies: Optional[List[str]] = []


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    assignee_id: Optional[str] = None
    dependencies: Optional[List[str]] = None


class MilestoneCreate(BaseModel):
    title: str
    due_date: Optional[str] = None


@router.get("/projects")
async def list_projects(client_id: Optional[str] = None, status: Optional[str] = None, user: dict = Depends(require_staff)):
    query = {}
    if client_id:
        query["client_id"] = client_id
    if status:
        query["status"] = status
    projects = await db.projects.find(query).sort("created_at", -1).to_list(500)
    result = []
    for p in projects:
        pid = str(p["_id"])
        tasks = await db.tasks.find({"related_type": "project", "related_id": pid}).to_list(500)
        done = len([t for t in tasks if t["status"] == "done"])
        p["progress"] = round((done / len(tasks)) * 100) if tasks else 0
        p["tasks_count"] = len(tasks)
        result.append(serialize_doc(p))
    return result


@router.post("/projects")
async def create_project(payload: ProjectCreate, user: dict = Depends(require_staff)):
    now = datetime.now(timezone.utc).isoformat()
    doc = payload.model_dump()
    doc.update({"risks": [], "ai_notes": "", "health": "green", "created_at": now, "updated_at": now})
    res = await db.projects.insert_one(doc)
    await log_audit(user["id"], "create_project", "project", str(res.inserted_id))
    project = await db.projects.find_one({"_id": res.inserted_id})
    return serialize_doc(project)


@router.get("/projects/{project_id}")
async def get_project(project_id: str, user: dict = Depends(require_staff)):
    project = await db.projects.find_one({"_id": to_object_id(project_id)})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    tasks = await db.tasks.find({"related_type": "project", "related_id": project_id}).to_list(500)
    milestones = await db.milestones.find({"project_id": project_id}).to_list(200)
    client = None
    if project.get("client_id"):
        client = await db.clients.find_one({"_id": to_object_id(project["client_id"])})
    data = serialize_doc(project)
    data["tasks"] = serialize_list(tasks)
    data["milestones"] = serialize_list(milestones)
    data["client"] = serialize_doc(client) if client else None
    data["profit"] = (data.get("budget") or 0) - (data.get("cost") or 0)
    return data


@router.put("/projects/{project_id}")
async def update_project(project_id: str, payload: ProjectUpdate, user: dict = Depends(require_staff)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.projects.update_one({"_id": to_object_id(project_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Project not found")
    project = await db.projects.find_one({"_id": to_object_id(project_id)})
    return serialize_doc(project)


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, user: dict = Depends(require_staff)):
    await db.projects.delete_one({"_id": to_object_id(project_id)})
    await db.tasks.delete_many({"related_type": "project", "related_id": project_id})
    return {"message": "Project deleted"}


@router.post("/projects/{project_id}/milestones")
async def create_milestone(project_id: str, payload: MilestoneCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc.update({"project_id": project_id, "completed": False, "created_at": datetime.now(timezone.utc).isoformat()})
    res = await db.milestones.insert_one(doc)
    milestone = await db.milestones.find_one({"_id": res.inserted_id})
    return serialize_doc(milestone)


@router.patch("/milestones/{milestone_id}")
async def toggle_milestone(milestone_id: str, user: dict = Depends(require_staff)):
    milestone = await db.milestones.find_one({"_id": to_object_id(milestone_id)})
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")
    await db.milestones.update_one({"_id": milestone["_id"]}, {"$set": {"completed": not milestone.get("completed", False)}})
    updated = await db.milestones.find_one({"_id": milestone["_id"]})
    return serialize_doc(updated)


# ---------------- Tasks ----------------

@router.post("/projects/{project_id}/share")
async def share_project(project_id: str, user: dict = Depends(require_staff)):
    import secrets as _secrets
    project = await db.projects.find_one({"_id": to_object_id(project_id)})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    token = project.get("share_token")
    if not token:
        token = _secrets.token_urlsafe(16)
        await db.projects.update_one({"_id": project["_id"]}, {"$set": {"share_token": token}})
    return {"share_token": token}


@router.get("/team/utilization")
async def team_utilization(days: int = 30, user: dict = Depends(require_staff)):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()[:10]
    entries = await db.time_entries.find({"date": {"$gte": since}}).to_list(2000)
    by_user = {}
    for e in entries:
        key = e.get("user_id") or "unknown"
        if key not in by_user:
            by_user[key] = {"user_id": key, "user_name": e.get("user_name") or "Unknown", "hours": 0, "billable_hours": 0, "projects": set()}
        by_user[key]["hours"] += e.get("hours", 0)
        if e.get("billable"):
            by_user[key]["billable_hours"] += e.get("hours", 0)
        by_user[key]["projects"].add(e.get("project_id"))
    result = []
    for u in by_user.values():
        u["projects"] = len(u["projects"])
        result.append(u)
    result.sort(key=lambda x: -x["hours"])
    return {"days": days, "members": result, "total_hours": sum(u["hours"] for u in result)}


# ---------------- Time tracking ----------------

class TimeEntryCreate(BaseModel):
    description: str
    hours: float
    date: Optional[str] = None
    billable: Optional[bool] = True


@router.get("/projects/{project_id}/time")
async def list_time_entries(project_id: str, user: dict = Depends(require_staff)):
    entries = await db.time_entries.find({"project_id": project_id}).sort("date", -1).to_list(500)
    total = sum(e.get("hours", 0) for e in entries)
    billable = sum(e.get("hours", 0) for e in entries if e.get("billable"))
    return {"entries": serialize_list(entries), "total_hours": total, "billable_hours": billable}


@router.post("/projects/{project_id}/time")
async def create_time_entry(project_id: str, payload: TimeEntryCreate, user: dict = Depends(require_staff)):
    project = await db.projects.find_one({"_id": to_object_id(project_id)})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if payload.hours <= 0 or payload.hours > 24:
        raise HTTPException(status_code=400, detail="Hours must be between 0 and 24")
    now = datetime.now(timezone.utc).isoformat()
    doc = payload.model_dump()
    doc.update({
        "project_id": project_id,
        "user_id": user["id"],
        "user_name": user.get("name"),
        "date": payload.date or now[:10],
        "created_at": now,
    })
    res = await db.time_entries.insert_one(doc)
    entry = await db.time_entries.find_one({"_id": res.inserted_id})
    return serialize_doc(entry)


@router.delete("/time/{entry_id}")
async def delete_time_entry(entry_id: str, user: dict = Depends(require_staff)):
    await db.time_entries.delete_one({"_id": to_object_id(entry_id)})
    return {"message": "Time entry deleted"}


@router.get("/tasks")
async def list_tasks(assignee_id: Optional[str] = None, related_type: Optional[str] = None, related_id: Optional[str] = None, status: Optional[str] = None, user: dict = Depends(require_staff)):
    query = {}
    if assignee_id:
        query["assignee_id"] = assignee_id
    if related_type:
        query["related_type"] = related_type
    if related_id:
        query["related_id"] = related_id
    if status:
        query["status"] = status
    tasks = await db.tasks.find(query).sort("due_date", 1).to_list(1000)
    return serialize_list(tasks)


@router.post("/tasks")
async def create_task(payload: TaskCreate, user: dict = Depends(require_staff)):
    now = datetime.now(timezone.utc).isoformat()
    doc = payload.model_dump()
    doc.update({"created_by": user["id"], "created_at": now, "completed_at": None})
    res = await db.tasks.insert_one(doc)
    task = await db.tasks.find_one({"_id": res.inserted_id})
    return serialize_doc(task)


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, payload: TaskUpdate, user: dict = Depends(require_staff)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if updates.get("status") == "done":
        updates["completed_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.tasks.update_one({"_id": to_object_id(task_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    task = await db.tasks.find_one({"_id": to_object_id(task_id)})
    return serialize_doc(task)


@router.patch("/tasks/{task_id}/status")
async def patch_task_status(task_id: str, status: str, user: dict = Depends(require_staff)):
    if status not in TASK_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    updates = {"status": status}
    if status == "done":
        updates["completed_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.tasks.update_one({"_id": to_object_id(task_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    task = await db.tasks.find_one({"_id": to_object_id(task_id)})
    return serialize_doc(task)


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, user: dict = Depends(require_staff)):
    await db.tasks.delete_one({"_id": to_object_id(task_id)})
    return {"message": "Task deleted"}
