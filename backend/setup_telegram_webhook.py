"""Register (or inspect) the Telegram webhook. Run once per environment.

Reads the token from the environment so it never appears in shell history or
in a command you might paste somewhere.

    # inspect what Telegram currently has
    python setup_telegram_webhook.py

    # point Telegram at production
    python setup_telegram_webhook.py --url https://<backend>.vercel.app/api/gateway/telegram

    # stop delivery entirely
    python setup_telegram_webhook.py --delete

Requires TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET in backend/.env or the
process environment. The secret is what the gateway checks on every inbound
request; without it the adapter refuses all traffic by design.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

API = "https://api.telegram.org"


def _redact(value: str) -> str:
    """Never print a token, even partially enough to be useful."""
    return f"<set, {len(value)} chars>" if value else "<missing>"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="Public HTTPS webhook URL")
    parser.add_argument("--delete", action="store_true", help="Remove the webhook")
    args = parser.parse_args()

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")

    print(f"TELEGRAM_BOT_TOKEN:      {_redact(token)}")
    print(f"TELEGRAM_WEBHOOK_SECRET: {_redact(secret)}\n")

    if not token:
        print("TELEGRAM_BOT_TOKEN is not set. Add it to backend/.env (local) or "
              "the Vercel backend project (production), then re-run.")
        return 1

    async with httpx.AsyncClient(timeout=20) as client:
        if args.delete:
            response = await client.post(f"{API}/bot{token}/deleteWebhook")
            print("deleteWebhook:", response.json())
            return 0

        if args.url:
            if not args.url.startswith("https://"):
                print("Telegram requires an HTTPS webhook URL.")
                return 1
            if not secret:
                print("TELEGRAM_WEBHOOK_SECRET is not set. Generate one first:\n"
                      "  python -c \"import secrets; print(secrets.token_urlsafe(32))\"\n"
                      "Without it the gateway refuses every inbound request.")
                return 1

            response = await client.post(
                f"{API}/bot{token}/setWebhook",
                json={
                    "url": args.url,
                    "secret_token": secret,
                    # Only what the gateway acts on. Fewer update types is less
                    # traffic and a smaller surface.
                    "allowed_updates": ["message", "edited_message", "callback_query"],
                    # A redeploy leaves stale updates queued; dropping them
                    # avoids the bot answering questions from an hour ago.
                    "drop_pending_updates": True,
                },
            )
            print("setWebhook:", response.json())

        info = await client.post(f"{API}/bot{token}/getWebhookInfo")
        result = info.json().get("result", {})
        print("\ncurrent webhook:")
        for key in ("url", "has_custom_certificate", "pending_update_count",
                    "last_error_date", "last_error_message", "allowed_updates"):
            if key in result:
                print(f"  {key}: {result[key]}")

        me = await client.post(f"{API}/bot{token}/getMe")
        bot = me.json().get("result", {})
        if bot:
            print(f"\nbot: @{bot.get('username')} ({bot.get('first_name')})")

    return 0


sys.exit(asyncio.run(main()))
