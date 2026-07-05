from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import logging
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware
import os

from database import db, client, create_indexes
from seed import seed_admin, seed_company_settings

from routers import auth, crm, clients, portal, projects, finance, documents, support, knowledge, vault, files, notifications, dashboard, search, ai, settings, meetings, automations, public, notes

app = FastAPI(title="AgencyOS API")

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

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000")],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup_event():
    await create_indexes()
    await seed_admin()
    await seed_company_settings()
    logger.info("AgencyOS backend started")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
