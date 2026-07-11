"""
Phase 4 backend tests: Stripe currency fix, client cascade delete + portal-user revoke,
CSV lead import, PDF export (invoice + finance report), Google Calendar meetings integration.
"""
import io
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "info@obrinex.space"
ADMIN_PASSWORD = "Obrinex@2009"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    resp = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return s


@pytest.fixture(scope="module")
def test_client_id(admin_session):
    """Create a client via lead->won flow for cascade/portal tests."""
    lead_resp = admin_session.post(f"{API}/leads", json={"company": "TEST_CascadeCo", "revenue": 5000})
    assert lead_resp.status_code == 200
    lead_id = lead_resp.json()["id"]
    stage_resp = admin_session.patch(f"{API}/leads/{lead_id}/stage", json={"stage": "won"})
    assert stage_resp.status_code == 200
    automation = stage_resp.json().get("automation")
    assert automation is not None
    client_id = automation.get("client_id") or automation.get("client", {}).get("id")
    if not client_id:
        clients = admin_session.get(f"{API}/clients").json()
        match = [c for c in clients if c.get("company_name") == "TEST_CascadeCo"]
        assert match, f"Could not locate created client. automation={automation}"
        client_id = match[0]["id"]
    yield client_id
    admin_session.delete(f"{API}/clients/{client_id}")


class TestStripeCurrencyFix:
    def test_invoice_checkout_inr_default(self, admin_session, test_client_id):
        inv = admin_session.post(f"{API}/invoices", json={
            "client_id": test_client_id,
            "line_items": [{"description": "Test service", "quantity": 1, "price": 1000}],
        })
        assert inv.status_code == 200
        invoice = inv.json()
        assert invoice["currency"] == "INR"
        checkout = admin_session.post(f"{API}/invoices/{invoice['id']}/checkout")
        assert checkout.status_code == 200
        data = checkout.json()
        assert "url" in data and "session_id" in data
        admin_session.delete(f"{API}/invoices/{invoice['id']}")

    def test_invoice_checkout_usd(self, admin_session, test_client_id):
        inv = admin_session.post(f"{API}/invoices", json={
            "client_id": test_client_id,
            "line_items": [{"description": "Test service USD", "quantity": 1, "price": 100}],
            "currency": "USD",
            "conversion_rate": 83,
        })
        assert inv.status_code == 200
        invoice = inv.json()
        assert invoice["currency"] == "USD"
        checkout = admin_session.post(f"{API}/invoices/{invoice['id']}/checkout")
        assert checkout.status_code == 200
        admin_session.delete(f"{API}/invoices/{invoice['id']}")


class TestClientCascadeDelete:
    def test_create_and_revoke_portal_user(self, admin_session, test_client_id):
        create_resp = admin_session.post(f"{API}/clients/{test_client_id}/portal-user", json={
            "email": "test_cascadeportal@example.com", "name": "Portal Tester",
        })
        assert create_resp.status_code == 200
        creds = create_resp.json()
        assert creds["email"] == "test_cascadeportal@example.com"
        assert "temp_password" in creds

        client_doc = admin_session.get(f"{API}/clients/{test_client_id}").json()
        assert client_doc.get("portal_user_id") is not None

        revoke_resp = admin_session.delete(f"{API}/clients/{test_client_id}/portal-user")
        assert revoke_resp.status_code == 200

        client_doc2 = admin_session.get(f"{API}/clients/{test_client_id}").json()
        assert client_doc2.get("portal_user_id") is None

        login_attempt = requests.post(f"{API}/auth/login", json={
            "email": "test_cascadeportal@example.com", "password": creds["temp_password"],
        })
        assert login_attempt.status_code == 401

    def test_delete_client_cascades_portal_user(self, admin_session):
        lead_resp = admin_session.post(f"{API}/leads", json={"company": "TEST_CascadeCo2", "revenue": 2000})
        lead_id = lead_resp.json()["id"]
        stage_resp = admin_session.patch(f"{API}/leads/{lead_id}/stage", json={"stage": "won"})
        automation = stage_resp.json().get("automation")
        clients = admin_session.get(f"{API}/clients").json()
        match = [c for c in clients if c.get("company_name") == "TEST_CascadeCo2"]
        assert match
        client_id = match[0]["id"]

        create_resp = admin_session.post(f"{API}/clients/{client_id}/portal-user", json={
            "email": "test_cascadeportal2@example.com", "name": "Portal Tester 2",
        })
        assert create_resp.status_code == 200
        creds = create_resp.json()

        del_resp = admin_session.delete(f"{API}/clients/{client_id}")
        assert del_resp.status_code == 200

        get_resp = admin_session.get(f"{API}/clients/{client_id}")
        assert get_resp.status_code == 404

        login_attempt = requests.post(f"{API}/auth/login", json={
            "email": "test_cascadeportal2@example.com", "password": creds["temp_password"],
        })
        assert login_attempt.status_code == 401


class TestCsvImport:
    def test_import_csv_success(self, admin_session):
        csv_content = (
            "company,email,revenue,priority\n"
            "TEST_CsvCo1,csvco1@example.com,10000,high\n"
            "TEST_CsvCo2,csvco2@example.com,20000,medium\n"
        )
        files = {"file": ("leads.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        resp = admin_session.post(f"{API}/leads/import-csv", files=files)
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 2
        assert data["errors"] == []

        leads = admin_session.get(f"{API}/leads", params={"search": "TEST_CsvCo"}).json()
        companies = {l["company"] for l in leads}
        assert "TEST_CsvCo1" in companies
        assert "TEST_CsvCo2" in companies

        for l in leads:
            admin_session.delete(f"{API}/leads/{l['id']}")

    def test_import_csv_missing_company_column(self, admin_session):
        csv_content = "name,email\nAcme,acme@example.com\n"
        files = {"file": ("bad.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        resp = admin_session.post(f"{API}/leads/import-csv", files=files)
        assert resp.status_code == 400
        assert "company" in resp.json()["detail"].lower()


class TestPdfExport:
    def test_invoice_pdf_download(self, admin_session, test_client_id):
        inv = admin_session.post(f"{API}/invoices", json={
            "client_id": test_client_id,
            "line_items": [{"description": "PDF test", "quantity": 1, "price": 500}],
        }).json()
        resp = admin_session.get(f"{API}/invoices/{inv['id']}/pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert len(resp.content) > 100
        admin_session.delete(f"{API}/invoices/{inv['id']}")

    def test_finance_report_pdf_download(self, admin_session):
        resp = admin_session.get(f"{API}/finance/report/pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert len(resp.content) > 100


class TestMeetingsGoogleCalendar:
    def test_google_status(self, admin_session):
        resp = admin_session.get(f"{API}/meetings/google/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is True
        assert data["connected"] is False
        assert data["email"] is None

    def test_google_connect_returns_valid_url(self, admin_session):
        resp = admin_session.get(f"{API}/meetings/google/connect")
        assert resp.status_code == 200
        data = resp.json()
        assert "authorization_url" in data
        url = data["authorization_url"]
        assert "accounts.google.com" in url
        assert os.environ.get("GOOGLE_CLIENT_ID_PLACEHOLDER", "") or "client_id=" in url
        assert "redirect_uri=" in url
        assert "%2Fapi%2Fmeetings%2Fgoogle%2Fcallback" in url or "/api/meetings/google/callback" in url

    def test_meeting_crud_without_google(self, admin_session):
        create_resp = admin_session.post(f"{API}/meetings", json={
            "title": "TEST_Meeting1",
            "start_time": "2026-03-01T10:00:00+00:00",
            "location": "Zoom",
            "notes": "Discuss roadmap",
        })
        assert create_resp.status_code == 200
        meeting = create_resp.json()
        assert meeting["title"] == "TEST_Meeting1"
        assert meeting["google_event_id"] is None

        list_resp = admin_session.get(f"{API}/meetings")
        assert any(m["id"] == meeting["id"] for m in list_resp.json())

        del_resp = admin_session.delete(f"{API}/meetings/{meeting['id']}")
        assert del_resp.status_code == 200

        list_resp2 = admin_session.get(f"{API}/meetings")
        assert not any(m["id"] == meeting["id"] for m in list_resp2.json())
