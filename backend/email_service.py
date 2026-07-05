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


async def send_invoice_email(to_email: str, invoice_number: str, total: float, due_date: str, invoice_id: str):
    html = _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">Invoice {invoice_number}</td></tr>
      <tr><td style="font-size:14px;color:#B5B5BC;padding-bottom:20px;">A new invoice has been issued to your account.</td></tr>
      <tr><td style="background:#222225;border-radius:8px;padding:16px;font-size:14px;">
        Amount Due: <b>${total:,.2f}</b><br/>Due Date: {due_date[:10]}
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


async def send_proposal_share_email(to_email: str, title: str, share_token: str):
    html = _wrapper(f"""
      <tr><td style="font-size:20px;font-weight:700;padding-bottom:12px;">Proposal: {title}</td></tr>
      <tr><td style="font-size:14px;color:#B5B5BC;padding-bottom:20px;">Your agency has shared a proposal for your review and approval.</td></tr>
      <tr><td><a href="{FRONTEND_URL}/proposal/{share_token}" style="background:#F4F4F5;color:#131315;padding:10px 20px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;">View Proposal</a></td></tr>
    """)
    return await send_email(to_email, f"Proposal: {title}", html)
