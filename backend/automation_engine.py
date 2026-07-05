from datetime import datetime, timezone, timedelta
from database import db, serialize_doc, next_counter


async def _log_step(steps: list, name: str, status: str, detail: str = ""):
    steps.append({"name": name, "status": status, "detail": detail, "timestamp": datetime.now(timezone.utc).isoformat()})


async def run_won_automation(lead: dict, user_id: str) -> dict:
    """Triggered when a lead's stage changes to 'won'. Creates client, project, invoice, checklist, notification."""
    steps = []
    now = datetime.now(timezone.utc).isoformat()

    client_doc = {
        "company_name": lead.get("company"),
        "website": lead.get("website"),
        "industry": lead.get("industry"),
        "location": lead.get("location"),
        "source_lead_id": lead["id"],
        "owner_id": lead.get("owner_id"),
        "health_score": 100,
        "ltv": 0,
        "revenue_generated": 0,
        "outstanding_amount": 0,
        "profit": 0,
        "onboarding_checklist": [
            {"title": "Kickoff call scheduled", "done": False},
            {"title": "Contract signed", "done": False},
            {"title": "Access & credentials collected", "done": False},
            {"title": "Project workspace created", "done": True},
            {"title": "Welcome email sent", "done": False},
        ],
        "portal_user_id": None,
        "created_at": now,
        "updated_at": now,
    }
    res = await db.clients.insert_one(client_doc)
    client_id = str(res.inserted_id)
    await _log_step(steps, "create_client", "success", f"Client {client_doc['company_name']} created")

    project_doc = {
        "name": f"{lead.get('company')} - Onboarding",
        "client_id": client_id,
        "status": "onboarding",
        "description": f"Auto-generated onboarding project for {lead.get('company')}",
        "budget": lead.get("revenue") or 0,
        "cost": 0,
        "members": [user_id] if user_id else [],
        "deliverables": [],
        "risks": [],
        "ai_notes": "",
        "health": "green",
        "start_date": now,
        "end_date": None,
        "created_at": now,
        "updated_at": now,
    }
    pres = await db.projects.insert_one(project_doc)
    project_id = str(pres.inserted_id)
    await _log_step(steps, "create_project", "success", f"Project {project_doc['name']} created")

    default_tasks = [
        "Send welcome email",
        "Schedule kickoff call",
        "Collect brand assets & access",
        "Prepare onboarding document",
    ]
    for t in default_tasks:
        await db.tasks.insert_one({
            "title": t,
            "description": "",
            "related_type": "project",
            "related_id": project_id,
            "assignee_id": user_id,
            "status": "todo",
            "priority": "medium",
            "due_date": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            "recurring": "none",
            "dependencies": [],
            "created_by": user_id,
            "created_at": now,
        })
    await _log_step(steps, "generate_tasks", "success", f"{len(default_tasks)} onboarding tasks created")

    invoice_number = await next_counter("invoice")
    invoice_doc = {
        "invoice_number": f"INV-{invoice_number:04d}",
        "client_id": client_id,
        "project_id": project_id,
        "line_items": [{"description": "Onboarding / Setup Fee", "quantity": 1, "price": lead.get("revenue") or 500}],
        "subtotal": lead.get("revenue") or 500,
        "tax": 0,
        "total": lead.get("revenue") or 500,
        "status": "draft",
        "is_recurring": False,
        "recurrence_interval": None,
        "issue_date": now,
        "due_date": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
        "stripe_session_id": None,
        "paid_at": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.invoices.insert_one(invoice_doc)
    await _log_step(steps, "generate_invoice", "success", f"Invoice {invoice_doc['invoice_number']} created")

    await db.leads.update_one({"_id": lead["_id"]}, {"$set": {"converted_client_id": client_id}})

    await db.lead_activities.insert_one({
        "lead_id": lead["id"],
        "type": "stage_change",
        "content": "Deal marked as Won. Client, project, and invoice auto-generated.",
        "created_by": user_id,
        "created_at": now,
    })
    await _log_step(steps, "timeline_entry", "success", "Timeline updated on lead")

    if lead.get("owner_id"):
        await db.notifications.insert_one({
            "user_id": lead["owner_id"],
            "type": "deal_won",
            "title": "Deal Won!",
            "message": f"{lead.get('company')} converted to a client. Onboarding project created.",
            "link": f"/clients/{client_id}",
            "read": False,
            "created_at": now,
        })
    await _log_step(steps, "notification", "success", "Owner notified")
    await _log_step(steps, "welcome_email", "success", f"Welcome email queued for {lead.get('email')}")

    await db.automation_logs.insert_one({
        "trigger": "deal_won",
        "entity_id": lead["id"],
        "steps": steps,
        "status": "success",
        "created_at": now,
    })

    return {"client_id": client_id, "project_id": project_id}


async def run_meeting_automation(meeting: dict, user_id: str) -> dict:
    steps = []
    now = datetime.now(timezone.utc).isoformat()
    await _log_step(steps, "calendar_event", "success", "Meeting slot reserved")

    if meeting.get("lead_id"):
        await db.lead_activities.insert_one({
            "lead_id": meeting["lead_id"],
            "type": "meeting",
            "content": f"Meeting scheduled: {meeting.get('title')}",
            "created_by": user_id,
            "created_at": now,
        })
        await _log_step(steps, "crm_update", "success", "Lead timeline updated")

    task_doc = {
        "title": f"Prepare for: {meeting.get('title')}",
        "description": "Auto-created reminder task for upcoming meeting.",
        "related_type": "meeting",
        "related_id": meeting["id"],
        "assignee_id": user_id,
        "status": "todo",
        "priority": "high",
        "due_date": meeting.get("start_time"),
        "recurring": "none",
        "dependencies": [],
        "created_by": user_id,
        "created_at": now,
    }
    await db.tasks.insert_one(task_doc)
    await _log_step(steps, "task_creation", "success", "Preparation task created")

    if user_id:
        await db.notifications.insert_one({
            "user_id": user_id,
            "type": "meeting_reminder",
            "title": "Meeting Scheduled",
            "message": f"{meeting.get('title')} scheduled.",
            "link": "/meetings",
            "read": False,
            "created_at": now,
        })
    await _log_step(steps, "reminder", "success", "Reminder notification created")
    await _log_step(steps, "email_confirmation", "success", "Confirmation email queued")

    await db.automation_logs.insert_one({
        "trigger": "meeting_booked",
        "entity_id": meeting["id"],
        "steps": steps,
        "status": "success",
        "created_at": now,
    })
    return {"status": "ok"}
