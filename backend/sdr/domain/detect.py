"""Technology and capability detection from a fetched page.

Pure: takes HTML plus response metadata, returns the `AuditFacts` dict the
signal registry consumes. No network, so every detector is testable against a
fixture.

**What this cannot do, and why that is handled rather than hidden.**
The spec calls for Lighthouse, Core Web Vitals and a headless crawl. Those
need a real browser; Vercel's Python serverless runtime has no Chromium and a
60-second ceiling, so Playwright is not an option on this deployment (see
ADR 0004). Rather than emit a fake Lighthouse score, facts we cannot measure
are simply absent - and `signals.detect()` already treats an absent fact as
"claim nothing", so an unmeasurable gap produces no signal instead of a false
one. That behaviour was designed in Phase 1 precisely for this.

What we *can* measure over plain HTTP is substantial: TLS, mobile viewport,
forms, chat widgets, booking tools, CRM and analytics pixels, WhatsApp links,
click-to-call, structured data, and server response time. Those cover thirteen
of the nineteen signals.
"""

import re

# --- Vendor fingerprints ------------------------------------------------------
#
# Matched against the raw HTML (script srcs, inline config, iframe hosts).
# Ordered dicts: first match wins, so the more specific pattern goes first.

CHAT_VENDORS = {
    "tawk.to": r"embed\.tawk\.to|tawk\.to/",
    "Crisp": r"client\.crisp\.chat",
    "Intercom": r"widget\.intercom\.io|intercomSettings",
    "Drift": r"js\.driftt\.com|drift\.com/",
    "Tidio": r"code\.tidio\.co",
    "Zendesk": r"static\.zdassets\.com|zendesk\.com/embeddable",
    "Freshchat": r"wchat\.freshchat\.com|fw-?cdn\.com",
    "LiveChat": r"cdn\.livechatinc\.com",
    "HubSpot Chat": r"js\.hs-scripts\.com.*conversations|hs-banner",
    "WhatsApp widget": r"whatsapp-widget|wa-widget|joinchat",
    "Chatway": r"cdn\.chatway\.app",
    "Smartsupp": r"smartsuppchat\.com",
}

BOOKING_VENDORS = {
    "Calendly": r"calendly\.com",
    "Cal.com": r"cal\.com/|app\.cal\.com",
    "Acuity": r"acuityscheduling\.com",
    "Setmore": r"setmore\.com",
    "SimplyBook": r"simplybook\.(me|it)",
    "HubSpot Meetings": r"meetings\.hubspot\.com",
    "Booksy": r"booksy\.com",
    "Square Appointments": r"squareup\.com/appointments",
    "Zoho Bookings": r"zohobookings\.",
    "Practo": r"practo\.com/.*book",
}

CRM_VENDORS = {
    "HubSpot": r"js\.hs-scripts\.com|hs-analytics\.net",
    "Salesforce/Pardot": r"pardot\.com|pi\.pardot|salesforce\.com/embedded",
    "Zoho": r"zohopublic\.com|salesiq\.zoho|zoho\.com/crm",
    "ActiveCampaign": r"prism\.app-us1\.com|activehosted\.com",
    "Freshsales": r"freshsales\.io|fwtracks",
    "Keap": r"infusionsoft\.com|keap\.com",
}

ANALYTICS_VENDORS = {
    "Google Analytics 4": r"gtag\('config',\s*'G-|googletagmanager\.com/gtag/js\?id=G-",
    "Universal Analytics": r"google-analytics\.com/analytics\.js|ga\('create'",
    "Google Tag Manager": r"googletagmanager\.com/gtm\.js|GTM-[A-Z0-9]+",
    "Meta Pixel": r"connect\.facebook\.net/.*fbevents\.js|fbq\('init'",
    "Hotjar": r"static\.hotjar\.com",
    "Microsoft Clarity": r"clarity\.ms/tag",
    "Plausible": r"plausible\.io/js",
    "Matomo": r"matomo\.(js|php)|piwik\.",
    "Fathom": r"cdn\.usefathom\.com",
}

MARKETING_AUTOMATION_VENDORS = {
    "Mailchimp": r"chimpstatic\.com|list-manage\.com",
    "Klaviyo": r"static\.klaviyo\.com",
    "Brevo/Sendinblue": r"sibautomation\.com|sendinblue\.com",
    "ConvertKit": r"convertkit\.com",
    "Omnisend": r"omnisnippet1\.com",
}

CMS_VENDORS = {
    "WordPress": r"wp-content|wp-includes|/wp-json",
    "Shopify": r"cdn\.shopify\.com|Shopify\.theme",
    "Wix": r"static\.parastorage\.com|wixstatic\.com",
    "Squarespace": r"squarespace\.com|static1\.squarespace",
    "Webflow": r"webflow\.com|wf-",
    "Framer": r"framerusercontent\.com",
    "Duda": r"dudaone|d\.dudamobile",
    "GoDaddy Builder": r"img1\.wsimg\.com",
}


def _match_vendors(html: str, fingerprints: dict) -> list:
    found = []
    for vendor, pattern in fingerprints.items():
        if re.search(pattern, html, re.IGNORECASE):
            found.append(vendor)
    return found


# --- Structural detection -----------------------------------------------------

_TAG = re.compile(r"(?s)<[^>]+>")
_SCRIPT_STYLE = re.compile(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>")


def strip_html(html: str) -> str:
    cleaned = _SCRIPT_STYLE.sub(" ", html or "")
    cleaned = _TAG.sub(" ", cleaned)
    cleaned = re.sub(r"&(nbsp|amp|lt|gt|quot|#39);", " ", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _has_viewport_meta(html: str) -> bool:
    return bool(re.search(
        r"<meta[^>]+name=[\"']viewport[\"'][^>]*content=[\"'][^\"']*width\s*=",
        html, re.IGNORECASE,
    ))


def _detect_forms(html: str) -> dict:
    forms = re.findall(r"(?is)<form\b.*?</form>", html)
    contact_like = 0
    has_email_input = False
    for form in forms:
        if re.search(r"type=[\"']email[\"']|name=[\"'][^\"']*email", form, re.IGNORECASE):
            has_email_input = True
        if re.search(r"(?i)contact|enquir|inquir|message|quote|book|appoint", form):
            contact_like += 1
    return {
        "form_count": len(forms),
        "contact_form_present": bool(forms) and (contact_like > 0 or has_email_input),
        "has_email_input": has_email_input,
    }


def _seo_basics(html: str) -> dict:
    """A measurable SEO check, not a Lighthouse score.

    Six binary structural checks. Named `seo_score_basic` rather than
    `lighthouse_seo` so nobody later mistakes it for the real audit - it does
    not test crawlability, redirects, or mobile rendering.
    """
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    title = strip_html(title_match.group(1)).strip() if title_match else ""
    meta_description = re.search(
        r"<meta[^>]+name=[\"']description[\"'][^>]*content=[\"']([^\"']{20,})",
        html, re.IGNORECASE,
    )
    h1_count = len(re.findall(r"(?i)<h1\b", html))
    canonical = bool(re.search(r"<link[^>]+rel=[\"']canonical", html, re.IGNORECASE))
    schema_org = bool(re.search(
        r"application/ld\+json|itemtype=[\"']https?://schema\.org", html, re.IGNORECASE
    ))

    images = re.findall(r"(?i)<img\b[^>]*>", html)
    with_alt = [img for img in images if re.search(r"(?i)\balt\s*=", img)]
    alt_ok = (not images) or (len(with_alt) / len(images) >= 0.8)

    checks = {
        "has_title": bool(title) and 10 <= len(title) <= 70,
        "has_meta_description": bool(meta_description),
        "has_single_h1": h1_count == 1,
        "has_canonical": canonical,
        "has_schema_org": schema_org,
        "images_have_alt": alt_ok,
    }
    score = round(100 * sum(checks.values()) / len(checks))
    return {
        "seo_score_basic": score,
        "seo_checks": checks,
        "seo_issues": [name for name, passed in checks.items() if not passed],
        "title": title[:200] or None,
        "schema_org_present": schema_org,
    }


def build_facts(*, html: str, status_code: int, headers: dict, elapsed_ms: int,
                tls: bool, company: dict | None = None) -> dict:
    """Assemble the AuditFacts dict from one fetched page.

    Keys we cannot determine over HTTP are deliberately omitted rather than
    set to False. `signals.detect()` distinguishes the two: absent means
    "unknown, claim nothing", False means "verified absent". Setting them
    False here would manufacture signals for gaps nobody has checked.
    """
    html = html or ""
    text = strip_html(html)
    lowered = html.lower()

    chat = _match_vendors(html, CHAT_VENDORS)
    booking = _match_vendors(html, BOOKING_VENDORS)
    crm = _match_vendors(html, CRM_VENDORS)
    analytics = _match_vendors(html, ANALYTICS_VENDORS)
    automation = _match_vendors(html, MARKETING_AUTOMATION_VENDORS)
    cms = _match_vendors(html, CMS_VENDORS)

    forms = _detect_forms(html)
    seo = _seo_basics(html)

    facts = {
        # Transport
        "ssl_valid": tls and status_code < 400,
        "status_code": status_code,
        "load_time_ms": elapsed_ms,
        "page_bytes": len(html),
        "server": headers.get("server"),

        # Rendering
        "mobile_friendly": _has_viewport_meta(html),

        # Capabilities
        "has_chat_widget": bool(chat),
        "chat_vendor": chat[0] if chat else None,
        "has_booking_system": bool(booking),
        "booking_vendor": booking[0] if booking else None,
        "has_crm_pixel": bool(crm),
        "crm_vendor": crm[0] if crm else None,
        "has_analytics": bool(analytics),
        "analytics_vendors": analytics,
        "has_marketing_automation": bool(automation),

        # Lead capture
        "contact_form_present": forms["contact_form_present"],
        "forms_detected": forms["form_count"],
        "cta_count": len(re.findall(
            r"(?i)(book now|get started|contact us|call now|enquire|request a quote|"
            r"schedule|get a quote|sign up|free consultation)", text
        )),

        # Contact routes
        "whatsapp_link_present": bool(re.search(
            r"wa\.me/|api\.whatsapp\.com/send|whatsapp://", lowered
        )),
        "phone_click_to_call": bool(re.search(r"href=[\"']tel:", lowered)),
        "email_link_present": bool(re.search(r"href=[\"']mailto:", lowered)),

        # Content
        "has_faq_content": bool(re.search(r"(?i)\bfaq\b|frequently asked", text))
                           or "FAQPage" in html,
        "tech_stack": sorted(set(cms + chat + booking + crm + analytics + automation)),
    }
    facts.update(seo)

    # Company-level facts the page cannot tell us, carried through from the
    # stored record so review-based signals can fire.
    if company:
        for key in ("google_review_count", "google_rating", "employee_count"):
            if company.get(key) is not None:
                facts[key] = company[key]

    # Deliberately absent, because this deployment cannot measure them:
    #   lighthouse_performance, lighthouse_seo, core_web_vitals,
    #   contact_form_working (needs a submission),
    #   has_after_hours_cover, measured_response_hours,
    #   has_review_automation, has_booking_reminders,
    #   review_response_rate, blog_days_since_update
    # See the module docstring and ADR 0004.
    return facts


#: What a full browser-based audit would add. Surfaced in the UI so the gap is
#: visible to whoever reads an audit, rather than looking like a clean bill.
UNMEASURED_FACTS = (
    "lighthouse_performance", "lighthouse_seo", "core_web_vitals",
    "contact_form_working", "has_after_hours_cover", "measured_response_hours",
    "has_review_automation", "has_booking_reminders", "review_response_rate",
    "blog_days_since_update",
)
