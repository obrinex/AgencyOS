"""Every email the product sends.

Composition only. Not one colour, size, font or padding value is written in this
file — those live in `email_theme.py` and come from the brand the admin saved in
Settings → Branding. That separation is the whole point: the brand controls were
already there and already saved, but the templates ignored them and hardcoded
seventy-nine hex literals, so changing "text colour" changed the frame and left
every paragraph exactly as it was.

If you are adding a template, use the components. If a component does not exist
for what you need, add it to `email_theme.py` — the moment a colour appears in
this file, that part of the email stops being customisable and nobody finds out
until a client asks why their brand did not apply.
"""
import os
import asyncio
import logging

import resend

import email_theme as T
from database import db

logger = logging.getLogger(__name__)
resend.api_key = os.environ.get("RESEND_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "Obrinex <noreply@obrinex.space>")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "")

#: Re-exported under the old names — `routers/settings.py` imports these, and
#: the Settings screen builds its colour pickers from the keys.
BRAND_DEFAULTS = T.TOKENS
BRAND_STRING_KEYS = list(T.STRING_KEYS)


async def get_brand() -> dict:
    """The saved brand merged over the defaults; blank fields fall back."""
    doc = await db.email_settings.find_one({"key": "main"}) or {}
    merged = dict(T.TOKENS)
    for k in T.STRING_KEYS:
        v = doc.get(k)
        if isinstance(v, str) and v.strip():
            merged[k] = v.strip()
    for k in T.BOOL_KEYS:
        if k in doc:
            merged[k] = bool(doc[k])
    return merged


def build_wrapper(inner_html: str, b: dict, preheader: str = "") -> str:
    """Wrap pre-composed table rows in the branded document.

    Kept for `routers/settings.py`, which renders the live preview from rows it
    builds itself.
    """
    return T.document(inner_html, b, preheader)


async def _render(rows: str, preheader: str = "") -> str:
    return T.document(rows, await get_brand(), preheader)


async def send_email(to_email: str, subject: str, html_content: str, attachments: list = None):
    """attachments: [{"filename": "x.pdf", "content": <bytes>}]

    Re-asserts the key on every call. `resend.api_key` is a module-level global
    that the deleted outreach sender also wrote to, from a different Resend
    account: setting it once at import was safe only while both used the same
    key, and the moment they differed an invoice went out on the outreach
    account, where SENDER_EMAIL's domain is not verified. Kept as-is, because
    any replacement sender will reintroduce exactly that hazard.
    """
    resend.api_key = os.environ.get("RESEND_API_KEY")
    if not resend.api_key:
        logger.info(f"[EMAIL MOCKED - no RESEND_API_KEY] To: {to_email} | Subject: {subject}"
                    + (f" | attachments: {[a['filename'] for a in attachments]}" if attachments else ""))
        return None
    try:
        params = {"from": SENDER_EMAIL, "to": [to_email], "subject": subject, "html": html_content}
        if attachments:
            import base64
            params["attachments"] = [
                {"filename": a["filename"], "content": base64.b64encode(a["content"]).decode("ascii")}
                for a in attachments if a.get("content")
            ]
        result = await asyncio.to_thread(resend.Emails.send, params)
        logger.info(f"Email sent to {to_email}: {subject}")
        return result
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        raise RuntimeError(f"Email delivery failed: {e}")


# --- Accounts -----------------------------------------------------------------

async def send_welcome_email(to_email: str, name: str, password: str):
    b = await get_brand()
    rows = (
        T.eyebrow("Your portal", b)
        + T.heading(f"Welcome, {name}", b)
        + T.lead("We've set up a secure portal where you can follow your projects, "
                 "settle invoices, sign documents and reach your team directly.", b)
        + T.panel([("Email", to_email), ("Temporary password", f'<span style="font-family:monospace">{password}</span>')], b)
        + T.button("Open your portal", f"{FRONTEND_URL}/login", b)
        + T.note("You'll be asked to set your own password the first time you sign in.", b)
    )
    html = T.document(rows, b, preheader=f"Your Obrinex portal is ready, {name} — sign in details inside.")
    return await send_email(to_email, "Welcome to your Obrinex portal", html)


async def send_invite_email(to_email: str, name: str, password: str):
    b = await get_brand()
    rows = (
        T.eyebrow("Team access", b)
        + T.heading(f"You've been invited, {name}", b)
        + T.lead("You now have team access to Obrinex CRM — clients, projects, finance and "
                 "everything else the agency runs on.", b)
        + T.panel([("Email", to_email), ("Temporary password", f'<span style="font-family:monospace">{password}</span>')], b)
        + T.button("Sign in", f"{FRONTEND_URL}/login", b)
        + T.note("Change this password once you're in — it was generated for you, not by you.", b)
    )
    html = T.document(rows, b, preheader="Your Obrinex CRM team account is ready.")
    return await send_email(to_email, "You've been invited to Obrinex CRM", html)


async def send_password_reset_email(to_email: str, token: str):
    b = await get_brand()
    rows = (
        T.eyebrow("Security", b)
        + T.heading("Reset your password", b)
        + T.lead("We received a request to reset the password on your Obrinex account. "
                 "This link works once, and expires in an hour.", b)
        + T.button("Choose a new password", f"{FRONTEND_URL}/reset-password?token={token}", b)
        + T.note("If you didn't ask for this, you can ignore this email — nothing has changed "
                 "and your current password still works.", b)
    )
    html = T.document(rows, b, preheader="A link to reset your Obrinex password. Expires in one hour.")
    return await send_email(to_email, "Reset your Obrinex password", html)


# --- Money --------------------------------------------------------------------

async def send_invoice_email(to_email: str, invoice_number: str, total: float, due_date: str, invoice_id: str,
                             currency: str = "INR", pay_url: str = None, has_crypto: bool = False, has_other: bool = False,
                             pdf_bytes: bytes = None):
    b = await get_brand()
    code = (currency or "INR").upper()
    target = pay_url or f"{FRONTEND_URL}/portal/invoices/{invoice_id}"

    # Lead with whatever settles best for this currency: crypto for USD (no FX
    # spread, no international card fee), Cashfree for INR.
    prefers_crypto = code == "USD" and has_crypto
    if prefers_crypto:
        primary_label, primary_hint = "Pay with crypto", "USD settles fastest in crypto."
        primary_url = f"{target}?method=crypto"
        secondary = ("Pay by card or bank instead", f"{target}?method=other") if has_other else None
    else:
        primary_label, primary_hint = "Pay this invoice", "Card, UPI, net banking and wallets."
        primary_url = target
        secondary = ("Pay with crypto instead", f"{target}?method=crypto") if has_crypto else None

    rows = (
        T.eyebrow("Invoice", b)
        + T.heading(invoice_number, b)
        + T.lead("A new invoice has been issued to your account.", b)
        + T.panel([("Amount due", f"{code} {total:,.2f}"), ("Due", due_date[:10])], b)
        + T.button(primary_label, primary_url, b, space=6)
        + T.note(primary_hint, b)
    )
    if secondary:
        rows += T.paragraph(T.link(secondary[0], secondary[1], b), b, space=4)
    if pdf_bytes:
        rows += T.note("The full invoice is attached as a PDF for your records.", b)

    html = T.document(rows, b, preheader=f"{invoice_number} — {code} {total:,.2f} due {due_date[:10]}.")
    attachments = [{"filename": f"{invoice_number}.pdf", "content": pdf_bytes}] if pdf_bytes else None
    return await send_email(to_email, f"Invoice {invoice_number} from Obrinex", html, attachments=attachments)


OVERDUE_TONES = {
    1: ("Friendly reminder",
        "Just a note that the invoice below has passed its due date. If you've already "
        "paid it, please ignore this — otherwise we'd appreciate it being settled when you can."),
    2: ("Payment overdue",
        "This invoice is now more than a week overdue. Please arrange payment as soon as "
        "possible, or reply and tell us if there's something we can help resolve."),
    3: ("Final notice",
        "Despite previous reminders this invoice is still unpaid. Please settle it within "
        "three business days to avoid interruption to ongoing services."),
}


async def send_overdue_invoice_email(to_email: str, invoice_number: str, total: float, due_date: str, currency: str, level: int):
    b = await get_brand()
    subject_prefix, tone = OVERDUE_TONES.get(min(level, 3), OVERDUE_TONES[1])
    code = currency or "INR"
    # The third notice is the only one that gets the danger colour. Escalating
    # the styling on notice one leaves nowhere to go, and reads as shouting at
    # someone who is four days late.
    amount = f"{code} {total:,.2f}"
    if level >= 3:
        amount = f'<span style="color:{b["danger_color"]}">{amount}</span>'

    rows = (
        T.eyebrow(subject_prefix, b)
        + T.heading(f"Invoice {invoice_number}", b)
        + T.lead(tone, b)
        + T.panel([("Amount due", amount), ("Was due", due_date[:10])], b)
        + T.button("Settle this invoice", f"{FRONTEND_URL}/portal/invoices", b)
        + T.note("Already paid? Reply to this email and we'll reconcile it.", b)
    )
    html = T.document(rows, b, preheader=f"{invoice_number} — {code} {total:,.2f}, due {due_date[:10]}.")
    return await send_email(to_email, f"{subject_prefix}: Invoice {invoice_number}", html)


# --- Documents ----------------------------------------------------------------

async def resolve_booking_url(explicit: str = None) -> str | None:
    """The booking button's target: an explicit URL wins; otherwise the app's
    own public booking page, if enabled. One resolver for every surface that
    offers a Book-a-Meeting button (Velliom agent, Emails section, proposals)."""
    if explicit:
        return explicit
    settings = await db.booking_settings.find_one({"key": "main"})
    slug = (settings or {}).get("slug")
    if not slug or not (settings or {}).get("enabled"):
        return None
    base = FRONTEND_URL.rstrip("/")
    return f"{base}/book/{slug}" if base else None


def _cta_rows(b: dict, demo_url: str = None, booking_url: str = None) -> str:
    """The conditional CTA rows: each button exists only when its link does, so
    an email without a demo never carries a dead demo button."""
    rows = ""
    if demo_url:
        rows += T.button("View the demo", demo_url, b, space=8)
    if booking_url:
        rows += T.button("Book a meeting", booking_url, b,
                         variant="primary" if not demo_url else "secondary", space=8)
    return rows


async def send_agreement_share_email(to_email: str, title: str, share_token: str, pdf_bytes: bytes = None):
    b = await get_brand()
    rows = (
        T.eyebrow("For signature", b)
        + T.heading(title, b)
        + T.lead("Please review the agreement and sign it online when you're ready. "
                 "The full document is attached as a PDF for your records.", b)
        + T.button("Review and sign", f"{FRONTEND_URL}/agreement/{share_token}", b)
    )
    if pdf_bytes:
        rows += T.note("A copy is attached as a PDF.", b)
    html = T.document(rows, b, preheader=f"{title} is ready for your signature.")
    safe = "".join(ch if ch.isalnum() or ch in "-_ " else "" for ch in title).strip().replace(" ", "_") or "agreement"
    attachments = [{"filename": f"{safe}.pdf", "content": pdf_bytes}] if pdf_bytes else None
    return await send_email(to_email, f"Agreement for signature: {title}", html, attachments=attachments)


async def send_proposal_share_email(to_email: str, title: str, share_token: str, pdf_bytes: bytes = None,
                                    demo_url: str = None, booking_url: str = None):
    b = await get_brand()
    rows = (
        T.eyebrow("Proposal", b)
        + T.heading(title, b)
        + T.lead("Here's the proposal in full. Open it online when you're ready to accept "
                 "or decline, or read the attached PDF first.", b)
        + T.button("Review the proposal", f"{FRONTEND_URL}/proposal/{share_token}", b)
        + _cta_rows(b, demo_url, booking_url)
    )
    if pdf_bytes:
        rows += T.note("The full proposal is attached as a PDF.", b)
    html = T.document(rows, b, preheader=f"{title} — review, then accept or decline.")
    safe = "".join(ch if ch.isalnum() or ch in "-_ " else "" for ch in title).strip().replace(" ", "_") or "proposal"
    attachments = [{"filename": f"{safe}.pdf", "content": pdf_bytes}] if pdf_bytes else None
    return await send_email(to_email, f"Proposal: {title}", html, attachments=attachments)


async def send_custom_email(to_email: str, subject: str, body_html: str,
                            demo_url: str = None, booking_url: str = None):
    """Send a drafted email (Emails section, or the Velliom agent) in the
    branded shell. Body is plain text: blank lines separate paragraphs, single
    newlines become line breaks — so what was written is what renders, instead
    of HTML collapsing it into one run-on blob."""
    b = await get_brand()
    paragraphs = "".join(
        T.paragraph(p.strip().replace(chr(10), "<br/>"), b)
        for p in body_html.split("\n\n") if p.strip()
    )
    rows = paragraphs + _cta_rows(b, demo_url, booking_url)
    # The first line of the body is the best preheader available — a drafted
    # email has no other summary of itself.
    first = next((p.strip() for p in body_html.split("\n\n") if p.strip()), "")
    html = T.document(rows, b, preheader=first[:140])
    return await send_email(to_email, subject, html)


# --- Meetings -----------------------------------------------------------------

def _fmt_meeting_time(iso_str: str) -> str:
    """A human, timezone-honest rendering of a meeting time for an email."""
    if not iso_str:
        return "the scheduled time"
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%A, %d %B %Y at %H:%M UTC")
    except Exception:
        return iso_str


async def send_booking_confirmation_email(to_email: str, name: str, title: str, when_label: str, location: str, company_name: str, manage_token: str = None):
    b = await get_brand()
    rows = (
        T.eyebrow("Confirmed", b)
        + T.heading(f"You're booked, {name}", b)
        + T.lead(f"Your {title} with {company_name} is confirmed.", b)
        + T.panel([("When", when_label), ("Where", location)], b)
    )
    # Self-service reschedule/cancel. Only when a manage token exists (bookings
    # made through the public page); without it the email falls back to the
    # reply-to-us line so older callers still work.
    if manage_token:
        manage_url = f"{FRONTEND_URL}/meeting/{manage_token}"
        rows += (T.button("Reschedule", f"{manage_url}?action=reschedule", b, space=8)
                 + T.button("Cancel", f"{manage_url}?action=cancel", b, variant="secondary", space=8)
                 + T.note("Need to change something? Use the buttons above, or just reply.", b))
    else:
        rows += T.note("Need to reschedule? Just reply to this email.", b)

    html = T.document(rows, b, preheader=f"{title} — {when_label}.")
    return await send_email(to_email, f"Confirmed: {title} with {company_name} — {when_label}", html)


async def send_meeting_reminder_email(to_email: str, name: str, title: str, when_label: str, location: str):
    b = await get_brand()
    rows = (
        T.eyebrow("Starting soon", b)
        + T.heading(title, b)
        + T.lead(f"Hi {name}, this is a reminder that your meeting starts shortly.", b)
        + T.panel([("When", when_label), ("Where", location)], b)
    )
    html = T.document(rows, b, preheader=f"{title} starts soon — {when_label}.")
    return await send_email(to_email, f"Starting soon: {title}", html)


async def send_meeting_cancelled_email(to_email: str, name: str, title: str,
                                       when_iso: str, reason: str = None):
    """Tell an attendee their meeting is cancelled. Warm, brief, no ambiguity."""
    b = await get_brand()
    facts = [("Meeting", title or "Meeting"), ("Was scheduled", _fmt_meeting_time(when_iso))]
    if reason:
        facts.append(("Reason", reason))
    rows = (
        T.eyebrow("Cancelled", b)
        + T.heading("Your meeting has been cancelled", b)
        + T.lead(f"Hi {name or 'there'}, the meeting below is no longer going ahead.", b)
        + T.panel(facts, b)
        + T.paragraph("If you'd like to find another time, just reply to this email and "
                      "we'll get it rebooked.", b)
    )
    html = T.document(rows, b, preheader=f"{title or 'Your meeting'} has been cancelled.")
    return await send_email(to_email, f"Cancelled: {title or 'your meeting'}", html)


async def send_meeting_rescheduled_email(to_email: str, name: str, title: str,
                                         old_iso: str, new_iso: str):
    """Tell an attendee their meeting moved, old time struck through, new time clear."""
    b = await get_brand()
    old = (f'<span style="color:{b["muted_color"]};text-decoration:line-through;">'
           f'{_fmt_meeting_time(old_iso)}</span>')
    rows = (
        T.eyebrow("Rescheduled", b)
        + T.heading("Your meeting has moved", b)
        + T.lead(f"Hi {name or 'there'}, the time for {title or 'your meeting'} has changed.", b)
        + T.panel([("Was", old), ("Now", _fmt_meeting_time(new_iso))], b)
        + T.paragraph("The invite has been updated. If the new time doesn't work, reply and "
                      "we'll sort it out.", b)
    )
    html = T.document(rows, b, preheader=f"New time: {_fmt_meeting_time(new_iso)}.")
    return await send_email(to_email, f"Rescheduled: {title or 'your meeting'}", html)


# --- Internal -----------------------------------------------------------------

async def send_daily_digest_email(to_email: str, digest: dict):
    b = await get_brand()

    def section(label, items):
        if not items:
            return (T.paragraph(f'<span style="color:{b["muted_color"]}">{label} — nothing</span>',
                                b, space=10))
        return (T.paragraph(f'<strong style="color:{b["text_color"]}">{label}</strong>', b, space=6)
                + T.bullets(items, b, space=14))

    rows = (
        T.eyebrow("Daily brief", b)
        + T.heading(digest["date"], b)
        + T.lead("Everything that wants your attention today.", b)
        + section("Today's meetings", digest["meetings"])
        + section("Tasks due today", digest["tasks"])
        + section("New leads (24h)", digest["leads"])
        + section("Overdue invoices", digest["overdue"])
        + T.button("Open the dashboard", f"{FRONTEND_URL}/dashboard", b)
    )
    counts = sum(len(digest.get(k) or []) for k in ("meetings", "tasks", "leads", "overdue"))
    html = T.document(rows, b, preheader=f"{counts} things want your attention today.")
    return await send_email(to_email, f"Daily brief · {digest['date']}", html)


# --- Founding Circle ----------------------------------------------------------
#
# Every applicant hears back, including the ones who did not get in. A silent
# rejection is the default failure of every application process and it is the
# one thing an applicant remembers.
#
# Note on the copy below: these emails used to say applications reopen "on the
# 1st of next month" and that everyone hears back "by the 30th". Intakes have
# been QUARTERLY for some time — see `founding.py`, which is the source of
# truth — so those lines were telling rejected applicants to come back eleven
# weeks early. Seat and cadence wording is now pulled from the model.

async def send_founding_approved_email(to_email: str, name: str, invite_token: str):
    """Approval. Carries a set-your-own-password link rather than a password.

    Nobody emails a working credential that then sits in an inbox forever. The
    token is single-use and the member chooses the password themselves.
    """
    import founding

    b = await get_brand()
    rows = (
        T.eyebrow("Founding Circle", b)
        + T.heading(f"You're in, {name}", b)
        + T.lead(f"You've been offered one of the {founding.SEATS_PER_INTAKE} seats in this "
                 f"quarter's intake. Set your password and your portal is ready — your "
                 f"membership passport, the community room, the member directory and your "
                 f"own assistant.", b)
        + T.button("Set your password", f"{FRONTEND_URL}/founding/accept/{invite_token}", b)
        + T.note("This link is single-use. Membership is never announced publicly — who is "
                 "in the circle stays between the people in it.", b)
    )
    html = T.document(rows, b, preheader=f"Your Founding Circle seat is confirmed, {name}.")
    return await send_email(to_email, "Your Founding Circle seat", html)


async def send_founding_rejected_email(to_email: str, name: str):
    """A decline that says the actual thing: ten seats, more applicants.

    No score, no ranking, no feedback promised that will not be given. Telling
    someone their number is an invitation to argue with arithmetic that was
    never the whole decision.
    """
    import founding

    b = await get_brand()
    rows = (
        T.eyebrow("Founding Circle", b)
        + T.heading("About your application", b)
        + T.lead(f"Thanks for applying, {name}. We had far more applications than the "
                 f"{founding.SEATS_PER_INTAKE} seats available this quarter, and yours "
                 f"isn't one we're taking forward.", b)
        + T.paragraph("That's a decision about fit and timing for a very small group — not a "
                      "verdict on your work.", b)
        + T.paragraph("A new intake opens each quarter, and you're welcome to apply again "
                      "when it does.", b)
    )
    html = T.document(rows, b, preheader="An update on your Founding Circle application.")
    return await send_email(to_email, "Your Founding Circle application", html)


async def send_founding_received_email(to_email: str, name: str):
    """Acknowledgement, so nobody wonders whether the form worked."""
    import founding

    b = await get_brand()
    rows = (
        T.eyebrow("Founding Circle", b)
        + T.heading(f"Application received, {name}", b)
        + T.lead(f"We've got it. This intake closes at the end of the quarter or once its "
                 f"{founding.SEATS_PER_INTAKE} seats are filled — whichever comes first.", b)
        + T.paragraph("Every applicant hears back either way. Nothing else is needed from "
                      "you in the meantime.", b)
    )
    html = T.document(rows, b, preheader="We've received your Founding Circle application.")
    return await send_email(to_email, "We've got your Founding Circle application", html)
