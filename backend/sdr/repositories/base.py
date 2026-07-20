"""Shared repository helpers.

`scope()` is the tenancy chokepoint. AgencyOS is single-tenant today - a grep
for org_id/tenant_id/workspace_id across the backend returns nothing, and
`company_settings` is a singleton keyed {"key": "main"}. The spec requires
multi-tenancy, but adding org_id to SDR collections alone would produce a
half-tenanted system whose guarantees are illusory: an SDR lead would be
tenant-scoped while the client it converts into would not.

So: build single-tenant to match the app, but route every read and write
through `scope()`. Adding tenancy later becomes one function body plus a
migration, not an archaeology exercise. See ADR 0002.
"""

from database import db, now_iso, serialize_doc, serialize_list, to_object_id
from sdr.errors import NotFoundError, ValidationError


def scope(query: dict | None = None, *, user: dict | None = None) -> dict:
    """Apply tenant scoping to a query filter.

    Today this is close to a pass-through. Do not bypass it - the value is in
    every query already flowing through one function on the day scoping stops
    being a no-op.
    """
    scoped = dict(query or {})
    # When tenancy lands, this is the line:
    #     scoped["org_id"] = require_org_id(user)
    #
    # Soft-deleted records are excluded everywhere unless a caller explicitly
    # asks for them, which prevents an archived lead from silently reappearing
    # in a campaign.
    scoped.setdefault("deleted_at", None)
    return scoped


def unscoped_include_deleted(query: dict | None = None) -> dict:
    """For the rare read that must see soft-deleted rows (restore, audit)."""
    return dict(query or {})


def object_id(value: str, label: str = "id"):
    """Convert a string id, raising a typed error the router can map to 400."""
    try:
        return to_object_id(value)
    except ValueError:
        raise ValidationError(f"Invalid {label}: '{value}'")


async def get_or_404(collection: str, doc_id: str, label: str = "record") -> dict:
    doc = await db[collection].find_one(scope({"_id": object_id(doc_id, label)}))
    if not doc:
        raise NotFoundError(f"{label.capitalize()} not found")
    return serialize_doc(doc)


async def paginate(collection: str, query: dict, *, sort, limit: int = 50, cursor: str | None = None):
    """Keyset pagination.

    The host app uses `.to_list(1000)` everywhere with no pagination at all
    (Phase 0 report, section 5). That does not survive the lead volumes this
    module targets, so SDR list endpoints paginate from day one. Keyset rather
    than skip/limit because skip degrades linearly and this collection grows.

    `sort` is a (field, direction) pair. The cursor is the last seen value of
    that field, so the index does all the work.
    """
    field, direction = sort
    filters = dict(query)
    if cursor:
        operator = "$lt" if direction < 0 else "$gt"
        filters[field] = {**filters.get(field, {}), operator: cursor}

    limit = max(1, min(int(limit), 200))
    # Over-fetch by one to detect a next page without a second count query.
    docs = await db[collection].find(filters).sort(field, direction).to_list(limit + 1)

    has_more = len(docs) > limit
    docs = docs[:limit]
    next_cursor = docs[-1].get(field) if (has_more and docs) else None

    return {
        "items": serialize_list(docs),
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


def stamp_create(doc: dict, user: dict | None = None) -> dict:
    """Server-owned fields on insert, matching the host app's convention."""
    now = now_iso()
    doc.update({
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    })
    if user:
        doc.setdefault("created_by", user.get("id"))
    return doc


def stamp_update(patch: dict) -> dict:
    patch = dict(patch)
    patch["updated_at"] = now_iso()
    return patch
