"""AI Lead Finder.

Finds REAL businesses worldwide via OpenStreetMap (free, no API key):
  - Nominatim geocodes the city
  - Overpass API returns businesses of the chosen type with name/address/phone/website
Then the NVIDIA AI analyzes each business: which of the agency's services to pitch,
plus a ready-to-send cold email and WhatsApp message.
"""
import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
import httpx
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from database import db, serialize_doc
from auth_utils import require_staff

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/leadfinder", tags=["leadfinder"])

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URLS = [
    url.strip()
    for url in os.environ.get(
        "OVERPASS_URLS",
        "https://overpass-api.de/api/interpreter,https://overpass.kumi.systems/api/interpreter,https://overpass.openstreetmap.ru/api/interpreter",
    ).split(",")
    if url.strip()
]
USER_AGENT = "AgencyOS-LeadFinder/1.0 (info@obrinex.space)"

# niche -> OSM tag filters
NICHES = {
    "cafe": '["amenity"="cafe"]',
    "restaurant": '["amenity"="restaurant"]',
    "dental_clinic": '["amenity"="dentist"]',
    "medical_clinic": '["amenity"="clinic"]',
    "doctor": '["amenity"="doctors"]',
    "pharmacy": '["amenity"="pharmacy"]',
    "salon": '["shop"="hairdresser"]',
    "beauty": '["shop"="beauty"]',
    "gym": '["leisure"="fitness_centre"]',
    "hotel": '["tourism"="hotel"]',
    "real_estate": '["office"="estate_agent"]',
    "lawyer": '["office"="lawyer"]',
    "accountant": '["office"="accountant"]',
    "veterinary": '["amenity"="veterinary"]',
    "car_repair": '["shop"="car_repair"]',
}

NICHE_SEARCH_TERMS = {
    "cafe": "cafe",
    "restaurant": "restaurant",
    "dental_clinic": "dentist",
    "medical_clinic": "clinic",
    "doctor": "doctor",
    "pharmacy": "pharmacy",
    "salon": "hair salon",
    "beauty": "beauty salon",
    "gym": "gym",
    "hotel": "hotel",
    "real_estate": "real estate agent",
    "lawyer": "lawyer",
    "accountant": "accountant",
    "veterinary": "veterinary clinic",
    "car_repair": "car repair",
}


class SearchRequest(BaseModel):
    niche: str
    city: str
    country: Optional[str] = None
    limit: Optional[int] = 25


class AnalyzeRequest(BaseModel):
    business: dict
    niche: str


class ImportRequest(BaseModel):
    business: dict
    niche: str
    analysis: Optional[dict] = None


async def _fallback_nominatim_businesses(client: httpx.AsyncClient, payload: SearchRequest, place: dict) -> list:
    query_place = payload.city + (f", {payload.country}" if payload.country else "")
    term = NICHE_SEARCH_TERMS.get(payload.niche, payload.niche.replace("_", " "))
    limit = min(int(payload.limit or 25), 25)
    resp = await client.get(
        NOMINATIM_URL,
        params={
            "q": f"{term} in {query_place}",
            "format": "json",
            "limit": limit,
            "addressdetails": 1,
            "extratags": 1,
            "namedetails": 1,
        },
    )
    if resp.status_code != 200:
        return []
    businesses = []
    seen_names = set()
    for item in resp.json():
        name = (
            (item.get("namedetails") or {}).get("name")
            or item.get("name")
            or item.get("display_name", "").split(",")[0]
        )
        if not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())
        address = item.get("display_name") or payload.city
        extra = item.get("extratags") or {}
        businesses.append({
            "name": name,
            "address": address,
            "phone": extra.get("phone") or extra.get("contact:phone"),
            "website": extra.get("website") or extra.get("contact:website"),
            "email": extra.get("email") or extra.get("contact:email"),
            "opening_hours": extra.get("opening_hours"),
            "cuisine": extra.get("cuisine"),
            "city": payload.city,
            "country": payload.country or place.get("display_name", "").split(",")[-1].strip(),
            "niche": payload.niche,
            "osm_id": f"nominatim/{item.get('osm_type', 'place')}/{item.get('osm_id') or item.get('place_id')}",
        })
    return businesses


@router.get("/niches")
async def list_niches(user: dict = Depends(require_staff)):
    return {"niches": list(NICHES.keys())}


@router.post("/search")
async def search_businesses(payload: SearchRequest, user: dict = Depends(require_staff)):
    if payload.niche not in NICHES:
        raise HTTPException(status_code=400, detail=f"Niche must be one of: {', '.join(NICHES)}")
    query_place = payload.city + (f", {payload.country}" if payload.country else "")

    # Short per-request timeouts: worst case (geocode + all mirrors + fallback) must
    # stay under the serverless function limit instead of hanging on one slow mirror.
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0), headers={"User-Agent": USER_AGENT}) as client:
        # 1. Geocode the city to a bounding box
        geo = await client.get(NOMINATIM_URL, params={"q": query_place, "format": "json", "limit": 1})
        if geo.status_code != 200 or not geo.json():
            raise HTTPException(status_code=404, detail=f"Could not find \"{query_place}\" — check the city name")
        place = geo.json()[0]
        south, north, west, east = [float(x) for x in place["boundingbox"]]

        # 2. Query Overpass for businesses of this type in the area
        tag = NICHES[payload.niche]
        overpass_query = f"""
        [out:json][timeout:8];
        (
          node{tag}({south},{west},{north},{east});
          way{tag}({south},{west},{north},{east});
        );
        out center tags {min(int(payload.limit or 25) * 3, 150)};
        """
        elements = None
        last_error = None
        for overpass_url in OVERPASS_URLS:
            try:
                resp = await client.post(overpass_url, data={"data": overpass_query})
                if resp.status_code == 200:
                    elements = resp.json().get("elements", [])
                    break
                last_error = f"{overpass_url} returned HTTP {resp.status_code}"
            except Exception as exc:
                last_error = f"{overpass_url} failed: {str(exc)}"
                logger.warning("Lead Finder Overpass request failed", exc_info=True)
        if elements is None:
            fallback_businesses = await _fallback_nominatim_businesses(client, payload, place)
            if fallback_businesses:
                return {
                    "place": place.get("display_name"),
                    "count": len(fallback_businesses),
                    "businesses": fallback_businesses,
                    "source": "nominatim_fallback",
                }
            raise HTTPException(status_code=502, detail=f"Business database is busy — try again in a minute ({last_error})")

    businesses = []
    seen_names = set()
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())
        addr_parts = [tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:suburb"),
                      tags.get("addr:city") or payload.city, tags.get("addr:postcode")]
        businesses.append({
            "name": name,
            "address": ", ".join(p for p in addr_parts if p) or f"{payload.city}",
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "website": tags.get("website") or tags.get("contact:website"),
            "email": tags.get("email") or tags.get("contact:email"),
            "opening_hours": tags.get("opening_hours"),
            "cuisine": tags.get("cuisine"),
            "city": payload.city,
            "country": payload.country or place.get("display_name", "").split(",")[-1].strip(),
            "niche": payload.niche,
            "osm_id": f"{el.get('type', 'node')}/{el.get('id')}",
        })
        if len(businesses) >= (payload.limit or 25):
            break

    return {"place": place.get("display_name"), "count": len(businesses), "businesses": businesses}


NICHE_PITCH_CONTEXT = {
    "cafe": "cafes struggle with repeat customers, online orders, review management, and social media consistency",
    "restaurant": "restaurants need table booking automation, review responses, delivery-platform sync, and social content",
    "dental_clinic": "dental clinics lose money on no-shows, slow appointment booking, and unanswered patient queries after hours",
    "medical_clinic": "clinics need appointment scheduling automation, patient reminders, and 24/7 query handling",
    "doctor": "private practices need appointment booking, patient follow-up automation, and reputation management",
    "pharmacy": "pharmacies benefit from refill reminders, WhatsApp ordering, and inventory alerts",
    "salon": "salons lose revenue to no-shows and manual booking; Instagram automation drives their bookings",
    "beauty": "beauty businesses thrive on Instagram automation, booking systems, and review management",
    "gym": "gyms need member onboarding automation, churn-prevention follow-ups, and class booking systems",
    "hotel": "hotels need direct-booking chatbots to reduce OTA commissions and guest-query automation",
    "real_estate": "estate agents need lead qualification chatbots, property-matching automation, and follow-up sequences",
    "lawyer": "law firms need client intake automation, appointment scheduling, and document workflows",
    "accountant": "accounting firms need client onboarding automation, document collection, and deadline reminders",
    "veterinary": "vet clinics need appointment reminders, vaccination follow-ups, and after-hours query handling",
    "car_repair": "garages need booking systems, service reminders, and quote-request automation",
}


@router.post("/analyze")
async def analyze_business(payload: AnalyzeRequest, user: dict = Depends(require_staff)):
    from routers.ai import _get_client, NVIDIA_MODEL
    client = _get_client()
    b = payload.business
    context = NICHE_PITCH_CONTEXT.get(payload.niche, "small businesses need automation to save time and win customers")

    prompt = (
        f"You are the sales strategist for Obrinex, an AI automation agency (chatbots, booking automation, "
        f"WhatsApp automation, review management, social media automation, custom AI agents, websites).\n\n"
        f"Target business:\n"
        f"- Name: {b.get('name')}\n- Type: {payload.niche.replace('_', ' ')}\n"
        f"- Location: {b.get('address')}, {b.get('city')}, {b.get('country')}\n"
        f"- Website: {b.get('website') or 'none found (opportunity!)'}\n"
        f"- Phone: {b.get('phone') or 'not listed'}\n\n"
        f"Industry context: {context}.\n\n"
        f"Return STRICT JSON (no markdown) with exactly these keys:\n"
        f'{{"services": ["3-4 specific Obrinex services worth pitching, most relevant first"],'
        f'"reason": "1-2 sentences on why this business specifically needs these",'
        f'"cold_email": "a personalized cold email, under 130 words, mentioning their business by name, ending with a soft call-to-action for a free 15-min call",'
        f'"whatsapp_message": "a casual 50-word-max WhatsApp/DM version of the pitch"}}'
    )
    try:
        resp = await client.chat.completions.create(
            model=NVIDIA_MODEL,
            messages=[{"role": "system", "content": "You output only valid JSON. No markdown fences, no commentary."},
                      {"role": "user", "content": prompt}],
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI pitch generation failed: {str(exc)}")
    raw = resp.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()
    try:
        analysis = json.loads(raw)
    except json.JSONDecodeError:
        analysis = {"services": ["AI chatbot", "Booking automation"], "reason": raw[:300],
                    "cold_email": raw[:800], "whatsapp_message": ""}
    return analysis


@router.post("/import")
async def import_to_crm(payload: ImportRequest, user: dict = Depends(require_staff)):
    b = payload.business
    a = payload.analysis or {}
    now = datetime.now(timezone.utc).isoformat()
    existing = await db.leads.find_one({"company": b.get("name"), "source": "ai_finder"})
    if existing:
        raise HTTPException(status_code=400, detail="This business is already in your pipeline")

    notes_parts = [f"Found via AI Lead Finder ({payload.niche.replace('_', ' ')} in {b.get('city')})"]
    if b.get("address"):
        notes_parts.append(f"Address: {b['address']}")
    if b.get("opening_hours"):
        notes_parts.append(f"Hours: {b['opening_hours']}")
    if a.get("reason"):
        notes_parts.append(f"\nWhy they need us: {a['reason']}")
    if a.get("services"):
        notes_parts.append("Services to pitch: " + ", ".join(a["services"]))
    if a.get("cold_email"):
        notes_parts.append(f"\n--- Cold email draft ---\n{a['cold_email']}")
    if a.get("whatsapp_message"):
        notes_parts.append(f"\n--- WhatsApp draft ---\n{a['whatsapp_message']}")

    doc = {
        "company": b.get("name"),
        "website": b.get("website"), "industry": payload.niche.replace("_", " "),
        "employees": None, "revenue": None,
        "location": f"{b.get('city')}, {b.get('country')}".strip(", "),
        "owner_id": user["id"], "source": "ai_finder", "priority": "medium",
        "email": b.get("email"), "phone": b.get("phone"), "linkedin": None,
        "notes": "\n".join(notes_parts),
        "tags": ["ai-finder", payload.niche], "stage": "prospect",
        "custom_fields": {"osm_id": b.get("osm_id")},
        "score": 0, "created_at": now, "updated_at": now, "converted_client_id": None,
        "ai_draft_reply": a.get("cold_email"),
    }
    res = await db.leads.insert_one(doc)
    await db.lead_activities.insert_one({
        "lead_id": str(res.inserted_id), "type": "note",
        "content": "Imported from AI Lead Finder with AI pitch analysis",
        "created_by": user["id"], "created_at": now,
    })
    lead = await db.leads.find_one({"_id": res.inserted_id})
    return serialize_doc(lead)
