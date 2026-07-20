"""Website audits and the opportunity signals derived from them.

Audits are append-only: a new audit never overwrites the previous one, so a
prospect's site improving (or the pitch going stale) is visible as history
rather than being silently rewritten. Signals *are* replaced per audit, since
a signal is a derived view of one audit and a stale one would be a claim we
no longer stand behind.
"""

from database import db, now_iso, serialize_doc, serialize_list
from sdr.collections import OPPORTUNITY_SIGNALS, WEBSITE_AUDITS
from sdr.domain import signals as signals_domain
from sdr.repositories.base import object_id, paginate, scope, stamp_create

AUDIT_VERSION = "1.0.0-http"


async def save_audit(company_id: str, facts: dict, *, status: str = "completed",
                     error: str | None = None, url: str | None = None,
                     unmeasured: tuple = ()) -> dict:
    doc = {
        "company_id": company_id,
        "audit_version": AUDIT_VERSION,
        "audited_at": now_iso(),
        "status": status,
        "url": url,
        "error": error,
        "facts": facts,
        # Recorded on every audit so a reader can see what was *not* checked.
        # An audit that silently omits Core Web Vitals reads like a clean
        # bill of health on performance.
        "unmeasured": list(unmeasured),
    }
    stamp_create(doc)
    result = await db[WEBSITE_AUDITS].insert_one(doc)
    return serialize_doc(await db[WEBSITE_AUDITS].find_one({"_id": result.inserted_id}))


async def latest_audit(company_id: str) -> dict | None:
    docs = await db[WEBSITE_AUDITS].find(scope({"company_id": company_id})) \
        .sort("audited_at", -1).to_list(1)
    return serialize_doc(docs[0]) if docs else None


async def audit_history(company_id: str, limit: int = 10) -> list:
    docs = await db[WEBSITE_AUDITS].find(scope({"company_id": company_id})) \
        .sort("audited_at", -1).to_list(limit)
    return serialize_list(docs)


async def list_audits(*, status: str | None = None, limit: int = 50,
                      cursor: str | None = None) -> dict:
    query = {}
    if status:
        query["status"] = status
    return await paginate(WEBSITE_AUDITS, scope(query), sort=("audited_at", -1),
                          limit=limit, cursor=cursor)


async def replace_signals(company_id: str, audit_id: str, detected: list) -> list:
    """Swap in the signals for a company's newest audit.

    Deleting first is intentional: a signal is a claim about the site as it is
    now. Keeping a `no_ssl` row after the prospect installed a certificate
    would put a false statement into an outreach email.
    """
    await db[OPPORTUNITY_SIGNALS].delete_many({"company_id": company_id})
    if not detected:
        return []

    docs = []
    for row in detected:
        doc = dict(row)
        doc.update({
            "company_id": company_id,
            "website_audit_id": audit_id,
            "confidence": signals_domain.confidence(row),
            "detected_at": now_iso(),
        })
        stamp_create(doc)
        docs.append(doc)

    await db[OPPORTUNITY_SIGNALS].insert_many(docs)
    return serialize_list(
        await db[OPPORTUNITY_SIGNALS].find({"company_id": company_id}).to_list(50)
    )


async def signals_for(company_id: str) -> list:
    docs = await db[OPPORTUNITY_SIGNALS].find(scope({"company_id": company_id})) \
        .to_list(50)
    rows = serialize_list(docs)
    rows.sort(
        key=lambda row: signals_domain.SEVERITY_RANK.get(row.get("severity"), 0),
        reverse=True,
    )
    return rows


async def signal_counts() -> list:
    """Which gaps are most common across the database.

    Drives the Audits page summary, and is genuinely useful for positioning -
    if 70% of prospects have no booking system, that is the offer to lead with.
    """
    cursor = db[OPPORTUNITY_SIGNALS].aggregate([
        {"$group": {
            "_id": "$signal_key",
            "count": {"$sum": 1},
            "severity": {"$first": "$severity"},
            "label": {"$first": "$label"},
        }},
        {"$sort": {"count": -1}},
    ])
    rows = await cursor.to_list(50)
    return [
        {"signal_key": row["_id"], "label": row.get("label"),
         "severity": row.get("severity"), "count": row["count"]}
        for row in rows
    ]


async def get_audit(audit_id: str) -> dict | None:
    doc = await db[WEBSITE_AUDITS].find_one({"_id": object_id(audit_id, "audit id")})
    return serialize_doc(doc)
