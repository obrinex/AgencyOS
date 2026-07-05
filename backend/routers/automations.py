from fastapi import APIRouter, Depends
from database import db, serialize_list
from auth_utils import require_staff

router = APIRouter(prefix="/api/automations", tags=["automations"])


@router.get("/logs")
async def list_automation_logs(trigger: str = None, user: dict = Depends(require_staff)):
    query = {}
    if trigger:
        query["trigger"] = trigger
    logs = await db.automation_logs.find(query).sort("created_at", -1).to_list(200)
    return serialize_list(logs)
