"""Reading a contact email off a company's own website.

This exists so a discovered lead is reachable without anyone uploading a
spreadsheet: OpenStreetMap almost never carries an email address, and a lead
with no address cannot be qualified, cannot be emailed, and correctly scores
near zero.

The test that matters most is
`test_a_web_designers_address_in_the_footer_is_not_the_lead`. Small business
sites routinely carry the address of whoever built them, a platform's support
desk, or a stock photo licence contact. Emailing one of those is worse than
having no address at all - it is cold outreach to an uninvolved third party,
and it is the kind of mistake that produces a spam complaint against a domain
that took three weeks to warm up.
"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "sdr_test")

from sdr.domain import contact_extract  # noqa: E402


def test_a_mailto_link_on_the_companys_own_domain_is_taken():
    html = """
      <html><body>
        <a href="mailto:info@kumardental.in">Email us</a>
      </body></html>
    """
    assert contact_extract.best_email(
        html, company_domain="kumardental.in") == "info@kumardental.in"


def test_www_does_not_defeat_the_match():
    html = '<a href="mailto:hello@kumardental.in">hi</a>'
    assert contact_extract.best_email(
        html, company_domain="www.kumardental.in") == "hello@kumardental.in"


def test_a_web_designers_address_in_the_footer_is_not_the_lead():
    """The expensive mistake. Every address here is real and none of them
    belong to the prospect."""
    html = """
      <html><body>
        <p>Call us on 0341 000000</p>
        <footer>
          Site by <a href="mailto:studio@brightpixel.co">Bright Pixel</a>.
          Powered by <a href="mailto:support@squarespace.com">Squarespace</a>.
          Photos licensed from contact@example.com
        </footer>
      </body></html>
    """
    assert contact_extract.best_email(html, company_domain="kumardental.in") is None


def test_a_general_inbox_is_preferred_over_a_personal_one():
    """An enquiries inbox is monitored; a named partner's address may not be,
    and is more likely to read as intrusive."""
    html = """
      <a href="mailto:dr.priya.kumar@kumardental.in">Dr Kumar</a>
      <a href="mailto:info@kumardental.in">General enquiries</a>
    """
    assert contact_extract.best_email(
        html, company_domain="kumardental.in") == "info@kumardental.in"


def test_a_subdomain_of_the_company_counts_as_the_company():
    html = '<a href="mailto:bookings@clinic.kumardental.in">Book</a>'
    assert contact_extract.best_email(
        html, company_domain="kumardental.in") == "bookings@clinic.kumardental.in"


def test_noreply_and_platform_addresses_are_never_returned():
    html = """
      <a href="mailto:noreply@kumardental.in">x</a>
      <a href="mailto:postmaster@kumardental.in">y</a>
      <a href="mailto:abuse@kumardental.in">z</a>
    """
    assert contact_extract.best_email(html, company_domain="kumardental.in") is None


def test_asset_filenames_that_look_like_addresses_are_ignored():
    html = '<img src="/i/logo@2x.png"> <link href="/f/icons@1.0.woff2">'
    assert contact_extract.extract_emails(html, company_domain="kumardental.in") == []


def test_nothing_is_returned_when_we_do_not_know_the_company_domain():
    """Without a domain there is no way to tell the prospect's address from
    anyone else's, so it refuses rather than guesses."""
    html = '<a href="mailto:info@kumardental.in">Email</a>'
    assert contact_extract.best_email(html, company_domain=None) is None


def test_an_address_in_plain_text_is_found_too():
    """Not every site uses a mailto link."""
    html = "<p>Write to us at reception@kumardental.in for appointments.</p>"
    assert contact_extract.best_email(
        html, company_domain="kumardental.in") == "reception@kumardental.in"


def test_trailing_punctuation_is_not_part_of_the_address():
    html = "<p>Email info@kumardental.in.</p>"
    assert contact_extract.best_email(
        html, company_domain="kumardental.in") == "info@kumardental.in"


def test_an_empty_or_broken_page_returns_nothing_rather_than_raising():
    for page in ("", None, "<html></html>", "@@@", "a@b"):
        assert contact_extract.best_email(page, company_domain="kumardental.in") is None


def test_third_party_addresses_are_still_listed_for_a_human_to_see():
    """extract_emails is the wider net - it may show a person options. Only
    best_email is allowed to feed automated outreach."""
    html = '<a href="mailto:studio@brightpixel.co">designer</a>'
    listed = contact_extract.extract_emails(html, company_domain="kumardental.in")
    assert "studio@brightpixel.co" in listed
    assert contact_extract.best_email(html, company_domain="kumardental.in") is None
