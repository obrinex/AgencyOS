import os
import requests
from datetime import datetime, timedelta

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
from googleapiclient.discovery import build

GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPE = "https://www.googleapis.com/auth/calendar"


def is_configured() -> bool:
    return bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))


def get_redirect_uri() -> str:
    return f"{os.environ['FRONTEND_URL']}/api/meetings/google/callback"


def build_authorization_url(state: str) -> str:
    params = {
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "redirect_uri": get_redirect_uri(),
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    query = "&".join(f"{k}={requests.utils.quote(str(v), safe='')}" for k, v in params.items())
    return f"{GOOGLE_AUTH_URI}?{query}"


def exchange_code_for_tokens(code: str) -> dict:
    resp = requests.post(GOOGLE_TOKEN_URI, data={
        "code": code,
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "redirect_uri": get_redirect_uri(),
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    return resp.json()


def get_user_email(access_token: str) -> str:
    resp = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    resp.raise_for_status()
    return resp.json().get("email")


def _credentials_from_tokens(tokens: dict) -> Credentials:
    return Credentials(
        token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        token_uri=GOOGLE_TOKEN_URI,
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
    )


async def get_calendar_service(tokens: dict, on_refresh=None):
    creds = _credentials_from_tokens(tokens)
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleAuthRequest())
        if on_refresh:
            await on_refresh(creds.token)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def event_body(meeting: dict) -> dict:
    start = meeting["start_time"]
    end = meeting.get("end_time")
    if not end:
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end = (start_dt + timedelta(minutes=30)).isoformat()
        except ValueError:
            end = start
    return {
        "summary": meeting.get("title", "Meeting"),
        "description": meeting.get("notes") or "",
        "start": {"dateTime": start, "timeZone": "UTC"},
        "end": {"dateTime": end, "timeZone": "UTC"},
    }
