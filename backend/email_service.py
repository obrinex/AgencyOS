import os
import asyncio
import logging
import resend

from database import db

logger = logging.getLogger(__name__)
resend.api_key = os.environ.get("RESEND_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "Obrinex <noreply@obrinex.space>")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "")


# Default email brand — tuned to match obrinex.space (black canvas, cream "paper"
# monogram, geometric Jost type). Admins override any of these in Settings → Branding.
BRAND_DEFAULTS = {
    "logo_url": "https://obrinex.space/brand/monogram-paper.png",
    "show_logo": True,
    "brand_name": "OBRINEX",
    "tagline": "AI Automation Agency",
    "bg_color": "#000000",
    "card_color": "#0B0B0C",
    "text_color": "#F4F4F5",
    "muted_color": "#8A8A90",
    "accent_color": "#EDE7D9",
    "accent_text_color": "#0B0B0C",
    "border_color": "#1E1E20",
    "box_color": "#161618",
    "footer_text": "Obrinex — Systems that ship",
    "footer_note": "Please check your spam folder if this email isn't in your inbox.",
    "font": "'Jost','Futura','Century Gothic','Trebuchet MS',Arial,sans-serif",
}

# Keys that are colors/text (string) vs booleans, for merge + validation.
BRAND_STRING_KEYS = [k for k in BRAND_DEFAULTS if k != "show_logo"]


async def get_brand() -> dict:
    """Load the saved email brand merged over defaults (missing/blank fields fall back)."""
    doc = await db.email_settings.find_one({"key": "main"}) or {}
    merged = dict(BRAND_DEFAULTS)
    for k in BRAND_STRING_KEYS:
        v = doc.get(k)
        if isinstance(v, str) and v.strip():
            merged[k] = v.strip()
    if "show_logo" in doc:
        merged["show_logo"] = bool(doc["show_logo"])
    return merged


def build_wrapper(inner_html: str, b: dict) -> str:
    """Assemble the branded email shell around inner table rows using brand dict `b`."""
    if b.get("show_logo") and b.get("logo_url"):
        header = (
            f'<img src="{b["logo_url"]}" alt="{b["brand_name"]}" height="46" '
            f'style="height:46px;width:auto;max-width:220px;display:block;margin:0 auto;border:0;outline:none;" />'
        )
    else:
        header = (
            f'<div style="font-size:24px;font-weight:700;letter-spacing:4px;color:{b["text_color"]};'
            f'font-family:{b["font"]};">{b["brand_name"]}</div>'
        )
    tagline = (
        f'<div style="font-size:11px;letter-spacing:3px;text-transform:uppercase;color:{b["muted_color"]};'
        f'padding-top:10px;font-family:{b["font"]};">{b["tagline"]}</div>' if b.get("tagline") else ""
    )
    return f"""\
<div style="background:{b['bg_color']};padding:40px 16px;font-family:{b['font']};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{b['bg_color']};">
    <tr><td align="center">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:{b['card_color']};border:1px solid {b['border_color']};border-radius:16px;overflow:hidden;">
        <tr><td style="padding:36px 36px 22px;text-align:center;">
          {header}
          {tagline}
        </td></tr>
        <tr><td style="padding:0 36px;"><div style="height:2px;background:{b['accent_color']};border-radius:2px;opacity:0.9;"></div></td></tr>
        <tr><td style="padding:30px 36px 8px;color:{b['text_color']};font-family:{b['font']};">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
            {inner_html}
          </table>
        </td></tr>
        <tr><td style="padding:26px 36px 34px;text-align:center;border-top:1px solid {b['border_color']};">
          <div style="font-size:12px;letter-spacing:1px;color:{b['muted_color']};font-family:{b['font']};">{b['footer_text']}</div>
          <div style="font-size:11px;color:{b['muted_color']};opacity:0.7;padding-top:8px;">{b['footer_note']}</div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</div>"""


async def _wrapper(inner_html: str) -> str:
    return build_wrapper(inner_html, await get_brand())


async def send_email(to_email: str, subject: str, html_content: str, attachments: list = None):
    """attachments: [{"filename": "x.pdf", "content": <bytes>}]"""
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


async def send_welcome_email(to_email: str, name: str, password: str):
    html = await _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">Welcome to your Client Portal, {name}</td></tr>
      <tr><td style="font-size:14px;color:#B5B5BC;padding-bottom:20px;">Your agency has set up a secure portal where you can track projects, invoices, files and support tickets.</td></tr>
      <tr><td style="background:#222225;border-radius:8px;padding:16px;font-size:14px;">
        Email: {to_email}<br/>Temporary Password: <b>{password}</b>
      </td></tr>
      <tr><td style="padding-top:20px;"><a href="{FRONTEND_URL}/login" style="background:#F4F4F5;color:#131315;padding:10px 20px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;">Log in to your Portal</a></td></tr>
    """)
    return await send_email(to_email, "Welcome to your Client Portal", html)


async def send_invite_email(to_email: str, name: str, password: str):
    html = await _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">You've been invited to AgencyOS, {name}</td></tr>
      <tr><td style="font-size:14px;color:#B5B5BC;padding-bottom:20px;">You now have team access to manage clients, projects and more.</td></tr>
      <tr><td style="background:#222225;border-radius:8px;padding:16px;font-size:14px;">
        Email: {to_email}<br/>Temporary Password: <b>{password}</b>
      </td></tr>
      <tr><td style="padding-top:20px;"><a href="{FRONTEND_URL}/login" style="background:#F4F4F5;color:#131315;padding:10px 20px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;">Log in to AgencyOS</a></td></tr>
    """)
    return await send_email(to_email, "You've been invited to AgencyOS", html)


async def send_invoice_email(to_email: str, invoice_number: str, total: float, due_date: str, invoice_id: str,
                             currency: str = "INR", pay_url: str = None, has_crypto: bool = False, has_other: bool = False,
                             pdf_bytes: bytes = None):
    code = (currency or "INR").upper()
    target = pay_url or f"{FRONTEND_URL}/portal/invoices/{invoice_id}"

    # Lead with whatever settles best for this currency: crypto for USD (no FX
    # spread, no international card fee), Cashfree for INR.
    prefers_crypto = code == "USD" and has_crypto
    if prefers_crypto:
        primary_label, primary_hint = "Pay with Crypto", "USD settles fastest in crypto"
        primary_url = f"{target}?method=crypto"
        secondary = ("Pay by card or bank", f"{target}?method=other") if has_other else None
    else:
        primary_label, primary_hint = "Pay Your Invoice", "Card, UPI, net banking & wallets"
        primary_url = target
        secondary = ("Pay with crypto instead", f"{target}?method=crypto") if has_crypto else None

    buttons = (f'<a href="{primary_url}" style="display:inline-block;background:#26A17B;color:#FFFFFF;'
               f'padding:13px 28px;border-radius:8px;text-decoration:none;font-size:15px;font-weight:700;">'
               f'{primary_label}</a>'
               f'<div style="font-size:12px;color:#85858C;padding-top:8px;">{primary_hint}</div>')
    if secondary:
        buttons += (f'<div style="padding-top:10px;"><a href="{secondary[1]}" '
                    f'style="font-size:13px;color:#B5B5BC;text-decoration:underline;">{secondary[0]}</a></div>')
    html = await _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">Invoice {invoice_number}</td></tr>
      <tr><td style="font-size:14px;color:#B5B5BC;padding-bottom:20px;">A new invoice has been issued to your account.</td></tr>
      <tr><td style="background:#222225;border-radius:8px;padding:16px;font-size:14px;">
        Amount Due: <b>{code} {total:,.2f}</b><br/>Due Date: {due_date[:10]}
      </td></tr>
      <tr><td style="padding-top:20px;">{buttons}</td></tr>
      {'<tr><td style="font-size:12px;color:#85858C;padding-top:14px;">The full invoice is attached as a PDF for your records.</td></tr>' if pdf_bytes else ''}
    """)
    attachments = [{"filename": f"{invoice_number}.pdf", "content": pdf_bytes}] if pdf_bytes else None
    return await send_email(to_email, f"Invoice {invoice_number} from Obrinex", html, attachments=attachments)


async def send_custom_email(to_email: str, subject: str, body_html: str):
    """Send a user-approved email drafted in the Emails section. Body is plain text/HTML paragraphs."""
    paragraphs = "".join(
        f'<tr><td style="font-size:14px;color:#E4E4E7;line-height:1.7;padding-bottom:12px;">{p.strip()}</td></tr>'
        for p in body_html.split("\n\n") if p.strip()
    )
    html = await _wrapper(paragraphs)
    return await send_email(to_email, subject, html)


async def send_password_reset_email(to_email: str, token: str):
    html = await _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">Reset your password</td></tr>
      <tr><td style="font-size:14px;color:#B5B5BC;padding-bottom:20px;">We received a request to reset your AgencyOS password. This link expires in 1 hour.</td></tr>
      <tr><td><a href="{FRONTEND_URL}/reset-password?token={token}" style="background:#F4F4F5;color:#131315;padding:10px 20px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;">Reset Password</a></td></tr>
    """)
    return await send_email(to_email, "Reset your AgencyOS password", html)


async def send_booking_confirmation_email(to_email: str, name: str, title: str, when_label: str, location: str, company_name: str):
    html = await _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">You're booked, {name}!</td></tr>
      <tr><td style="font-size:14px;color:#B5B5BC;padding-bottom:20px;">Your {title} with {company_name} is confirmed.</td></tr>
      <tr><td style="background:#222225;border-radius:8px;padding:16px;font-size:14px;">
        When: <b>{when_label}</b><br/>Where: {location}
      </td></tr>
      <tr><td style="padding-top:20px;font-size:13px;color:#85858C;">Need to reschedule? Just reply to this email.</td></tr>
    """)
    return await send_email(to_email, f"Confirmed: {title} with {company_name} — {when_label}", html)


async def send_meeting_reminder_email(to_email: str, name: str, title: str, when_label: str, location: str):
    html = await _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">Reminder: {title}</td></tr>
      <tr><td style="font-size:14px;color:#B5B5BC;padding-bottom:20px;">Hi {name}, your meeting starts soon.</td></tr>
      <tr><td style="background:#222225;border-radius:8px;padding:16px;font-size:14px;">
        When: <b>{when_label}</b><br/>Where: {location}
      </td></tr>
    """)
    return await send_email(to_email, f"Starting soon: {title}", html)


async def send_agreement_share_email(to_email: str, title: str, share_token: str, pdf_bytes: bytes = None):
    html = await _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">Agreement: {title}</td></tr>
      <tr><td style="font-size:14px;color:#B5B5BC;padding-bottom:20px;">Please find the full agreement attached as a PDF. When you're ready, review and sign it online.</td></tr>
      <tr><td><a href="{FRONTEND_URL}/agreement/{share_token}" style="background:#F4F4F5;color:#131315;padding:10px 20px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;">Review & Sign Agreement</a></td></tr>
      {'<tr><td style="font-size:12px;color:#85858C;padding-top:14px;">📎 Full agreement attached as PDF.</td></tr>' if pdf_bytes else ''}
    """)
    safe = "".join(ch if ch.isalnum() or ch in "-_ " else "" for ch in title).strip().replace(" ", "_") or "agreement"
    attachments = [{"filename": f"{safe}.pdf", "content": pdf_bytes}] if pdf_bytes else None
    return await send_email(to_email, f"Agreement for signature: {title}", html, attachments=attachments)


OVERDUE_TONES = {
    1: ("Friendly reminder", "Just a friendly note that the invoice below is now past its due date. If you've already made the payment, please ignore this email — otherwise we'd appreciate it being settled at your earliest convenience."),
    2: ("Payment overdue", "This invoice is now more than a week overdue. Please arrange payment as soon as possible, or reply to let us know if there's an issue we can help resolve."),
    3: ("Final notice", "Despite previous reminders, this invoice remains unpaid. Please settle it within 3 business days to avoid interruption of ongoing services."),
}


async def send_overdue_invoice_email(to_email: str, invoice_number: str, total: float, due_date: str, currency: str, level: int):
    subject_prefix, tone = OVERDUE_TONES.get(min(level, 3), OVERDUE_TONES[1])
    code = currency or "INR"
    html = await _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">{subject_prefix}: Invoice {invoice_number}</td></tr>
      <tr><td style="font-size:14px;color:#B5B5BC;padding-bottom:20px;">{tone}</td></tr>
      <tr><td style="background:#222225;border-radius:8px;padding:16px;font-size:14px;">
        Amount Due: <b>{code} {total:,.2f}</b><br/>Was Due: {due_date[:10]}
      </td></tr>
    """)
    return await send_email(to_email, f"{subject_prefix}: Invoice {invoice_number}", html)


async def send_daily_digest_email(to_email: str, digest: dict):
    def _list(items):
        if not items:
            return "<span style='color:#85858C'>None</span>"
        return "<br/>".join(f"&bull; {i}" for i in items)
    html = await _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">Your Daily Brief — {digest['date']}</td></tr>
      <tr><td style="font-size:13px;color:#B5B5BC;padding-bottom:6px;font-weight:700;">📅 Today's Meetings</td></tr>
      <tr><td style="font-size:13px;padding-bottom:14px;">{_list(digest['meetings'])}</td></tr>
      <tr><td style="font-size:13px;color:#B5B5BC;padding-bottom:6px;font-weight:700;">✅ Tasks Due Today</td></tr>
      <tr><td style="font-size:13px;padding-bottom:14px;">{_list(digest['tasks'])}</td></tr>
      <tr><td style="font-size:13px;color:#B5B5BC;padding-bottom:6px;font-weight:700;">🔥 New Leads (24h)</td></tr>
      <tr><td style="font-size:13px;padding-bottom:14px;">{_list(digest['leads'])}</td></tr>
      <tr><td style="font-size:13px;color:#B5B5BC;padding-bottom:6px;font-weight:700;">💰 Overdue Invoices</td></tr>
      <tr><td style="font-size:13px;padding-bottom:14px;">{_list(digest['overdue'])}</td></tr>
      <tr><td style="padding-top:10px;"><a href="{FRONTEND_URL}/dashboard" style="background:#F4F4F5;color:#131315;padding:10px 20px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;">Open Dashboard</a></td></tr>
    """)
    return await send_email(to_email, f"Daily Brief · {digest['date']}", html)


async def send_proposal_share_email(to_email: str, title: str, share_token: str, pdf_bytes: bytes = None):
    html = await _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">Proposal: {title}</td></tr>
      <tr><td style="font-size:14px;color:#B5B5BC;padding-bottom:20px;">Please find the full proposal attached as a PDF. When you're ready, open it online to accept or decline.</td></tr>
      <tr><td><a href="{FRONTEND_URL}/proposal/{share_token}" style="background:#F4F4F5;color:#131315;padding:10px 20px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;">Review & Accept / Decline</a></td></tr>
      {'<tr><td style="font-size:12px;color:#85858C;padding-top:14px;">📎 Full proposal attached as PDF.</td></tr>' if pdf_bytes else ''}
    """)
    safe = "".join(ch if ch.isalnum() or ch in "-_ " else "" for ch in title).strip().replace(" ", "_") or "proposal"
    attachments = [{"filename": f"{safe}.pdf", "content": pdf_bytes}] if pdf_bytes else None
    return await send_email(to_email, f"Proposal: {title}", html, attachments=attachments)
