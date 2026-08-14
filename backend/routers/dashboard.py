from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends

from database import db, serialize_doc, serialize_list
from auth_utils import require_staff
from finance_utils import to_base
from lead_stages import CLOSED_LOST, FUNNEL_ORDER, WON

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
async def dashboard_stats(user: dict = Depends(require_staff)):
    invoices = await db.invoices.find({}).to_list(5000)
    expenses = await db.expenses.find({}).to_list(5000)
    # Soft-deleted leads are excluded here as they are everywhere else. Without
    # this the funnel, the pipeline value and the conversion rate all counted
    # leads the SDR module had already deleted.
    leads = await db.leads.find({"deleted_at": None}).to_list(5000)
    projects = await db.projects.find({}).to_list(1000)
    tasks = await db.tasks.find({}).to_list(2000)
    meetings = await db.meetings.find({}).to_list(500)

    revenue = sum(to_base(i["total"], i.get("conversion_rate")) for i in invoices if i["status"] == "paid")
    outstanding = sum(to_base(i["total"], i.get("conversion_rate")) for i in invoices if i["status"] in ("sent", "overdue", "partial", "viewed"))
    total_expenses = sum(to_base(e["amount"], e.get("conversion_rate")) for e in expenses)
    profit = revenue - total_expenses
    mrr = sum(to_base(i["total"], i.get("conversion_rate")) for i in invoices if i.get("is_recurring") and i["status"] == "paid")
    arr = mrr * 12

    # `cold` and `archived` count as closed now that they are in CLOSED_LOST.
    # Both were previously counted as live pipeline, which overstated its value
    # by every deal that had gone quiet or been shelved.
    active_leads = [ld for ld in leads if ld.get("stage") not in (WON,) + CLOSED_LOST]
    pipeline_value = sum(ld.get("revenue") or 0 for ld in active_leads)
    won_leads = [ld for ld in leads if ld.get("stage") == WON]
    total_closed = len(won_leads) + len([ld for ld in leads if ld.get("stage") in CLOSED_LOST])
    conversion_rate = round((len(won_leads) / total_closed) * 100, 1) if total_closed else 0
    avg_deal_size = round(sum(ld.get("revenue") or 0 for ld in won_leads) / len(won_leads), 2) if won_leads else 0

    funnel = [{"stage": s, "count": len([ld for ld in leads if ld.get("stage") == s])} for s in FUNNEL_ORDER]

    now = datetime.now(timezone.utc)
    today_str = now.date().isoformat()
    upcoming_meetings = [m for m in meetings if m.get("start_time") and m["start_time"][:10] >= today_str and m["status"] != "cancelled"]
    upcoming_meetings.sort(key=lambda m: m["start_time"])

    todays_tasks = [t for t in tasks if t.get("due_date") and t["due_date"][:10] == today_str and t["status"] != "done"]
    active_projects = [p for p in projects if p["status"] not in ("completed", "archived")]
    at_risk_projects = [p for p in active_projects if p.get("health") == "red" or (p.get("end_date") and p["end_date"] < now.isoformat())]

    return {
        "revenue": revenue, "mrr": mrr, "arr": arr, "outstanding": outstanding,
        "profit": profit, "expenses": total_expenses,
        "pipeline_value": pipeline_value, "conversion_rate": conversion_rate, "avg_deal_size": avg_deal_size,
        "sales_funnel": funnel,
        "upcoming_meetings_count": len(upcoming_meetings), "upcoming_meetings": serialize_list(upcoming_meetings[:5]),
        "todays_tasks_count": len(todays_tasks), "todays_tasks": serialize_list(todays_tasks[:5]),
        "active_projects_count": len(active_projects), "at_risk_projects_count": len(at_risk_projects),
        "total_leads": len(leads), "total_clients": await db.clients.count_documents({}),
    }


@router.get("/activity")
async def recent_activity(limit: int = 20, user: dict = Depends(require_staff)):
    activities = await db.lead_activities.find({}).sort("created_at", -1).to_list(limit)
    return serialize_list(activities)
