import os
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from database import db, serialize_doc, serialize_list, to_object_id, next_counter
from auth_utils import get_current_user, require_staff, log_audit

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


class InvoiceUpdate(BaseModel):
    line_items: Optional[List[LineItem]] = None
    tax: Optional[float] = None
    due_date: Optional[str] = None
    status: Optional[str] = None


class ExpenseCreate(BaseModel):
    category: str
    description: str
    amount: float
    date: str
    vendor: Optional[str] = None
    recurring: Optional[bool] = False


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
    print(f"[INVOICE EMAIL] Invoice {invoice['invoice_number']} sent for client {invoice['client_id']}")
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

    stripe_checkout = StripeCheckout(api_key=os.environ["STRIPE_API_KEY"], webhook_url=f"{origin}/api/webhook/stripe")
    checkout_request = CheckoutSessionRequest(
        amount=float(invoice["total"]), currency="usd",
        success_url=success_url, cancel_url=cancel_url,
        metadata={"invoice_id": invoice_id, "invoice_number": invoice["invoice_number"]},
    )
    session = await stripe_checkout.create_checkout_session(checkout_request)

    await db.payment_transactions.insert_one({
        "session_id": session.session_id,
        "invoice_id": invoice_id,
        "amount": invoice["total"],
        "currency": "usd",
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

    revenue = sum(i["total"] for i in invoices if i["status"] == "paid")
    outstanding = sum(i["total"] for i in invoices if i["status"] in ("sent", "overdue", "partial", "viewed"))
    total_expenses = sum(e["amount"] for e in expenses)
    profit = revenue - total_expenses
    recurring_invoices = [i for i in invoices if i.get("is_recurring")]
    mrr = sum(i["total"] for i in recurring_invoices if i["status"] == "paid")
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
            monthly[month] = monthly.get(month, 0) + i["total"]
    revenue_by_month = [{"month": k, "revenue": v} for k, v in sorted(monthly.items())]

    return {
        "revenue": revenue, "outstanding": outstanding, "expenses": total_expenses,
        "profit": profit, "mrr": mrr, "arr": arr, "gross_margin": round((profit / revenue) * 100, 1) if revenue else 0,
        "pipeline_value": pipeline_value, "conversion_rate": conversion_rate, "avg_deal_size": avg_deal_size,
        "revenue_by_month": revenue_by_month,
    }
