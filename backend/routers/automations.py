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


@router.post("/cron/sdr", dependencies=[Depends(require_cron_secret)])
@router.get("/cron/sdr", dependencies=[Depends(require_cron_secret)])
async def drain_sdr_jobs():
    """Drain the AI SDR job queue.

    Designed to be hit frequently (every few minutes) by an external pinger,
    because Vercel Hobby crons only fire daily and an SDR that acts once a day
    is not autonomous. The handler is idempotent and time-boxed: it claims due
    jobs, works until its budget is nearly spent, and returns. Whatever it
    does not reach is simply picked up next time. See docs/ai-sdr/adr/0003.

    Deliberately NOT registered in vercel.json: the Hobby plan caps the number
    of cron jobs, and the two existing ones (payment reconciliation and
    reminders) matter more than a once-daily drain. The external pinger is the
    real scheduler. Add an entry here on Pro if a platform-native safety net
    is wanted.

    Kept here rather than in routers/sdr.py so every scheduled entrypoint in
    this codebase lives behind the same cron-secret guard.
    """
    from sdr.repositories import settings as sdr_settings
    from sdr.services import jobs as sdr_jobs

    settings = await sdr_settings.get_settings()
    if not settings["module_enabled"]:
        return {"message": "AI SDR module is disabled", "processed": 0}
    if settings["kill_switch"]:
        return {"message": "AI SDR kill switch is on", "processed": 0}

    # The campaign heartbeat runs first, so work it enqueues (drafts due,
    # sends due) is drained in the same invocation rather than waiting a
    # full pinger interval.
    from sdr.services import campaigns as sdr_campaigns
    tick_report = await sdr_campaigns.tick()

    result = await sdr_jobs.drain()
    result["tick"] = tick_report
    await db.automation_logs.insert_one({
        "trigger": "sdr_drain",
        "processed": result["processed"],
        "succeeded": result["succeeded"],
        "failed": result["failed"],
        "dead_lettered": result["dead_lettered"],
        "duration_ms": result["duration_ms"],
        "created_at": now_iso(),
    })
    return result
