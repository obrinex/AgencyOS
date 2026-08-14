import os
from fastapi import APIRouter, Depends, Header, HTTPException
from database import db, now_iso, serialize_list
from auth_utils import require_staff
from reminders import (_process_due_reminders, chase_overdue_invoices, generate_recurring_invoices,
                       reconcile_cashfree_payments, send_daily_digest)

router = APIRouter(prefix="/api/automations", tags=["automations"])


@router.get("/logs")
async def list_automation_logs(trigger: str = None, user: dict = Depends(require_staff)):
    query = {}
    if trigger:
        query["trigger"] = trigger
    logs = await db.automation_logs.find(query).sort("created_at", -1).to_list(200)
    return serialize_list(logs)


def require_cron_secret(x_cron_secret: str = Header(default=""), authorization: str = Header(default="")):
    """Accepts the secret as either `x-cron-secret: <secret>` (external cron services)
    or `Authorization: Bearer <secret>` (how Vercel Cron invokes endpoints)."""
    expected = os.environ.get("CRON_SECRET")
    bearer = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not expected or (x_cron_secret != expected and bearer != expected):
        raise HTTPException(status_code=401, detail="Invalid cron secret")


@router.post("/cron/reminders", dependencies=[Depends(require_cron_secret)])
@router.get("/cron/reminders", dependencies=[Depends(require_cron_secret)])
async def run_due_reminders():
    """Also reconciles Cashfree payments.

    Production runs with RUN_BACKGROUND_LOOPS=false, so the in-process sweep
    never fires there. Without this, a webhook that failed to deliver would
    leave a genuinely paid invoice outstanding forever.
    """
    await _process_due_reminders()
    await reconcile_cashfree_payments()
    return {"message": "Reminder job completed"}


@router.post("/cron/daily", dependencies=[Depends(require_cron_secret)])
@router.get("/cron/daily", dependencies=[Depends(require_cron_secret)])
async def run_daily_jobs():
    # Reconcile here too: on the Hobby plan each cron may only run daily, so
    # both jobs sweep for lost payment webhooks to halve the worst-case delay.
    await reconcile_cashfree_payments()
    overdue = await chase_overdue_invoices()
    recurring = await generate_recurring_invoices()
    await send_daily_digest()
    return {
        "message": "Daily automation job completed",
        "overdue_reminders": len(overdue),
        "recurring_invoices": len(recurring),
    }
