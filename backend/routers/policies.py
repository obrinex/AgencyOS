"""Public-facing legal policies, for transparency in the admin + client portal.

Serves ONLY the curated legal documents. Content prefers the owner's dashboard
edit (kb_articles by seed_key) and falls back to the bundled file, so a
lawyer-reviewed edit in the Knowledge Base shows here without a deploy.
"""
import logging
import os

from fastapi import APIRouter, Depends, HTTPException

from auth_utils import get_current_user
from database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/policies", tags=["policies"])

# `backend/legal/`, not the agent knowledge base. These eleven documents used
# to live in `velliom/brand_kb/` alongside the agents' internal knowledge, and
# were moved out when that module was deleted: they are published, client-facing
# legal text - Terms, Privacy, the DPA, the SLA - and their lifetime has nothing
# to do with whichever agent system happens to exist. The rest of that knowledge
# base went with the agents.
_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "legal")

# The only documents exposed to clients. Order is the display order.
POLICIES = [
    {"slug": "terms", "title": "Terms & Conditions", "file": "17-legal-terms-and-conditions.md"},
    {"slug": "privacy", "title": "Privacy Policy", "file": "14-legal-privacy.md"},
    {"slug": "refund-and-cancellation", "title": "Refund & Cancellation Policy", "file": "13-legal-refund-and-cancellation.md"},
    {"slug": "sla", "title": "Service Level Agreement", "file": "19-legal-sla.md"},
    {"slug": "support", "title": "Support Policy", "file": "16-legal-support-document.md"},
    {"slug": "warranty", "title": "Warranty Policy", "file": "23-legal-warranty.md"},
    {"slug": "ip-rights", "title": "Intellectual Property Rights", "file": "20-legal-ip-rights.md"},
    {"slug": "data-processing", "title": "Data Processing Agreement", "file": "18-legal-data-processing-agreement.md"},
    {"slug": "security", "title": "Security Policy", "file": "21-legal-security.md"},
    {"slug": "copyright", "title": "Copyright Policy", "file": "22-legal-copyright.md"},
    {"slug": "disclaimer", "title": "Disclaimer", "file": "15-legal-disclaimer.md"},
]
_BY_SLUG = {p["slug"]: p for p in POLICIES}


async def _content(entry: dict) -> str:
    # Prefer the dashboard-editable copy; fall back to the bundled file.
    art = await db.kb_articles.find_one({"seed_key": entry["file"]})
    if art and (art.get("content") or "").strip():
        return art["content"]
    path = os.path.join(_DIR, entry["file"])
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    # Nothing in the database and nothing on disk. Serverless bundlers trace
    # Python imports, and these are markdown that nothing imports - so a
    # missing file here means the deployment did not ship `backend/legal/`
    # (see `includeFiles` in vercel.json). Say so, rather than returning an
    # empty string that renders as a blank Terms page nobody notices.
    logger.error("Policy file missing from the deployment: %s", path)
    return ""


@router.get("/_health")
async def policies_health(user: dict = Depends(get_current_user)):
    """Which policy documents are actually reachable in this deployment.

    Exists because the failure mode is silent: a policy whose file was not
    bundled and has no database override returns empty and looks like an
    unwritten page rather than a broken deploy.
    """
    return {
        "source_dir": _DIR,
        "missing_files": [
            p["file"] for p in POLICIES
            if not os.path.exists(os.path.join(_DIR, p["file"]))
        ],
    }


@router.get("")
async def list_policies(user: dict = Depends(get_current_user)):
    """Titles + slugs. Any signed-in user (admin or client) may read policies."""
    return [{"slug": p["slug"], "title": p["title"]} for p in POLICIES]


@router.get("/{slug}")
async def get_policy(slug: str, user: dict = Depends(get_current_user)):
    entry = _BY_SLUG.get(slug)
    if not entry:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {"slug": slug, "title": entry["title"], "content": await _content(entry)}


# --- Public --------------------------------------------------------------------
#
# These are legal documents. They exist to be read by people deciding whether to
# work with us, which is exactly the audience that does not have a login — a
# terms page behind authentication is a terms page nobody can check before they
# agree to it. Read-only, no user context, same content as the signed-in routes.

public_router = APIRouter(prefix="/api/public/policies", tags=["policies"])


@public_router.get("")
async def public_list_policies():
    return [{"slug": p["slug"], "title": p["title"]} for p in POLICIES]


@public_router.get("/{slug}")
async def public_get_policy(slug: str):
    entry = _BY_SLUG.get(slug)
    if not entry:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {"slug": slug, "title": entry["title"], "content": await _content(entry)}
