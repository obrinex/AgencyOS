"""WhatsApp notifications via the Meta WhatsApp Business Cloud API.

Required env vars (all three) — until they are set, messages are logged instead of sent:
  WHATSAPP_ACCESS_TOKEN     - permanent token from Meta Business (developers.facebook.com)
  WHATSAPP_PHONE_NUMBER_ID  - the sender phone number ID from the WhatsApp app dashboard
  WHATSAPP_ADMIN_NUMBER     - your own number with country code, e.g. 919876543210
"""
import os
import logging
import httpx

logger = logging.getLogger(__name__)

ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
ADMIN_NUMBER = os.environ.get("WHATSAPP_ADMIN_NUMBER")

API_VERSION = "v21.0"


def is_configured() -> bool:
    return bool(ACCESS_TOKEN and PHONE_NUMBER_ID)


async def send_whatsapp(to_number: str, message: str):
    """Send a plain-text WhatsApp message. Logs instead of sending when unconfigured."""
    if not is_configured() or not to_number:
        logger.info(f"[WHATSAPP MOCKED - not configured] To: {to_number or '(no number)'} | {message[:120]}")
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}/messages",
                headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": to_number.lstrip("+"),
                    "type": "text",
                    "text": {"body": message[:4096]},
                },
            )
            if resp.status_code >= 400:
                logger.error(f"WhatsApp send failed ({resp.status_code}): {resp.text[:300]}")
                return None
            logger.info(f"WhatsApp sent to {to_number}")
            return resp.json()
    except Exception as e:
        logger.error(f"WhatsApp send error: {e}")
        return None


async def notify_admin(message: str):
    """Send a WhatsApp message to the agency owner."""
    return await send_whatsapp(ADMIN_NUMBER, message)
