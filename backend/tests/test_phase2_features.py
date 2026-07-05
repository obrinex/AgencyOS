"""
Phase 2 feature tests: Resend email integration (portal welcome, team invite,
invoice send, forgot-password), Contract e-signature (staff + client portal),
Proposal e-signature via public share-token link (no auth required).
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
ADMIN_EMAIL = "admin@obrinex.com"
ADMIN_PASSWORD = "AgencyOS@2026"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} {resp.text}")
    return s


def _create_client_via_won_lead(session, tag):
    """Clients have no direct create endpoint - they're auto-created when a lead is marked 'won'."""
    company_name = f"TEST_Phase2_{tag}_{int(time.time()*1000)}"
    lead_resp = session.post(f"{BASE_URL}/api/leads", json={"company": company_name, "revenue": 1000})
    assert lead_resp.status_code == 200, lead_resp.text
    lead_id = lead_resp.json()["id"]
    won_resp = session.patch(f"{BASE_URL}/api/leads/{lead_id}/stage", json={"stage": "won"})
    assert won_resp.status_code == 200, won_resp.text
    client_id = won_resp.json()["automation"]["client_id"]
    client = session.get(f"{BASE_URL}/api/clients/{client_id}").json()
    return client


@pytest.fixture(scope="module")
def test_client(admin_session):
    """Auto-create a TEST_ client via the won-lead automation, to use across this module."""
    return _create_client_via_won_lead(admin_session, "main")


class TestEmailIntegration:
    def test_create_portal_access_sends_welcome_email(self, admin_session, test_client):
        email = f"test_portal_{int(time.time())}@example.com"
        resp = admin_session.post(f"{BASE_URL}/api/clients/{test_client['id']}/portal-user", json={
            "email": email, "name": "Portal Test User"
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "temp_password" in data and len(data["temp_password"]) > 0
        assert data["email"] == email

    def test_invite_team_member_sends_invite_email(self, admin_session):
        email = f"test_invite_{int(time.time())}@example.com"
        resp = admin_session.post(f"{BASE_URL}/api/settings/team", json={
            "email": email, "name": "Invited Member", "role": "team_member", "permissions": []
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "temp_password" in data
        assert data["email"] == email
        assert "password_hash" not in data

    def test_send_invoice_attempts_email(self, admin_session, test_client):
        create = admin_session.post(f"{BASE_URL}/api/invoices", json={
            "client_id": test_client["id"], "line_items": [{"description": "TEST item", "quantity": 1, "price": 100}],
            "due_date": "2026-03-01T00:00:00Z"
        })
        assert create.status_code in (200, 201), create.text
        invoice_id = create.json()["id"]
        send = admin_session.post(f"{BASE_URL}/api/invoices/{invoice_id}/send")
        assert send.status_code == 200, send.text
        assert send.json()["status"] == "sent"

    def test_forgot_password_existing_user(self, admin_session):
        resp = requests.post(f"{BASE_URL}/api/auth/forgot-password", json={"email": ADMIN_EMAIL})
        assert resp.status_code == 200, resp.text
        assert "message" in resp.json()

    def test_forgot_password_nonexistent_user_still_200(self):
        resp = requests.post(f"{BASE_URL}/api/auth/forgot-password", json={"email": "nonexistent_xyz@example.com"})
        assert resp.status_code == 200, resp.text


class TestContractSigning:
    def test_staff_sign_contract(self, admin_session, test_client):
        create = admin_session.post(f"{BASE_URL}/api/contracts", json={
            "title": "TEST Contract Staff Sign", "client_id": test_client["id"]
        })
        assert create.status_code in (200, 201), create.text
        contract_id = create.json()["id"]

        sign = admin_session.post(f"{BASE_URL}/api/contracts/{contract_id}/sign", json={"signature_name": "Jane Staff"})
        assert sign.status_code == 200, sign.text
        data = sign.json()
        assert data["status"] == "signed"
        assert data["signature_name"] == "Jane Staff"
        assert data["signed_at"] is not None

        # verify persisted
        get_resp = admin_session.get(f"{BASE_URL}/api/contracts", params={"client_id": test_client["id"]})
        found = [c for c in get_resp.json() if c["id"] == contract_id][0]
        assert found["status"] == "signed"
        assert found["signature_name"] == "Jane Staff"

    def test_portal_client_sign_contract(self, admin_session, test_client):
        # create portal user for this client
        email = f"test_portal_sign_{int(time.time())}@example.com"
        portal_resp = admin_session.post(f"{BASE_URL}/api/clients/{test_client['id']}/portal-user", json={
            "email": email, "name": "Portal Signer"
        })
        assert portal_resp.status_code == 200, portal_resp.text
        temp_password = portal_resp.json()["temp_password"]

        client_session = requests.Session()
        login = client_session.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": temp_password})
        assert login.status_code == 200, login.text

        create = admin_session.post(f"{BASE_URL}/api/contracts", json={
            "title": "TEST Contract Portal Sign", "client_id": test_client["id"]
        })
        contract_id = create.json()["id"]

        sign = client_session.post(f"{BASE_URL}/api/portal/contracts/{contract_id}/sign", json={"signature_name": "Client Signer"})
        assert sign.status_code == 200, sign.text
        data = sign.json()
        assert data["status"] == "signed"
        assert data["signature_name"] == "Client Signer"

    def test_portal_client_cannot_sign_other_clients_contract(self, admin_session, test_client):
        """Ownership check: a client user should not sign a contract not linked to their client_id."""
        other_client = _create_client_via_won_lead(admin_session, "other")
        contract = admin_session.post(f"{BASE_URL}/api/contracts", json={
            "title": "TEST Other Contract", "client_id": other_client["id"]
        }).json()

        email = f"test_portal_iso_{int(time.time())}@example.com"
        portal_resp = admin_session.post(f"{BASE_URL}/api/clients/{test_client['id']}/portal-user", json={
            "email": email, "name": "Isolated Signer"
        })
        temp_password = portal_resp.json()["temp_password"]
        client_session = requests.Session()
        client_session.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": temp_password})

        sign = client_session.post(f"{BASE_URL}/api/portal/contracts/{contract['id']}/sign", json={"signature_name": "Hacker"})
        assert sign.status_code == 404


class TestProposalPublicSigning:
    def test_create_proposal_has_share_token(self, admin_session, test_client):
        resp = admin_session.post(f"{BASE_URL}/api/proposals", json={
            "title": "TEST Proposal Public Sign", "client_id": test_client["id"], "content": "Scope of work here."
        })
        assert resp.status_code in (200, 201), resp.text
        data = resp.json()
        assert data.get("share_token")
        assert data["status"] == "draft"

    def test_public_get_proposal_no_auth(self, admin_session, test_client):
        create = admin_session.post(f"{BASE_URL}/api/proposals", json={
            "title": "TEST Proposal NoAuth", "client_id": test_client["id"], "content": "Some content"
        }).json()
        token = create["share_token"]

        # fresh session with NO cookies at all
        no_auth = requests.Session()
        resp = no_auth.get(f"{BASE_URL}/api/public/proposals/{token}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["title"] == "TEST Proposal NoAuth"
        assert "versions" not in data

    def test_public_sign_proposal_accept_no_auth(self, admin_session, test_client):
        create = admin_session.post(f"{BASE_URL}/api/proposals", json={
            "title": "TEST Proposal Accept", "client_id": test_client["id"], "content": "Content"
        }).json()
        token = create["share_token"]

        no_auth = requests.Session()
        sign = no_auth.post(f"{BASE_URL}/api/public/proposals/{token}/sign", json={
            "signature_name": "John Client", "signer_email": "john@client.com", "accept": True
        })
        assert sign.status_code == 200, sign.text
        data = sign.json()
        assert data["status"] == "accepted"
        assert data["signature_name"] == "John Client"

        # reload -> should remain finalized, no re-sign allowed
        reget = no_auth.get(f"{BASE_URL}/api/public/proposals/{token}")
        assert reget.json()["status"] == "accepted"

        resign = no_auth.post(f"{BASE_URL}/api/public/proposals/{token}/sign", json={
            "signature_name": "Second Attempt", "signer_email": "x@x.com", "accept": True
        })
        assert resign.status_code == 400

    def test_public_proposal_invalid_token_404(self):
        no_auth = requests.Session()
        resp = no_auth.get(f"{BASE_URL}/api/public/proposals/invalid-token-xyz")
        assert resp.status_code == 404

    def test_share_email_endpoint_sets_status_sent(self, admin_session, test_client):
        create = admin_session.post(f"{BASE_URL}/api/proposals", json={
            "title": "TEST Proposal ShareEmail", "client_id": test_client["id"], "content": "Content"
        }).json()
        resp = admin_session.post(f"{BASE_URL}/api/proposals/{create['id']}/share-email", json={"email": "client@example.com"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["share_token"]

        get_resp = admin_session.get(f"{BASE_URL}/api/proposals/{create['id']}")
        assert get_resp.json()["status"] == "sent"
