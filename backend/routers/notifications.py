from fastapi import APIRouter, Depends
from database import db, serialize_doc, serialize_list, to_object_id
from auth_utils import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(user: dict = Depends(get_current_user)):
    notifs = await db.notifications.find({"user_id": user["id"]}).sort("created_at", -1).to_list(100)
    return serialize_list(notifs)


@router.get("/unread-count")
async def unread_count(user: dict = Depends(get_current_user)):
    count = await db.notifications.count_documents({"user_id": user["id"], "read": False})
    return {"count": count}


@router.patch("/{notif_id}/read")
async def mark_read(notif_id: str, user: dict = Depends(get_current_user)):
    await db.notifications.update_one({"_id": to_object_id(notif_id), "user_id": user["id"]}, {"$set": {"read": True}})
    return {"message": "Marked as read"}


@router.patch("/read-all")
async def mark_all_read(user: dict = Depends(get_current_user)):
    await db.notifications.update_many({"user_id": user["id"]}, {"$set": {"read": True}})
    return {"message": "All marked as read"}
