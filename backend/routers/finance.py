import os
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import io as _io
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from database import db, serialize_doc, serialize_list, to_object_id, next_counter
from auth_utils import get_current_user, require_admin, require_staff, log_audit, require_module
require_finance = require_module("finance")
from email_service import send_invoice_email
import fx
from finance_utils import to_base, SUPPORTED_CURRENCIES, EXPENSE_TYPES

router = APIRouter(prefix="/api", tags=["finance"])

INVOICE_STATUSES = ["draft", "sent", "viewed", "pending", "paid", "partial", "overdue", "failed", "cancelled"]
PAYMENT_RECORD_STATUSES = {"paid", "failed", "pending"}


class LineItem(BaseModel):
    description: str
    quantity: float = 1
    price: float


class InvoiceCreate(BaseModel):
    client_id: str
    project_id: Optional[str] = None
    line_items: List[LineItem]
    tax: Optional[float] = 0
    due_date: Optional[str] = None
    is_recurring: Optional[bool] = False
    recurrence_interval: Optional[str] = None
    currency: Optional[str] = "INR"
    conversion_rate: Optional[float] = 1.0


class InvoiceUpdate(BaseModel):
    line_items: Optional[List[LineItem]] = None
    tax: Optional[float] = None
    due_date: Optional[str] = None
    status: Optional[str] = None
    currency: Optional[str] = None
    conversion_rate: Optional[float] = None


class PaymentStatusUpdate(BaseModel):
    status: str
    note: Optional[str] = None


class ExpenseCreate(BaseModel):
    category: str
    description: str
    amount: float
    date: str
    vendor: Optional[str] = None
    recurring: Optional[bool] = False
    currency: Optional[str] = "INR"
    conversion_rate: Optional[float] = 1.0
    expense_type: Optional[str] = "unclassified"


def _calc_totals(line_items: list, tax: float):
    subtotal = sum(li["quantity"] * li["price"] for li in line_items)
    total = subtotal + (tax or 0)
    return subtotal, total


@router.get("/invoices")
async def list_invoices(client_id: Optional[str] = None, status: Optional[str] = None, user: dict = Depends(require_finance)):
    query = {}
    if client_id:
        query["client_id"] = client_id
    if status:
        query["status"] = status
    invoices = await db.invoices.find(query).sort("created_at", -1).to_list(1000)
    return serialize_list(invoices)


async def _invoice_recipient(invoice: dict):
    portal_user = await db.users.find_one({"role": "client", "client_id": invoice["client_id"]})
    if portal_user:
        return portal_user["email"]
    contact = await db.contacts.find_one({"client_id": invoice["client_id"], "email": {"$ne": None}})
    return contact.get("email") if contact else None


async def _payment_links(invoice: dict):
    """Build (pay_url, has_crypto, has_other) for an invoice.
    Both email buttons point at the public /pay page. 'Other methods' is always
    offered — the page creates a Cashfree link on demand for INR invoices, and
    falls back to crypto when Cashfree cannot serve the payment."""
    settings = await db.payment_settings.find_one({"key": "main"}) or {}
    frontend = os.environ.get("FRONTEND_URL", "")
    has_crypto = bool(settings.get("crypto_enabled") and any(settings.get(k) for k in (
        "usdt_trc20_address", "usdt_pol_address", "usdt_bep20_address", "btc_address", "eth_address", "sol_address")))
    has_other = True
    token = invoice.get("payment_token")
    if not token:
        import secrets as _secrets
        token = _secrets.token_urlsafe(12)
        await db.invoices.update_one({"_id": invoice["_id"]}, {"$set": {"payment_token": token}})
    pay_url = f"{frontend}/pay/{token}"
    return pay_url, has_crypto, has_other


@router.get("/finance/fx-rate")
async def get_fx_rate(base: str = "USD", quote: str = "INR", refresh: bool = False,
                      user: dict = Depends(require_finance)):
    """Current conversion rate, with provenance so the UI can show how fresh it is."""
    return await fx.get_rate(base, quote, force=refresh)


@router.post("/invoices")
async def create_invoice(payload: InvoiceCreate, user: dict = Depends(require_finance)):
    if payload.currency and payload.currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=400, detail=f"Currency must be one of {SUPPORTED_CURRENCIES}")
    now = datetime.now(timezone.utc).isoformat()
    currency = payload.currency or "INR"
    if payload.conversion_rate and payload.conversion_rate != 1.0:
        conversion_rate, rate_source = payload.conversion_rate, "manual"
    else:
        info = await fx.get_rate(currency, "INR")
        conversion_rate, rate_source = info["rate"], info["source"]
    line_items = [li.model_dump() for li in payload.line_items]
    subtotal, total = _calc_totals(line_items, payload.tax)
    number = await next_counter("invoice")
    import secrets as _secrets
    doc = {
        "invoice_number": f"INV-{number:04d}",
        "client_id": payload.client_id,
        "project_id": payload.project_id,
        "line_items": line_items,
        "subtotal": subtotal,
        "tax": payload.tax or 0,
        "total": total,
        "currency": currency,
        # Pinned at issue time from the live feed, so the invoice keeps the rate
        # it was raised at even as the market moves.
        "conversion_rate": conversion_rate,
        "conversion_rate_source": rate_source,
        "status": "draft",
        "is_recurring": payload.is_recurring,
        "recurrence_interval": payload.recurrence_interval,
        "issue_date": now,
        "due_date": payload.due_date or (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
        "payment_link": None,
        "payment_token": _secrets.token_urlsafe(12),
        "paid_at": None,
        "created_at": now,
        "updated_at": now,
    }
    res = await db.invoices.insert_one(doc)
    await log_audit(user["id"], "create_invoice", "invoice", str(res.inserted_id))
    invoice = await db.invoices.find_one({"_id": res.inserted_id})

    # Auto-email the invoice with payment links (custom + crypto) when the client has an email.
    auto_sent = False
    recipient = await _invoice_recipient(invoice)
    if recipient:
        pay_url, has_crypto, has_other = await _payment_links(invoice)
        pdf_bytes = None
        try:
            pdf_bytes = await build_invoice_pdf_bytes(invoice)
        except Exception:
            pass  # never block invoice creation on PDF rendering
        await send_invoice_email(
            recipient, invoice["invoice_number"], invoice["total"], invoice["due_date"],
            str(invoice["_id"]), invoice.get("currency", "INR"),
            pay_url=pay_url, has_crypto=has_crypto, has_other=has_other,
            pdf_bytes=pdf_bytes,
        )
        await db.invoices.update_one({"_id": invoice["_id"]}, {"$set": {"status": "sent"}})
        invoice = await db.invoices.find_one({"_id": invoice["_id"]})
        auto_sent = True

    data = serialize_doc(invoice)
    data["auto_sent"] = auto_sent
    data["sent_to"] = recipient if auto_sent else None
    return data


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, user: dict = Depends(get_current_user)):
    invoice = await db.invoices.find_one({"_id": to_object_id(invoice_id)})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if user["role"] == "client" and invoice["client_id"] != user.get("client_id"):
        raise HTTPException(status_code=403, detail="Not authorized")
    # Ensure a public payment token exists so the client's "Pay Invoice" button always works.
    if not invoice.get("payment_token"):
        import secrets as _secrets
        token = _secrets.token_urlsafe(12)
        await db.invoices.update_one({"_id": invoice["_id"]}, {"$set": {"payment_token": token}})
        invoice["payment_token"] = token
    client = await db.clients.find_one({"_id": to_object_id(invoice["client_id"])})
    data = serialize_doc(invoice)
    data["client"] = serialize_doc(client) if client else None
    return data


@router.put("/invoices/{invoice_id}")
async def update_invoice(invoice_id: str, payload: InvoiceUpdate, user: dict = Depends(require_finance)):
    updates = {}
    if payload.line_items is not None:
        line_items = [li.model_dump() for li in payload.line_items]
        tax = payload.tax if payload.tax is not None else 0
        subtotal, total = _calc_totals(line_items, tax)
        updates.update({"line_items": line_items, "subtotal": subtotal, "total": total, "tax": tax})
    if payload.due_date is not None:
        updates["due_date"] = payload.due_date
    if payload.currency is not None:
        if payload.currency not in SUPPORTED_CURRENCIES:
            raise HTTPException(status_code=400, detail=f"Currency must be one of {SUPPORTED_CURRENCIES}")
        updates["currency"] = payload.currency
    if payload.conversion_rate is not None:
        updates["conversion_rate"] = payload.conversion_rate
    if payload.status is not None:
        if payload.status not in INVOICE_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status")
        updates["status"] = payload.status
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.invoices.update_one({"_id": to_object_id(invoice_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice = await db.invoices.find_one({"_id": to_object_id(invoice_id)})
    return serialize_doc(invoice)


@router.post("/invoices/{invoice_id}/payment-status")
async def record_payment_status(invoice_id: str, payload: PaymentStatusUpdate, user: dict = Depends(require_admin)):
    """Record the finance outcome of an invoice from the admin workspace."""
    if payload.status not in PAYMENT_RECORD_STATUSES:
        raise HTTPException(status_code=400, detail="Payment status must be paid, failed, or pending")

    invoice = await db.invoices.find_one({"_id": to_object_id(invoice_id)})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    now = datetime.now(timezone.utc).isoformat()
    updates = {
        "status": payload.status,
        "payment_status": payload.status,
        "payment_note": (payload.note or "").strip() or None,
        "payment_recorded_at": now,
        "payment_recorded_by": user["id"],
        "updated_at": now,
    }
    if payload.status == "paid":
        updates["paid_at"] = now
    else:
        updates["paid_at"] = None

    await db.invoices.update_one({"_id": invoice["_id"]}, {"$set": updates})
    await log_audit(user["id"], f"record_invoice_payment_{payload.status}", "invoice", invoice_id)
    updated = await db.invoices.find_one({"_id": invoice["_id"]})
    return serialize_doc(updated)


@router.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str, user: dict = Depends(require_finance)):
    await db.invoices.delete_one({"_id": to_object_id(invoice_id)})
    return {"message": "Invoice deleted"}


@router.post("/invoices/{invoice_id}/send")
async def send_invoice(invoice_id: str, user: dict = Depends(require_finance)):
    invoice = await db.invoices.find_one({"_id": to_object_id(invoice_id)})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    recipient_email = None
    portal_user = await db.users.find_one({"role": "client", "client_id": invoice["client_id"]})
    if portal_user:
        recipient_email = portal_user["email"]
    else:
        contact = await db.contacts.find_one({"client_id": invoice["client_id"], "email": {"$ne": None}})
        if contact:
            recipient_email = contact.get("email")

    if not recipient_email:
        raise HTTPException(
            status_code=400,
            detail="Client email not found. Please ensure the client has portal access or a contact email."
        )

    await db.invoices.update_one({"_id": invoice["_id"]}, {"$set": {"status": "sent", "updated_at": datetime.now(timezone.utc).isoformat()}})

    pay_url, has_crypto, has_other = await _payment_links(invoice)
    pdf_bytes = None
    try:
        pdf_bytes = await build_invoice_pdf_bytes(invoice)
    except Exception:
        pass
    await send_invoice_email(
        recipient_email,
        invoice["invoice_number"],
        invoice["total"],
        invoice["due_date"],
        invoice_id,
        invoice.get("currency", "INR"),
        pay_url=pay_url, has_crypto=has_crypto, has_other=has_other,
        pdf_bytes=pdf_bytes,
    )

    updated = await db.invoices.find_one({"_id": invoice["_id"]})
    return serialize_doc(updated)


@router.get("/invoices/{invoice_id}/payment-link")
async def get_invoice_payment_link(invoice_id: str, user: dict = Depends(require_finance)):
    """Return (creating if needed) the public crypto-payment URL for this invoice."""
    invoice = await db.invoices.find_one({"_id": to_object_id(invoice_id)})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    import secrets as _secrets
    token = invoice.get("payment_token")
    if not token:
        token = _secrets.token_urlsafe(12)
        await db.invoices.update_one({"_id": invoice["_id"]}, {"$set": {"payment_token": token}})
    frontend = os.environ.get("FRONTEND_URL", "")
    return {"payment_token": token, "pay_url": f"{frontend}/pay/{token}"}


# ---------------- Expenses ----------------

@router.get("/expenses")
async def list_expenses(user: dict = Depends(require_finance)):
    expenses = await db.expenses.find({}).sort("date", -1).to_list(1000)
    return serialize_list(expenses)


@router.post("/expenses")
async def create_expense(payload: ExpenseCreate, user: dict = Depends(require_finance)):
    if payload.currency and payload.currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=400, detail=f"Currency must be one of {SUPPORTED_CURRENCIES}")
    if payload.expense_type and payload.expense_type not in EXPENSE_TYPES:
        raise HTTPException(status_code=400, detail=f"Expense type must be one of {EXPENSE_TYPES}")
    doc = payload.model_dump()
    # Same rule as invoices: pin the live rate unless one was supplied.
    if not doc.get("conversion_rate") or doc.get("conversion_rate") == 1.0:
        info = await fx.get_rate(doc.get("currency") or "INR", "INR")
        doc["conversion_rate"] = info["rate"]
        doc["conversion_rate_source"] = info["source"]
    else:
        doc["conversion_rate_source"] = "manual"
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    res = await db.expenses.insert_one(doc)
    expense = await db.expenses.find_one({"_id": res.inserted_id})
    return serialize_doc(expense)


@router.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: str, user: dict = Depends(require_finance)):
    await db.expenses.delete_one({"_id": to_object_id(expense_id)})
    return {"message": "Expense deleted"}


@router.get("/finance/summary")
async def finance_summary(user: dict = Depends(require_finance)):
    invoices = await db.invoices.find({}).to_list(5000)
    expenses = await db.expenses.find({}).to_list(5000)
    leads = await db.leads.find({}).to_list(5000)

    revenue = sum(to_base(i["total"], i.get("conversion_rate")) for i in invoices if i["status"] == "paid")
    outstanding = sum(to_base(i["total"], i.get("conversion_rate")) for i in invoices if i["status"] in ("sent", "overdue", "partial", "viewed"))
    total_expenses = sum(to_base(e["amount"], e.get("conversion_rate")) for e in expenses)
    profit = revenue - total_expenses
    recurring_invoices = [i for i in invoices if i.get("is_recurring")]
    mrr = sum(to_base(i["total"], i.get("conversion_rate")) for i in recurring_invoices if i["status"] == "paid")
    arr = mrr * 12

    active_leads = [ld for ld in leads if ld["stage"] not in ("won", "lost", "rejected")]
    pipeline_value = sum(ld.get("revenue") or 0 for ld in active_leads)
    won_leads = [ld for ld in leads if ld["stage"] == "won"]
    total_closed = len(won_leads) + len([ld for ld in leads if ld["stage"] in ("lost", "rejected")])
    conversion_rate = round((len(won_leads) / total_closed) * 100, 1) if total_closed else 0
    avg_deal_size = round(sum(ld.get("revenue") or 0 for ld in won_leads) / len(won_leads), 2) if won_leads else 0

    monthly = {}
    for i in invoices:
        if i["status"] == "paid" and i.get("paid_at"):
            month = i["paid_at"][:7]
            monthly[month] = monthly.get(month, 0) + to_base(i["total"], i.get("conversion_rate"))
    revenue_by_month = [{"month": k, "revenue": v} for k, v in sorted(monthly.items())]

    expense_breakdown = {t: 0 for t in EXPENSE_TYPES}
    for e in expenses:
        etype = e.get("expense_type") or "unclassified"
        if etype not in expense_breakdown:
            expense_breakdown[etype] = 0
        expense_breakdown[etype] += to_base(e["amount"], e.get("conversion_rate"))

    return {
        "revenue": revenue, "outstanding": outstanding, "expenses": total_expenses,
        "profit": profit, "mrr": mrr, "arr": arr, "gross_margin": round((profit / revenue) * 100, 1) if revenue else 0,
        "pipeline_value": pipeline_value, "conversion_rate": conversion_rate, "avg_deal_size": avg_deal_size,
        "revenue_by_month": revenue_by_month,
        "expense_breakdown": expense_breakdown,
    }



class RevenueGoalUpdate(BaseModel):
    monthly_revenue_goal: float


@router.get("/finance/goal")
async def get_revenue_goal(user: dict = Depends(require_finance)):
    settings = await db.company_settings.find_one({"key": "main"})
    goal = (settings or {}).get("monthly_revenue_goal") or 0

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    invoices = await db.invoices.find({"status": "paid", "paid_at": {"$gte": month_start}}).to_list(2000)
    mtd_revenue = sum(to_base(i["total"], i.get("conversion_rate")) for i in invoices)

    day = now.day
    days_in_month = (now.replace(month=now.month % 12 + 1, day=1) - timedelta(days=1)).day if now.month != 12 else 31
    projected = round(mtd_revenue / day * days_in_month, 2) if day else 0

    leads = await db.leads.find({"stage": {"$nin": ["won", "lost", "rejected", "cold"]}}).to_list(2000)
    pipeline_value = sum(ld.get("revenue") or 0 for ld in leads)

    return {
        "monthly_revenue_goal": goal,
        "mtd_revenue": mtd_revenue,
        "projected_month_end": projected,
        "pipeline_value": pipeline_value,
        "progress_pct": round(mtd_revenue / goal * 100, 1) if goal else None,
        "on_track": projected >= goal if goal else None,
        "day_of_month": day,
        "days_in_month": days_in_month,
    }


@router.put("/finance/goal")
async def set_revenue_goal(payload: RevenueGoalUpdate, user: dict = Depends(require_finance)):
    await db.company_settings.update_one({"key": "main"}, {"$set": {"monthly_revenue_goal": payload.monthly_revenue_goal}}, upsert=True)
    return await get_revenue_goal(user=user)


async def build_invoice_pdf_bytes(invoice: dict) -> bytes:
    """Render the branded invoice PDF and return raw bytes (used by the download endpoint and email attachments)."""
    client = await db.clients.find_one({"_id": to_object_id(invoice["client_id"])})
    company = await db.company_settings.find_one({"key": "main"})
    agency_name = (company or {}).get("company_name") or "Obrinex"

    code = invoice.get("currency") or "INR"
    buf = _io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 25 * mm

    # Branded header band
    c.setFillColorRGB(0.05, 0.05, 0.05)
    c.rect(0, height - 38 * mm, width, 38 * mm, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(20 * mm, height - 20 * mm, agency_name.upper())
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, height - 27 * mm, "AgencyOS \u00b7 info@obrinex.space")
    c.setFont("Helvetica-Bold", 24)
    c.drawRightString(190 * mm, height - 20 * mm, "INVOICE")
    c.setFont("Helvetica", 10)
    c.drawRightString(190 * mm, height - 27 * mm, invoice["invoice_number"])
    c.setFillColorRGB(0, 0, 0)

    y = height - 50 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "Billed To")
    c.drawRightString(190 * mm, y, "Details")
    c.setFont("Helvetica", 10)
    y -= 6 * mm
    if client:
        c.drawString(20 * mm, y, client.get("company_name", ""))
        if client.get("location"):
            c.drawString(20 * mm, y - 5 * mm, client["location"])
        if client.get("website"):
            c.drawString(20 * mm, y - 10 * mm, client["website"])
    c.drawRightString(190 * mm, y, f"Issue Date: {invoice['issue_date'][:10]}")
    c.drawRightString(190 * mm, y - 5 * mm, f"Due Date: {invoice['due_date'][:10]}")
    c.drawRightString(190 * mm, y - 10 * mm, f"Status: {invoice['status'].upper()}  \u00b7  {invoice.get('currency', 'INR')}")

    y -= 24 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, "Description")
    c.drawString(115 * mm, y, "Qty")
    c.drawString(140 * mm, y, "Price")
    c.drawString(168 * mm, y, "Amount")
    y -= 3 * mm
    c.line(20 * mm, y, 190 * mm, y)
    c.setFont("Helvetica", 10)
    for li in invoice["line_items"]:
        y -= 7 * mm
        c.drawString(20 * mm, y, str(li["description"])[:55])
        c.drawString(115 * mm, y, str(li["quantity"]))
        c.drawString(140 * mm, y, f"{code} {li['price']:,.2f}")
        c.drawString(168 * mm, y, f"{code} {li['quantity'] * li['price']:,.2f}")

    y -= 9 * mm
    c.line(115 * mm, y, 190 * mm, y)
    y -= 7 * mm
    c.drawString(140 * mm, y, "Subtotal:")
    c.drawString(168 * mm, y, f"{code} {invoice['subtotal']:,.2f}")
    y -= 6 * mm
    c.drawString(140 * mm, y, "Tax:")
    c.drawString(168 * mm, y, f"{code} {invoice.get('tax', 0):,.2f}")
    y -= 7 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(140 * mm, y, "Total:")
    c.drawString(168 * mm, y, f"{code} {invoice['total']:,.2f}")

    c.setFont("Helvetica", 9)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawString(20 * mm, 20 * mm, f"Thank you for your business. Questions about this invoice? Contact {agency_name} at info@obrinex.space.")
    c.setFillColorRGB(0, 0, 0)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()


@router.get("/invoices/{invoice_id}/pdf")
async def invoice_pdf(invoice_id: str, user: dict = Depends(get_current_user)):
    invoice = await db.invoices.find_one({"_id": to_object_id(invoice_id)})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if user["role"] == "client" and invoice["client_id"] != user.get("client_id"):
        raise HTTPException(status_code=403, detail="Not authorized")
    pdf = await build_invoice_pdf_bytes(invoice)
    return StreamingResponse(
        _io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={invoice['invoice_number']}.pdf"},
    )


@router.get("/finance/report/pdf")
async def finance_report_pdf(user: dict = Depends(require_finance)):
    summary = await finance_summary(user=user)

    buf = _io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    height = A4[1]
    y = height - 25 * mm

    c.setFont("Helvetica-Bold", 18)
    c.drawString(20 * mm, y, "Finance Report")
    c.setFont("Helvetica", 9)
    y -= 8 * mm
    c.drawString(20 * mm, y, f"Generated: {datetime.now(timezone.utc).strftime('%b %d, %Y')} \u00b7 Base currency: INR")

    rows = [
        ("Revenue", summary["revenue"]), ("Outstanding", summary["outstanding"]),
        ("Expenses", summary["expenses"]), ("Profit", summary["profit"]),
        ("MRR", summary["mrr"]), ("ARR", summary["arr"]),
        ("Gross Margin", f"{summary['gross_margin']}%"), ("Pipeline Value", summary["pipeline_value"]),
        ("Avg Deal Size", summary["avg_deal_size"]),
    ]
    y -= 14 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, "Key Metrics")
    c.setFont("Helvetica", 10)
    for label, value in rows:
        y -= 7 * mm
        display = f"INR {value:,.2f}" if isinstance(value, (int, float)) else str(value)
        c.drawString(20 * mm, y, label)
        c.drawString(90 * mm, y, display)

    y -= 12 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, "Expense Breakdown")
    c.setFont("Helvetica", 10)
    for etype, amount in summary["expense_breakdown"].items():
        y -= 7 * mm
        c.drawString(20 * mm, y, etype.replace("_", " ").title())
        c.drawString(90 * mm, y, f"INR {amount:,.2f}")

    c.showPage()
    c.save()
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=finance_report.pdf"},
    )


