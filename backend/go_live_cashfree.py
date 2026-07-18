"""Switch Cashfree from sandbox to live, once your account is actually approved.

Run this from the `backend` directory.

    python go_live_cashfree.py --check     # has Cashfree approved you yet?
    python go_live_cashfree.py --deploy    # switch production over and redeploy

Credentials are read from a file, never hardcoded and never printed. Pass the
CSV Cashfree gave you (format: <app_id>,<secret_key>):

    python go_live_cashfree.py --check --creds "C:/Users/singh/Downloads/APIKey.csv"

--deploy refuses to run unless the pre-flight passes, so a repeat of the
"transactions are not enabled" situation cannot reach production: switching to
credentials that cannot transact would break INR *and* USD and silently drop
every client to crypto.
"""
import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

import aiohttp

PROD_BASE = "https://api.cashfree.com/pg"
API_VERSION = "2023-08-01"
DEFAULT_CREDS = r"C:/Users/singh/Downloads/APIKey.csv"
BACKEND_URL = "https://backend-five-hazel-13.vercel.app"
FRONTEND_URL = "https://obrinexcrm.vercel.app"
WEBHOOK = f"{BACKEND_URL}/api/public/cashfree/webhook"


def read_creds(path: str):
    p = Path(path)
    if not p.exists():
        sys.exit(f"! Credentials file not found: {p}")
    text = p.read_text(encoding="utf-8-sig").strip()
    for line in text.splitlines():
        parts = [x.strip() for x in line.split(",") if x.strip()]
        if len(parts) >= 2:
            app_id, secret = parts[0], parts[1]
            if "test" in secret.lower():
                sys.exit("! That is a SANDBOX key (cfsk_ma_test_...). Use the live pair.")
            return app_id, secret
    sys.exit("! Could not parse '<app_id>,<secret_key>' from the file.")


def headers(app_id: str, secret: str) -> dict:
    return {
        "x-client-id": app_id,
        "x-client-secret": secret,
        "x-api-version": API_VERSION,
        "Content-Type": "application/json",
    }


async def preflight(app_id: str, secret: str) -> bool:
    """Confirm the live account can authenticate AND actually transact."""
    h = headers(app_id, secret)
    timeout = aiohttp.ClientTimeout(total=25)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        # 1. credentials - a link that cannot exist: 404 good, 401 bad
        async with s.get(f"{PROD_BASE}/links/obx_preflight_zzz", headers=h) as r:
            if r.status == 401:
                print("  credentials     : FAILED (authentication rejected)")
                return False
            print("  credentials     : ok")

        # 2. can it create a real link? ₹1, cancelled straight after.
        ok = True
        for currency in ("INR", "USD"):
            body = {
                "link_id": f"obx_preflight_{currency.lower()}",
                "link_amount": 1,
                "link_currency": currency,
                "link_purpose": "pre-flight capability check",
                "customer_details": {"customer_phone": "9999999999"},
                "link_notify": {"send_email": False, "send_sms": False},
            }
            async with s.post(f"{PROD_BASE}/links", json=body, headers=h) as r:
                data = await r.json(content_type=None)
                if r.status < 400:
                    print(f"  {currency} payments  : ENABLED")
                    lid = data.get("link_id")
                    if lid:
                        async with s.post(f"{PROD_BASE}/links/{lid}/cancel", headers=h):
                            pass  # tidy up the probe link
                else:
                    msg = (data or {}).get("message", f"HTTP {r.status}")
                    print(f"  {currency} payments  : BLOCKED - {msg}")
                    if currency == "INR":
                        ok = False  # INR is the must-have; USD is optional
        return ok


def run(cmd: list, cwd: str = ".") -> bool:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, shell=True)
    if result.returncode != 0:
        print(f"    ! {' '.join(cmd[:3])} failed: {(result.stderr or '')[:200]}")
        return False
    return True


def set_env(key: str, value: str) -> None:
    """Replace a Vercel production env var (remove-then-add; remove may no-op)."""
    subprocess.run(["npx", "vercel", "env", "rm", key, "production", "--yes"],
                   capture_output=True, text=True, shell=True)
    p = subprocess.run(["npx", "vercel", "env", "add", key, "production"],
                       input=value, capture_output=True, text=True, shell=True)
    print(f"    {key}: {'set' if p.returncode == 0 else 'FAILED'}")


def deploy(project_dir: str, label: str) -> bool:
    print(f"    deploying {label} ...")
    return run(["npx", "vercel", "--prod", "--yes"], cwd=project_dir)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="only test whether Cashfree has approved you")
    ap.add_argument("--deploy", action="store_true", help="switch production to live and redeploy")
    ap.add_argument("--creds", default=DEFAULT_CREDS)
    args = ap.parse_args()
    if not (args.check or args.deploy):
        ap.error("pass --check or --deploy")

    app_id, secret = read_creds(args.creds)
    print(f"Cashfree LIVE account ...{app_id[-4:]}  ({PROD_BASE})\n")
    print("Pre-flight:")
    ready = await preflight(app_id, secret)
    print()

    if not ready:
        print("NOT READY - your account still cannot take live INR payments.")
        print("Email care@cashfree.com and ask them to approve live transactions")
        print("and the payment-links API (mention USD/international too).")
        print("Nothing was changed. Re-run --check when they confirm.")
        return 1

    print("READY - the live account can create payment links.")
    if args.check:
        print("\nThis was a check only. Re-run with --deploy to go live.")
        return 0

    print("\nSwitching production to live:")
    set_env("CASHFREE_APP_ID", app_id)
    set_env("CASHFREE_SECRET_KEY", secret)
    set_env("CASHFREE_ENV", "production")

    print("\nRedeploying:")
    if not deploy(".", "backend"):
        print("! Backend deploy failed - production still on the previous build.")
        return 1
    if not deploy("../frontend", "frontend"):
        print("! Frontend deploy failed. Backend is live; rerun the frontend deploy.")
        return 1

    print(f"""
LIVE. Real payments will now be taken.

  Verify:
    1. {FRONTEND_URL} - open an INR invoice's payment page.
       The orange "Test mode" banner must be GONE.
    2. Register the webhook in the Cashfree dashboard:
         {WEBHOOK}
       Without it, invoices settle only via the twice-daily reconciliation.
    3. Make one small real payment and confirm the invoice flips to paid.

  Roll back (returns to sandbox, payments stop being real):
    npx vercel env rm CASHFREE_ENV production --yes
    printf sandbox | npx vercel env add CASHFREE_ENV production
    npx vercel --prod --yes
""")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
