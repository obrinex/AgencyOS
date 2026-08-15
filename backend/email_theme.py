"""The email design system: tokens, components, and the document shell.

## Why this module exists

`BRAND_DEFAULTS` has been in `email_service.py` for a long time, and Settings →
Branding has been writing to it for just as long. It changed almost nothing.
Every template body hardcoded its own colours — seventy-nine hex literals across
fourteen templates — so an admin could set the text colour to anything they
liked and the paragraphs stayed `#B5B5BC`. The brand controlled the frame; the
frame was the only part that was ever branded.

So the rule here is absolute: **no template writes a colour, a size or a font.**
It asks for a component, and the component reads the brand. If a value is not a
token, it cannot be customised, and a thing that cannot be customised in a
"customisable" system is a bug with good intentions.

## Why it looks the way it does

Email is not the web. There is no cascade worth trusting, no flexbox in Outlook,
no external stylesheet in Gmail, and no webfont in most clients. So:

- **Tables, inline styles.** Every layout is a `role="presentation"` table with
  styles on the element. This is not old-fashioned; it is the only thing that
  renders the same in Outlook 2016 and iOS Mail.
- **A real document.** The old wrapper returned a bare `<div>`. Clients that
  receive a fragment supply their own `<body>` defaults, which is why the same
  email looked tighter in Apple Mail than in Gmail. There is now a full
  document, with the Outlook DPI fix and the Apple reformatting opt-out.
- **A preheader.** The grey line an inbox shows next to the subject was
  previously the first words of the body — usually "Hi {name}," repeated down
  the list. Every template now states its own.
- **Bulletproof buttons.** A padded `<a>` collapses to a text link in Outlook.
  Buttons are tables with a VML fallback, so they are buttons everywhere.
- **One type scale.** 26 / 17 / 15 / 13 / 11 with fixed line heights, and one
  horizontal gutter used by every row. The old templates mixed 20/14/13/12 and
  three different paddings, which is what made them read as assembled rather
  than designed.
"""

from html import escape

#: The design tokens. Everything below is overridable from Settings → Branding;
#: `email_service.get_brand()` merges saved values over these.
#:
#: Grouped by what they do rather than alphabetically, because someone changing
#: "the colour of the buttons" should not have to know it is called `accent`.
TOKENS = {
    # ── Identity ──────────────────────────────────────────────────────────
    "logo_url": "https://obrinex.space/brand/monogram-paper.png",
    "show_logo": True,
    "brand_name": "OBRINEX",
    "tagline": "AI Automation Agency",

    # ── Type ──────────────────────────────────────────────────────────────
    #: Webfonts do not load in Outlook, Gmail's web client, or most corporate
    #: clients, so a stack is a promise about the *fallbacks*, not the first
    #: name. Jost first for the clients that have it; then the geometric
    #: grotesques that ship with Windows and macOS and actually resemble it.
    "font": "'Jost','Futura','Century Gothic','Segoe UI',Roboto,Helvetica,Arial,sans-serif",
    #: Headings can differ. Same stack by default — one voice unless asked.
    "heading_font": "",

    # ── Colour ────────────────────────────────────────────────────────────
    "bg_color": "#000000",
    "card_color": "#0B0B0C",
    "text_color": "#F4F4F5",
    #: Body copy. Distinct from `text_color`, which is headings: running text a
    #: shade under the heading is most of what makes an email look typeset.
    "body_color": "#C8C8CE",
    "muted_color": "#8A8A90",
    "border_color": "#1E1E20",
    "box_color": "#141416",
    "box_border_color": "#232326",
    "accent_color": "#EDE7D9",
    "accent_text_color": "#0B0B0C",
    "link_color": "#EDE7D9",
    "success_color": "#3FBF8F",
    "danger_color": "#E5484D",

    # ── Shape ─────────────────────────────────────────────────────────────
    "width": "600",
    "radius": "14",
    "button_radius": "10",

    # ── Footer ────────────────────────────────────────────────────────────
    "footer_text": "Obrinex — Systems that ship",
    "footer_note": "Please check your spam folder if this email isn't in your inbox.",
    "footer_address": "",
    "footer_link_text": "",
    "footer_link_url": "",
}

#: Which tokens are booleans; everything else is a string. Used by the merge in
#: `get_brand()` and by the Settings validator.
BOOL_KEYS = ("show_logo",)
STRING_KEYS = tuple(k for k in TOKENS if k not in BOOL_KEYS)

#: The horizontal gutter, used by every row so nothing is ever off by 4px.
GUTTER = 40

#: One type scale. Size, line-height.
SCALE = {
    "display": (26, 34),
    "lead": (17, 27),
    "body": (15, 25),
    "small": (13, 21),
    "micro": (11, 17),
}


def _font(b: dict, heading: bool = False) -> str:
    if heading and (b.get("heading_font") or "").strip():
        return b["heading_font"]
    return b.get("font") or TOKENS["font"]


def _px(value, fallback: int) -> int:
    try:
        return int(str(value).strip().replace("px", ""))
    except (TypeError, ValueError):
        return fallback


# ── Text ──────────────────────────────────────────────────────────────────────

def heading(text: str, b: dict) -> str:
    """The one big line. At most one per email — two headings is two emails."""
    size, lh = SCALE["display"]
    return (
        f'<tr><td class="obx-pad" style="padding:0 {GUTTER}px 14px;font-family:{_font(b, True)};'
        f'font-size:{size}px;line-height:{lh}px;font-weight:700;letter-spacing:-0.3px;'
        f'color:{b["text_color"]};">{text}</td></tr>'
    )


def lead(text: str, b: dict) -> str:
    """The sentence under the heading that says what this email is for."""
    size, lh = SCALE["lead"]
    return (
        f'<tr><td class="obx-pad" style="padding:0 {GUTTER}px 22px;font-family:{_font(b)};'
        f'font-size:{size}px;line-height:{lh}px;color:{b["body_color"]};">{text}</td></tr>'
    )


def paragraph(text: str, b: dict, space: int = 16) -> str:
    size, lh = SCALE["body"]
    return (
        f'<tr><td class="obx-pad" style="padding:0 {GUTTER}px {space}px;font-family:{_font(b)};'
        f'font-size:{size}px;line-height:{lh}px;color:{b["body_color"]};">{text}</td></tr>'
    )


def note(text: str, b: dict, space: int = 0) -> str:
    """Small print. The line that manages an expectation rather than making a point."""
    size, lh = SCALE["small"]
    return (
        f'<tr><td class="obx-pad" style="padding:14px {GUTTER}px {space}px;font-family:{_font(b)};'
        f'font-size:{size}px;line-height:{lh}px;color:{b["muted_color"]};">{text}</td></tr>'
    )


def eyebrow(text: str, b: dict) -> str:
    """A small tracked label above a heading — what kind of email this is."""
    return (
        f'<tr><td class="obx-pad" style="padding:0 {GUTTER}px 10px;font-family:{_font(b)};font-size:11px;'
        f'line-height:16px;letter-spacing:2.5px;text-transform:uppercase;'
        f'color:{b["muted_color"]};">{escape(text)}</td></tr>'
    )


def bullets(items, b: dict, space: int = 16) -> str:
    if not items:
        return ""
    size, lh = SCALE["body"]
    rows = "".join(
        f'<tr>'
        f'<td valign="top" width="14" style="font-family:{_font(b)};font-size:{size}px;'
        f'line-height:{lh}px;color:{b["accent_color"]};">&bull;</td>'
        f'<td style="font-family:{_font(b)};font-size:{size}px;line-height:{lh}px;'
        f'color:{b["body_color"]};padding-bottom:6px;">{i}</td></tr>'
        for i in items
    )
    return (
        f'<tr><td class="obx-pad" style="padding:0 {GUTTER}px {space}px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        f'{rows}</table></td></tr>'
    )


# ── Structure ─────────────────────────────────────────────────────────────────

def panel(rows, b: dict, space: int = 22) -> str:
    """The boxed facts: amount due, when, where, credentials.

    `rows` is a list of `(label, value)`. Labels sit in their own column so the
    values line up down the email — the old version was `Label: value<br/>`,
    which ragged as soon as one label was longer than another.
    """
    size, _ = SCALE["small"]
    body_size, _ = SCALE["body"]
    cells = ""
    for i, (label, value) in enumerate(rows):
        pad_top = 0 if i == 0 else 10
        cells += (
            f'<tr>'
            f'<td valign="top" style="padding-top:{pad_top}px;font-family:{_font(b)};'
            f'font-size:{size}px;line-height:20px;color:{b["muted_color"]};'
            f'white-space:nowrap;padding-right:18px;">{label}</td>'
            f'<td valign="top" align="right" style="padding-top:{pad_top}px;'
            f'font-family:{_font(b)};font-size:{body_size}px;line-height:20px;'
            f'font-weight:600;color:{b["text_color"]};">{value}</td>'
            f'</tr>'
        )
    radius = _px(b.get("box_radius") or b.get("radius"), 14) - 2
    return (
        f'<tr><td class="obx-pad" style="padding:0 {GUTTER}px {space}px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:{b["box_color"]};border:1px solid {b["box_border_color"]};'
        f'border-radius:{radius}px;">'
        f'<tr><td style="padding:18px 20px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        f'{cells}</table>'
        f'</td></tr></table></td></tr>'
    )


def divider(b: dict, space: int = 24) -> str:
    return (
        f'<tr><td class="obx-pad" style="padding:{space}px {GUTTER}px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        f'<tr><td style="height:1px;background:{b["border_color"]};line-height:1px;'
        f'font-size:0;">&nbsp;</td></tr></table></td></tr>'
    )


def spacer(height: int) -> str:
    return (f'<tr><td style="height:{height}px;line-height:{height}px;font-size:0;">'
            f'&nbsp;</td></tr>')


def button(label: str, url: str, b: dict, variant: str = "primary", space: int = 8) -> str:
    """A button that is still a button in Outlook.

    A padded `<a>` — which is what every template used — loses its background in
    Outlook's Word renderer and arrives as a bare blue link. This is a table
    with a VML rectangle behind it for `mso`, which is the only construction
    that survives everywhere.
    """
    radius = _px(b.get("button_radius"), 10)
    if variant == "primary":
        bg, fg, border = b["accent_color"], b["accent_text_color"], b["accent_color"]
    else:
        bg, fg, border = b["card_color"], b["text_color"], b["border_color"]

    return f'''<tr><td class="obx-pad" style="padding:0 {GUTTER}px {space}px;">
<table role="presentation" class="obx-btn-wrap" cellpadding="0" cellspacing="0" border="0"><tr><td>
<!--[if mso]>
<v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word"
 href="{url}" style="height:46px;v-text-anchor:middle;width:240px;" arcsize="{int(radius / 46 * 100)}%"
 strokecolor="{border}" fillcolor="{bg}">
<w:anchorlock/><center style="color:{fg};font-family:{_font(b)};font-size:15px;font-weight:600;">{label}</center>
</v:roundrect>
<![endif]-->
<a href="{url}" class="obx-btn" style="background:{bg};border:1px solid {border};border-radius:{radius}px;
color:{fg};display:inline-block;font-family:{_font(b)};font-size:15px;font-weight:600;
line-height:46px;text-align:center;text-decoration:none;width:240px;
-webkit-text-size-adjust:none;mso-hide:all;">{label}</a>
</td></tr></table></td></tr>'''


def link(text: str, url: str, b: dict) -> str:
    return (f'<a href="{url}" style="color:{b["link_color"]};text-decoration:underline;">'
            f'{text}</a>')


# ── The document ──────────────────────────────────────────────────────────────

def _header(b: dict) -> str:
    if b.get("show_logo") and b.get("logo_url"):
        mark = (f'<img src="{b["logo_url"]}" alt="{escape(b["brand_name"])}" height="42" '
                f'style="height:42px;width:auto;max-width:200px;display:block;border:0;'
                f'outline:none;text-decoration:none;" />')
    else:
        mark = (f'<div style="font-family:{_font(b, True)};font-size:22px;font-weight:700;'
                f'letter-spacing:5px;color:{b["text_color"]};">{escape(b["brand_name"])}</div>')
    tagline = (
        f'<div style="font-family:{_font(b)};font-size:11px;letter-spacing:2.5px;'
        f'text-transform:uppercase;color:{b["muted_color"]};padding-top:9px;">'
        f'{escape(b["tagline"])}</div>'
    ) if b.get("tagline") else ""
    return (f'<tr><td class="obx-pad" style="padding:38px {GUTTER}px 26px;">{mark}{tagline}</td></tr>'
            f'<tr><td class="obx-pad" style="padding:0 {GUTTER}px 30px;">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
            f'<tr><td style="height:2px;background:{b["accent_color"]};line-height:2px;'
            f'font-size:0;border-radius:2px;">&nbsp;</td></tr></table></td></tr>')


def _footer(b: dict) -> str:
    extra = ""
    if b.get("footer_link_text") and b.get("footer_link_url"):
        extra = (f'<div style="padding-top:10px;">'
                 f'<a href="{b["footer_link_url"]}" style="color:{b["muted_color"]};'
                 f'font-size:11px;text-decoration:underline;">'
                 f'{escape(b["footer_link_text"])}</a></div>')
    address = (f'<div style="font-size:11px;line-height:17px;color:{b["muted_color"]};'
               f'opacity:0.65;padding-top:10px;">{escape(b["footer_address"])}</div>'
               ) if b.get("footer_address") else ""
    return f'''<tr><td class="obx-pad" style="padding:0 {GUTTER}px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td style="height:1px;background:{b['border_color']};line-height:1px;font-size:0;">&nbsp;</td></tr>
</table></td></tr>
<tr><td class="obx-pad" style="padding:24px {GUTTER}px 36px;font-family:{_font(b)};">
  <div style="font-size:12px;line-height:18px;letter-spacing:0.4px;color:{b['muted_color']};">{escape(b['footer_text'])}</div>
  <div style="font-size:11px;line-height:17px;color:{b['muted_color']};opacity:0.65;padding-top:8px;">{escape(b['footer_note'])}</div>
  {address}{extra}
</td></tr>'''


def document(inner: str, b: dict, preheader: str = "") -> str:
    """Wrap composed rows in a full, client-safe HTML email."""
    width = _px(b.get("width"), 600)
    radius = _px(b.get("radius"), 14)

    # The inbox preview line. Padded with zero-width joiners so the client stops
    # after our sentence instead of running on into the body copy.
    pre = (
        f'<div style="display:none;font-size:1px;color:{b["bg_color"]};line-height:1px;'
        f'max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;">'
        f'{escape(preheader)}{"&#8204;&nbsp;" * 60}</div>'
    ) if preheader else ""

    return f'''<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta http-equiv="X-UA-Compatible" content="IE=edge" />
<meta name="x-apple-disable-message-reformatting" />
<meta name="color-scheme" content="dark light" />
<meta name="supported-color-schemes" content="dark light" />
<title>{escape(b.get("brand_name") or "")}</title>
<!--[if mso]>
<noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript>
<![endif]-->
<style>
  /* Client resets. Kept to the handful that actually earn their place. */
  body,table,td,a {{ -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; }}
  table,td {{ mso-table-lspace:0pt; mso-table-rspace:0pt; }}
  img {{ -ms-interpolation-mode:bicubic; border:0; outline:none; text-decoration:none; }}
  a {{ color:{b['link_color']}; }}
  /* Gmail and Outlook.com underline and recolour anything that looks like a
     date, an address or a phone number. This turns that off for our own text. */
  u + #body a, #MessageViewBody a {{ color:inherit; text-decoration:none; }}
  @media only screen and (max-width:620px) {{
    .obx-card {{ width:100% !important; border-radius:0 !important; border-left:0 !important; border-right:0 !important; }}
    .obx-pad {{ padding-left:22px !important; padding-right:22px !important; }}
    .obx-btn-wrap {{ width:100% !important; }}
    .obx-btn {{ width:100% !important; }}
  }}
</style>
</head>
<body id="body" style="margin:0;padding:0;background:{b['bg_color']};">
{pre}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{b['bg_color']};">
  <tr><td align="center" style="padding:36px 12px;">
    <table role="presentation" class="obx-card" width="{width}" cellpadding="0" cellspacing="0" border="0"
           style="width:{width}px;max-width:{width}px;background:{b['card_color']};border:1px solid {b['border_color']};border-radius:{radius}px;">
      {_header(b)}
      {inner}
      {spacer(10)}
      {_footer(b)}
    </table>
  </td></tr>
</table>
</body>
</html>'''
