from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import logging
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
import os

from database import db, client, create_indexes
from seed import seed_admin, seed_company_settings

from routers import auth, crm, clients, portal, projects, finance, documents, support, knowledge, vault, files, notifications, dashboard, search, ai, settings, meetings, automations, public, notes, bookings, leadform, leadfinder, emails, payment_links, sdr, ai_agents
from reminders import reminder_loop, daily_loop

IS_PRODUCTION = os.environ.get("APP_ENV", "development").lower() == "production"
RUN_BACKGROUND_LOOPS = os.environ.get("RUN_BACKGROUND_LOOPS", "false").lower() == "true"
REQUIRED_ENV = ["MONGO_URL", "DB_NAME", "JWT_SECRET", "VAULT_ENCRYPTION_KEY"]


def validate_environment():
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Missing required environment variable(s): {', '.join(missing)}")
    if IS_PRODUCTION:
        weak_values = {"secret", "changeme", "password", "123", "dev", "development"}
        if os.environ["JWT_SECRET"].lower() in weak_values or len(os.environ["JWT_SECRET"]) < 32:
            raise RuntimeError("JWT_SECRET must be a strong production secret")
        if len(os.environ["VAULT_ENCRYPTION_KEY"]) < 32:
            raise RuntimeError("VAULT_ENCRYPTION_KEY must be a valid strong production encryption key")
        if not os.environ.get("CRON_SECRET"):
            raise RuntimeError("CRON_SECRET is required in production for stateless scheduled automation endpoints")


validate_environment()
app = FastAPI(
    title="AgencyOS API",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
)

api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"message": "AgencyOS API"}


app.include_router(api_router)
app.include_router(auth.router)
app.include_router(crm.router)
app.include_router(clients.router)
app.include_router(portal.router)
app.include_router(projects.router)
app.include_router(finance.router)
app.include_router(documents.router)
app.include_router(support.router)
app.include_router(knowledge.router)
app.include_router(vault.router)
app.include_router(files.router)
app.include_router(notifications.router)
app.include_router(dashboard.router)
app.include_router(search.router)
app.include_router(ai.router)
app.include_router(settings.router)
app.include_router(meetings.router)
app.include_router(automations.router)
app.include_router(public.router)
app.include_router(notes.router)
app.include_router(bookings.router)
app.include_router(leadform.router)
app.include_router(leadfinder.router)
app.include_router(emails.router)
app.include_router(payment_links.router)
app.include_router(sdr.router)
app.include_router(ai_agents.router)

allowed_origins = [origin.strip() for origin in os.environ.get("CORS_ORIGINS", os.environ.get("FRONTEND_URL", "http://localhost:3000")).split(",") if origin.strip()]
if "*" in allowed_origins:
    raise RuntimeError("CORS_ORIGINS must list explicit origins when credentials are enabled")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

allowed_hosts = [host.strip() for host in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,192.168.1.13").split(",") if host.strip()]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup_event():
    await create_indexes()
    await seed_admin()
    await seed_company_settings()
    if RUN_BACKGROUND_LOOPS:
        import asyncio
        asyncio.create_task(reminder_loop())
        asyncio.create_task(daily_loop())
        logger.warning("Background loops are enabled. Do not use this mode on Hostinger managed Node.js hosting.")
    else:
        logger.info("Background loops disabled; use authenticated cron endpoints for scheduled jobs")
    logger.info("AgencyOS backend started")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
