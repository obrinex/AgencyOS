import os
import asyncio
import logging
import resend

logger = logging.getLogger(__name__)
resend.api_key = os.environ.get("RESEND_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "")


async def send_email(to_email: str, subject: str, html_content: str):
    if not resend.api_key:
        logger.info(f"[EMAIL MOCKED - no RESEND_API_KEY] To: {to_email} | Subject: {subject}")
        return None
    try:
        params = {"from": SENDER_EMAIL, "to": [to_email], "subject": subject, "html": html_content}
        result = await asyncio.to_thread(resend.Emails.send, params)
        logger.info(f"Email sent to {to_email}: {subject}")
        return result
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return None


def _wrapper(inner_html: str) -> str:
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#131315;padding:32px 0;font-family:Arial,sans-serif;">
      <tr><td align="center">
        <table width="480" cellpadding="0" cellspacing="0" style="background:#18181A;border-radius:12px;padding:32px;color:#F4F4F5;">
          <tr><td style="font-size:12px;letter-spacing:2px;color:#85858C;padding-bottom:16px;">AGENCYOS &middot; OBRINEX</td></tr>
          {inner_html}
          <tr><td style="font-size:11px;color:#85858C;padding-top:24px;border-top:1px solid #222225;margin-top:16px;">
            Note: Please check your spam folder if this email is not delivered to your inbox.
          </td></tr>
        </table>
      </td></tr>
    </table>
    """


async def send_welcome_email(to_email: str, name: str, password: str):
    html = _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">Welcome to your Client Portal, {name}</td></tr>
      <tr><td style="font-size:14px;color:#B5B5BC;padding-bottom:20px;">Your agency has set up a secure portal where you can track projects, invoices, files and support tickets.</td></tr>
      <tr><td style="background:#222225;border-radius:8px;padding:16px;font-size:14px;">
        Email: {to_email}<br/>Temporary Password: <b>{password}</b>
      </td></tr>
      <tr><td style="padding-top:20px;"><a href="{FRONTEND_URL}/login" style="background:#F4F4F5;color:#131315;padding:10px 20px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;">Log in to your Portal</a></td></tr>
    """)
    return await send_email(to_email, "Welcome to your Client Portal", html)


async def send_invite_email(to_email: str, name: str, password: str):
    html = _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">You've been invited to AgencyOS, {name}</td></tr>
      <tr><td style="font-size:14px;color:#B5B5BC;padding-bottom:20px;">You now have team access to manage clients, projects and more.</td></tr>
      <tr><td style="background:#222225;border-radius:8px;padding:16px;font-size:14px;">
        Email: {to_email}<br/>Temporary Password: <b>{password}</b>
      </td></tr>
      <tr><td style="padding-top:20px;"><a href="{FRONTEND_URL}/login" style="background:#F4F4F5;color:#131315;padding:10px 20px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;">Log in to AgencyOS</a></td></tr>
    """)
    return await send_email(to_email, "You've been invited to AgencyOS", html)


async def send_invoice_email(to_email: str, invoice_number: str, total: float, due_date: str, invoice_id: str, currency: str = "INR"):
    code = currency or "INR"
    html = _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">Invoice {invoice_number}</td></tr>
      <tr><td style="font-size:14px;color:#B5B5BC;padding-bottom:20px;">A new invoice has been issued to your account.</td></tr>
      <tr><td style="background:#222225;border-radius:8px;padding:16px;font-size:14px;">
        Amount Due: <b>{code} {total:,.2f}</b><br/>Due Date: {due_date[:10]}
      </td></tr>
      <tr><td style="padding-top:20px;"><a href="{FRONTEND_URL}/portal/invoices/{invoice_id}" style="background:#F4F4F5;color:#131315;padding:10px 20px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;">View & Pay Invoice</a></td></tr>
    """)
    return await send_email(to_email, f"Invoice {invoice_number} from your agency", html)


async def send_password_reset_email(to_email: str, token: str):
    html = _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">Reset your password</td></tr>
      <tr><td style="font-size:14px;color:#B5B5BC;padding-bottom:20px;">We received a request to reset your AgencyOS password. This link expires in 1 hour.</td></tr>
      <tr><td><a href="{FRONTEND_URL}/reset-password?token={token}" style="background:#F4F4F5;color:#131315;padding:10px 20px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;">Reset Password</a></td></tr>
    """)
    return await send_email(to_email, "Reset your AgencyOS password", html)


async def send_booking_confirmation_email(to_email: str, name: str, title: str, when_label: str, location: str, company_name: str):
    html = _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">You're booked, {name}!</td></tr>
      <tr><td style="font-size:14px;color:#B5B5BC;padding-bottom:20px;">Your {title} with {company_name} is confirmed.</td></tr>
      <tr><td style="background:#222225;border-radius:8px;padding:16px;font-size:14px;">
        When: <b>{when_label}</b><br/>Where: {location}
      </td></tr>
      <tr><td style="padding-top:20px;font-size:13px;color:#85858C;">Need to reschedule? Just reply to this email.</td></tr>
    """)
    return await send_email(to_email, f"Confirmed: {title} with {company_name} — {when_label}", html)


async def send_meeting_reminder_email(to_email: str, name: str, title: str, when_label: str, location: str):
    html = _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">Reminder: {title}</td></tr>
      <tr><td style="font-size:14px;color:#B5B5BC;padding-bottom:20px;">Hi {name}, your meeting starts soon.</td></tr>
      <tr><td style="background:#222225;border-radius:8px;padding:16px;font-size:14px;">
        When: <b>{when_label}</b><br/>Where: {location}
      </td></tr>
    """)
    return await send_email(to_email, f"Starting soon: {title}", html)


async def send_agreement_share_email(to_email: str, title: str, share_token: str):
    html = _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">Agreement: {title}</td></tr>
      <tr><td style="font-size:14px;color:#B5B5BC;padding-bottom:20px;">Your agency has shared a service agreement for your review and signature.</td></tr>
      <tr><td><a href="{FRONTEND_URL}/agreement/{share_token}" style="background:#F4F4F5;color:#131315;padding:10px 20px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;">Review & Sign Agreement</a></td></tr>
    """)
    return await send_email(to_email, f"Agreement for signature: {title}", html)


OVERDUE_TONES = {
    1: ("Friendly reminder", "Just a friendly note that the invoice below is now past its due date. If you've already made the payment, please ignore this email — otherwise we'd appreciate it being settled at your earliest convenience."),
    2: ("Payment overdue", "This invoice is now more than a week overdue. Please arrange payment as soon as possible, or reply to let us know if there's an issue we can help resolve."),
    3: ("Final notice", "Despite previous reminders, this invoice remains unpaid. Please settle it within 3 business days to avoid interruption of ongoing services."),
}


async def send_overdue_invoice_email(to_email: str, invoice_number: str, total: float, due_date: str, currency: str, level: int):
    subject_prefix, tone = OVERDUE_TONES.get(min(level, 3), OVERDUE_TONES[1])
    code = currency or "INR"
    html = _wrapper(f"""
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
    html = _wrapper(f"""
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


async def send_proposal_share_email(to_email: str, title: str, share_token: str):
    html = _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">Proposal: {title}</td></tr>
      <tr><td style="font-size:14px;color:#B5B5BC;padding-bottom:20px;">Your agency has shared a proposal for your review and approval.</td></tr>
      <tr><td><a href="{FRONTEND_URL}/proposal/{share_token}" style="background:#F4F4F5;color:#131315;padding:10px 20px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;">View Proposal</a></td></tr>
    """)
    return await send_email(to_email, f"Proposal: {title}", html)


async def send_payment_link_email(to_email: str, invoice_number: str, total: float, payment_link: str, currency: str = "INR"):
    code = currency or "INR"
    html = _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">Payment Link for Invoice {invoice_number}</td></tr>
      <tr><td style="font-size:14px;color:#B5B5BC;padding-bottom:20px;">Your agency has generated a secure payment link for your invoice {invoice_number}.</td></tr>
      <tr><td style="background:#222225;border-radius:8px;padding:16px;font-size:14px;">
        Amount Due: <b>{code} {total:,.2f}</b>
      </td></tr>
      <tr><td style="padding-top:20px;"><a href="{payment_link}" style="background:#F4F4F5;color:#131315;padding:10px 20px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;">Pay Invoice Now</a></td></tr>
      <tr><td style="font-size:12px;color:#85858C;padding-top:20px;">If the button above does not work, copy and paste this URL into your browser:<br/>{payment_link}</td></tr>
    """)
    return await send_email(to_email, f"Payment link for Invoice {invoice_number}", html)
