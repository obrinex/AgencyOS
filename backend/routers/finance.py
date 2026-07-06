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
from auth_utils import get_current_user, require_staff, log_audit
from email_service import send_invoice_email
from finance_utils import to_base, SUPPORTED_CURRENCIES, EXPENSE_TYPES

from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionRequest

router = APIRouter(prefix="/api", tags=["finance"])

INVOICE_STATUSES = ["draft", "sent", "viewed", "paid", "partial", "overdue", "cancelled"]


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
async def list_invoices(client_id: Optional[str] = None, status: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {}
    if client_id:
        query["client_id"] = client_id
    if status:
        query["status"] = status
    invoices = await db.invoices.find(query).sort("created_at", -1).to_list(1000)
    return serialize_list(invoices)


@router.post("/invoices")
async def create_invoice(payload: InvoiceCreate, user: dict = Depends(require_staff)):
    if payload.currency and payload.currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=400, detail=f"Currency must be one of {SUPPORTED_CURRENCIES}")
    now = datetime.now(timezone.utc).isoformat()
    line_items = [li.model_dump() for li in payload.line_items]
    subtotal, total = _calc_totals(line_items, payload.tax)
    number = await next_counter("invoice")
    doc = {
        "invoice_number": f"INV-{number:04d}",
        "client_id": payload.client_id,
        "project_id": payload.project_id,
        "line_items": line_items,
        "subtotal": subtotal,
        "tax": payload.tax or 0,
        "total": total,
        "currency": payload.currency or "INR",
        "conversion_rate": payload.conversion_rate or 1.0,
        "status": "draft",
        "is_recurring": payload.is_recurring,
        "recurrence_interval": payload.recurrence_interval,
        "issue_date": now,
        "due_date": payload.due_date or (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
        "stripe_session_id": None,
        "paid_at": None,
        "created_at": now,
        "updated_at": now,
    }
    res = await db.invoices.insert_one(doc)
    await log_audit(user["id"], "create_invoice", "invoice", str(res.inserted_id))
    invoice = await db.invoices.find_one({"_id": res.inserted_id})
    return serialize_doc(invoice)


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, user: dict = Depends(get_current_user)):
    invoice = await db.invoices.find_one({"_id": to_object_id(invoice_id)})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if user["role"] == "client" and invoice["client_id"] != user.get("client_id"):
        raise HTTPException(status_code=403, detail="Not authorized")
    client = await db.clients.find_one({"_id": to_object_id(invoice["client_id"])})
    data = serialize_doc(invoice)
    data["client"] = serialize_doc(client) if client else None
    return data


@router.put("/invoices/{invoice_id}")
async def update_invoice(invoice_id: str, payload: InvoiceUpdate, user: dict = Depends(require_staff)):
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


@router.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str, user: dict = Depends(require_staff)):
    await db.invoices.delete_one({"_id": to_object_id(invoice_id)})
    return {"message": "Invoice deleted"}


@router.post("/invoices/{invoice_id}/send")
async def send_invoice(invoice_id: str, user: dict = Depends(require_staff)):
    invoice = await db.invoices.find_one({"_id": to_object_id(invoice_id)})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    await db.invoices.update_one({"_id": invoice["_id"]}, {"$set": {"status": "sent", "updated_at": datetime.now(timezone.utc).isoformat()}})

    recipient_email = None
    portal_user = await db.users.find_one({"role": "client", "client_id": invoice["client_id"]})
    if portal_user:
        recipient_email = portal_user["email"]
    else:
        contact = await db.contacts.find_one({"client_id": invoice["client_id"], "email": {"$ne": None}})
        if contact:
            recipient_email = contact.get("email")
    if recipient_email:
        await send_invoice_email(recipient_email, invoice["invoice_number"], invoice["total"], invoice["due_date"], invoice_id)

    updated = await db.invoices.find_one({"_id": invoice["_id"]})
    return serialize_doc(updated)


@router.post("/invoices/{invoice_id}/checkout")
async def create_checkout(invoice_id: str, request: Request, user: dict = Depends(get_current_user)):
    invoice = await db.invoices.find_one({"_id": to_object_id(invoice_id)})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if user["role"] == "client" and invoice["client_id"] != user.get("client_id"):
        raise HTTPException(status_code=403, detail="Not authorized")
    origin = os.environ["FRONTEND_URL"]
    success_url = f"{origin}/invoices/{invoice_id}?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/invoices/{invoice_id}"

    invoice_currency = (invoice.get("currency") or "INR").lower()
    stripe_checkout = StripeCheckout(api_key=os.environ["STRIPE_API_KEY"], webhook_url=f"{origin}/api/webhook/stripe")
    checkout_request = CheckoutSessionRequest(
        amount=float(invoice["total"]), currency=invoice_currency,
        success_url=success_url, cancel_url=cancel_url,
        metadata={"invoice_id": invoice_id, "invoice_number": invoice["invoice_number"]},
    )
    session = await stripe_checkout.create_checkout_session(checkout_request)

    await db.payment_transactions.insert_one({
        "session_id": session.session_id,
        "invoice_id": invoice_id,
        "amount": invoice["total"],
        "currency": invoice_currency,
        "payment_status": "initiated",
        "metadata": {"invoice_id": invoice_id},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    await db.invoices.update_one({"_id": invoice["_id"]}, {"$set": {"stripe_session_id": session.session_id}})
    return {"url": session.url, "session_id": session.session_id}


@router.get("/invoices/checkout/status/{session_id}")
async def checkout_status(session_id: str, request: Request, user: dict = Depends(get_current_user)):
    tx = await db.payment_transactions.find_one({"session_id": session_id})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if tx["payment_status"] == "paid":
        return {"payment_status": "paid", "status": "complete"}

    origin = os.environ["FRONTEND_URL"]
    stripe_checkout = StripeCheckout(api_key=os.environ["STRIPE_API_KEY"], webhook_url=f"{origin}/api/webhook/stripe")
    status = await stripe_checkout.get_checkout_status(session_id)

    if status.payment_status == "paid" and tx["payment_status"] != "paid":
        await db.payment_transactions.update_one({"session_id": session_id}, {"$set": {"payment_status": "paid", "status": status.status}})
        invoice_id = tx["invoice_id"]
        await db.invoices.update_one({"_id": to_object_id(invoice_id)}, {"$set": {"status": "paid", "paid_at": datetime.now(timezone.utc).isoformat()}})
        invoice = await db.invoices.find_one({"_id": to_object_id(invoice_id)})
        if invoice:
            await db.clients.update_one({"_id": to_object_id(invoice["client_id"])}, {"$inc": {"revenue_generated": invoice["total"]}})
    else:
        await db.payment_transactions.update_one({"session_id": session_id}, {"$set": {"payment_status": status.payment_status, "status": status.status}})

    return {"payment_status": status.payment_status, "status": status.status}


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    body = await request.body()
    stripe_checkout = StripeCheckout(api_key=os.environ["STRIPE_API_KEY"], webhook_url="")
    webhook_response = await stripe_checkout.handle_webhook(body, request.headers.get("Stripe-Signature"))
    if webhook_response.payment_status == "paid":
        tx = await db.payment_transactions.find_one({"session_id": webhook_response.session_id})
        if tx and tx["payment_status"] != "paid":
            await db.payment_transactions.update_one({"session_id": webhook_response.session_id}, {"$set": {"payment_status": "paid"}})
            invoice_id = tx["invoice_id"]
            await db.invoices.update_one({"_id": to_object_id(invoice_id)}, {"$set": {"status": "paid", "paid_at": datetime.now(timezone.utc).isoformat()}})
    return {"received": True}


# ---------------- Expenses ----------------

@router.get("/expenses")
async def list_expenses(user: dict = Depends(get_current_user)):
    expenses = await db.expenses.find({}).sort("date", -1).to_list(1000)
    return serialize_list(expenses)


@router.post("/expenses")
async def create_expense(payload: ExpenseCreate, user: dict = Depends(require_staff)):
    if payload.currency and payload.currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=400, detail=f"Currency must be one of {SUPPORTED_CURRENCIES}")
    if payload.expense_type and payload.expense_type not in EXPENSE_TYPES:
        raise HTTPException(status_code=400, detail=f"Expense type must be one of {EXPENSE_TYPES}")
    doc = payload.model_dump()
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    res = await db.expenses.insert_one(doc)
    expense = await db.expenses.find_one({"_id": res.inserted_id})
    return serialize_doc(expense)


@router.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: str, user: dict = Depends(require_staff)):
    await db.expenses.delete_one({"_id": to_object_id(expense_id)})
    return {"message": "Expense deleted"}


@router.get("/finance/summary")
async def finance_summary(user: dict = Depends(get_current_user)):
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



@router.get("/invoices/{invoice_id}/pdf")
async def invoice_pdf(invoice_id: str, user: dict = Depends(get_current_user)):
    invoice = await db.invoices.find_one({"_id": to_object_id(invoice_id)})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if user["role"] == "client" and invoice["client_id"] != user.get("client_id"):
        raise HTTPException(status_code=403, detail="Not authorized")
    client = await db.clients.find_one({"_id": to_object_id(invoice["client_id"])})

    symbol = "\u20b9" if (invoice.get("currency") or "INR") == "INR" else "$"
    buf = _io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 25 * mm

    c.setFont("Helvetica-Bold", 18)
    c.drawString(20 * mm, y, "INVOICE")
    c.setFont("Helvetica", 10)
    y -= 10 * mm
    c.drawString(20 * mm, y, f"Invoice #: {invoice['invoice_number']}")
    y -= 6 * mm
    c.drawString(20 * mm, y, f"Issue Date: {invoice['issue_date'][:10]}")
    y -= 6 * mm
    c.drawString(20 * mm, y, f"Due Date: {invoice['due_date'][:10]}")
    y -= 6 * mm
    c.drawString(20 * mm, y, f"Status: {invoice['status'].upper()}")
    y -= 6 * mm
    c.drawString(20 * mm, y, f"Currency: {invoice.get('currency', 'INR')}")

    if client:
        y -= 12 * mm
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, y, "Billed To:")
        c.setFont("Helvetica", 10)
        y -= 6 * mm
        c.drawString(20 * mm, y, client.get("company_name", ""))

    y -= 14 * mm
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
        c.drawString(140 * mm, y, f"{symbol}{li['price']:,.2f}")
        c.drawString(168 * mm, y, f"{symbol}{li['quantity'] * li['price']:,.2f}")

    y -= 9 * mm
    c.line(115 * mm, y, 190 * mm, y)
    y -= 7 * mm
    c.drawString(140 * mm, y, "Subtotal:")
    c.drawString(168 * mm, y, f"{symbol}{invoice['subtotal']:,.2f}")
    y -= 6 * mm
    c.drawString(140 * mm, y, "Tax:")
    c.drawString(168 * mm, y, f"{symbol}{invoice.get('tax', 0):,.2f}")
    y -= 7 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(140 * mm, y, "Total:")
    c.drawString(168 * mm, y, f"{symbol}{invoice['total']:,.2f}")

    c.showPage()
    c.save()
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={invoice['invoice_number']}.pdf"},
    )


@router.get("/finance/report/pdf")
async def finance_report_pdf(user: dict = Depends(require_staff)):
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
        display = f"\u20b9{value:,.2f}" if isinstance(value, (int, float)) else str(value)
        c.drawString(20 * mm, y, label)
        c.drawString(90 * mm, y, display)

    y -= 12 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, "Expense Breakdown")
    c.setFont("Helvetica", 10)
    for etype, amount in summary["expense_breakdown"].items():
        y -= 7 * mm
        c.drawString(20 * mm, y, etype.replace("_", " ").title())
        c.drawString(90 * mm, y, f"\u20b9{amount:,.2f}")

    c.showPage()
    c.save()
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=finance_report.pdf"},
    )
