"""Regression: GET /api/settings/team should return 403 for client-role users (require_staff)"""
import os
import time
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
ADMIN_EMAIL = "info@obrinex.space"
ADMIN_PASSWORD = "Obrinex@2009"


def _admin_session():
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert resp.status_code == 200
    return s


class TestTeamSettingsRBAC:
    def test_admin_can_list_team(self):
        s = _admin_session()
        resp = s.get(f"{BASE_URL}/api/settings/team")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_client_role_forbidden_from_team_list(self):
        import pytest
        admin = _admin_session()
        unique = int(time.time())
        # Clients are created via won-lead automation (no direct POST /api/clients).
        # Create a lead and mark it won to auto-generate a client.
        lead_resp = admin.post(f"{BASE_URL}/api/leads", json={
            "company": f"TEST_RBAC_Client_{unique}",
            "contact_name": "Test Contact",
            "contact_email": f"test_rbac_{unique}@example.com",
            "stage": "new",
            "revenue": 1000,
        })
        if lead_resp.status_code not in (200, 201):
            pytest.skip(f"Could not create lead for RBAC test: {lead_resp.status_code} {lead_resp.text}")
        lead_id = lead_resp.json().get("id")

        won_resp = admin.patch(f"{BASE_URL}/api/leads/{lead_id}/stage", json={"stage": "won"})
        if won_resp.status_code != 200:
            pytest.skip(f"Could not mark lead won: {won_resp.status_code} {won_resp.text}")

        clients_resp = admin.get(f"{BASE_URL}/api/clients")
        client_id = None
        for c in clients_resp.json():
            if c.get("company_name") == f"TEST_RBAC_Client_{unique}":
                client_id = c.get("id")
                break
        if not client_id:
            pytest.skip("Won-automation did not create a matching client (unrelated to this RBAC test)")

        portal_resp = admin.post(f"{BASE_URL}/api/clients/{client_id}/portal-user", json={
            "email": f"test_portal_rbac_{unique}@example.com",
            "name": "Test Portal User",
        })
        if portal_resp.status_code not in (200, 201):
            pytest.skip(f"Could not create portal access: {portal_resp.status_code} {portal_resp.text}")
        portal_data = portal_resp.json()
        portal_email = portal_data.get("email")
        portal_password = portal_data.get("temp_password") or portal_data.get("password")

        if not portal_email or not portal_password:
            import pytest
            pytest.skip("Portal creation response missing email/temp_password")

        client_session = requests.Session()
        login_resp = client_session.post(f"{BASE_URL}/api/auth/login", json={"email": portal_email, "password": portal_password})
        assert login_resp.status_code == 200
        assert login_resp.json()["role"] == "client"

        team_resp = client_session.get(f"{BASE_URL}/api/settings/team")
        assert team_resp.status_code == 403, f"Expected 403, got {team_resp.status_code}: {team_resp.text}"

        # cleanup
        admin.delete(f"{BASE_URL}/api/clients/{client_id}")
