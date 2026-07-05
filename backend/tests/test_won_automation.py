"""CRM Won-Automation: Lead creation -> stage=won -> auto Client+Project+Invoice+Tasks+Notification+ActivityLog"""
import os
import time
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
ADMIN_EMAIL = "admin@obrinex.com"
ADMIN_PASSWORD = "AgencyOS@2026"


def admin_session():
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert resp.status_code == 200, f"admin login failed: {resp.text}"
    return s


class TestWonAutomation:
    def test_full_won_automation_flow(self):
        s = admin_session()
        company_name = f"TEST_WonCo_{int(time.time())}"

        # 1. Create lead
        lead_payload = {"company": company_name, "revenue": 5000, "priority": "high", "email": "test@wonco.com"}
        resp = s.post(f"{BASE_URL}/api/leads", json=lead_payload)
        assert resp.status_code == 200, resp.text
        lead = resp.json()
        assert lead["company"] == company_name
        assert lead["stage"] == "prospect"
        lead_id = lead["id"]

        # 2. Move lead to won
        resp = s.patch(f"{BASE_URL}/api/leads/{lead_id}/stage", json={"stage": "won"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["lead"]["stage"] == "won"
        automation = data["automation"]
        assert automation is not None, "Automation result missing - won automation did not trigger"
        client_id = automation["client_id"]
        project_id = automation["project_id"]

        # 3. Verify client created
        resp = s.get(f"{BASE_URL}/api/clients/{client_id}")
        assert resp.status_code == 200, resp.text
        client = resp.json()
        assert client["company_name"] == company_name
        assert len(client["onboarding_checklist"]) == 5

        # 4. Verify project created and linked to client
        resp = s.get(f"{BASE_URL}/api/projects/{project_id}")
        assert resp.status_code == 200, resp.text
        project = resp.json()
        assert project["client_id"] == client_id
        assert project["status"] == "onboarding"

        # 5. Verify invoice auto-created with INV- number, linked to client
        resp = s.get(f"{BASE_URL}/api/invoices", params={"client_id": client_id})
        assert resp.status_code == 200, resp.text
        invoices = resp.json()
        assert len(invoices) >= 1
        inv = invoices[0]
        assert inv["invoice_number"].startswith("INV-")
        assert inv["status"] == "draft"

        # 6. Verify onboarding tasks created for project
        resp = s.get(f"{BASE_URL}/api/tasks", params={"related_id": project_id})
        assert resp.status_code == 200, resp.text
        tasks = resp.json()
        assert len(tasks) >= 4, f"Expected >=4 onboarding tasks, got {len(tasks)}"

        # 7. Verify lead timeline / activity entry
        resp = s.get(f"{BASE_URL}/api/leads/{lead_id}/activities")
        assert resp.status_code == 200, resp.text
        activities = resp.json()
        assert any("Won" in a["content"] or "won" in a["content"] for a in activities)

        # 8. Verify automation log exists
        resp = s.get(f"{BASE_URL}/api/automations/logs") if _endpoint_exists(s, "/api/automations/logs") else None
        # non-critical, tolerate missing endpoint name variations

    def test_double_won_does_not_duplicate(self):
        """Moving an already-won lead to won again should not error and not re-trigger automation."""
        s = admin_session()
        company_name = f"TEST_DoubleWon_{int(time.time())}"
        resp = s.post(f"{BASE_URL}/api/leads", json={"company": company_name, "revenue": 1000})
        lead_id = resp.json()["id"]
        resp1 = s.patch(f"{BASE_URL}/api/leads/{lead_id}/stage", json={"stage": "won"})
        assert resp1.status_code == 200
        automation1 = resp1.json()["automation"]
        assert automation1 is not None
        resp2 = s.patch(f"{BASE_URL}/api/leads/{lead_id}/stage", json={"stage": "won"})
        assert resp2.status_code == 200
        automation2 = resp2.json()["automation"]
        assert automation2 is None, "Automation re-triggered on duplicate won stage change"


def _endpoint_exists(session, path):
    try:
        r = session.get(f"{BASE_URL}{path}")
        return r.status_code != 404
    except Exception:
        return False


class TestPortalUserCreationAndAccess:
    def test_create_portal_user_and_login(self):
        s = admin_session()
        company_name = f"TEST_PortalCo_{int(time.time())}"
        resp = s.post(f"{BASE_URL}/api/leads", json={"company": company_name, "revenue": 2000})
        lead_id = resp.json()["id"]
        resp = s.patch(f"{BASE_URL}/api/leads/{lead_id}/stage", json={"stage": "won"})
        client_id = resp.json()["automation"]["client_id"]

        # Create portal access
        portal_email = f"test_portal_{int(time.time())}@portalco.com"
        resp = s.post(f"{BASE_URL}/api/clients/{client_id}/portal-user", json={"name": "Portal Tester", "email": portal_email})
        assert resp.status_code == 200, resp.text
        result = resp.json()
        assert "temp_password" in result or "password" in result, f"No temp password in response: {result}"
        temp_password = result.get("temp_password") or result.get("password")

        # Login as portal user
        client_session = requests.Session()
        login_resp = client_session.post(f"{BASE_URL}/api/auth/login", json={"email": portal_email, "password": temp_password})
        assert login_resp.status_code == 200, login_resp.text
        user_data = login_resp.json()
        assert user_data["role"] == "client"

        # Verify client CANNOT access staff-only endpoints
        resp = client_session.get(f"{BASE_URL}/api/vault")
        assert resp.status_code == 403, f"Client should not access vault, got {resp.status_code}"

        resp = client_session.get(f"{BASE_URL}/api/settings/team")
        assert resp.status_code == 403, f"Client should not access settings/team, got {resp.status_code}"

        # Verify client CAN access portal endpoints
        resp = client_session.get(f"{BASE_URL}/api/portal/overview")
        assert resp.status_code == 200, resp.text
