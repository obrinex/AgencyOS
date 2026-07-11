import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
ADMIN_EMAIL = "info@obrinex.space"
ADMIN_PASSWORD = "Obrinex@2009"


def _create_client_via_won_lead(session, tag):
    company_name = f"TEST_PayReq_{tag}_{int(time.time()*1000)}"
    lead_resp = session.post(f"{BASE_URL}/api/leads", json={"company": company_name, "revenue": 1200})
    assert lead_resp.status_code == 200, lead_resp.text
    lead_id = lead_resp.json()["id"]
    won_resp = session.patch(f"{BASE_URL}/api/leads/{lead_id}/stage", json={"stage": "won"})
    assert won_resp.status_code == 200, won_resp.text
    client_id = won_resp.json()["automation"]["client_id"]
    client = session.get(f"{BASE_URL}/api/clients/{client_id}").json()
    return client


def _create_client_portal_user(admin_session, client_id, email):
    resp = admin_session.post(f"{BASE_URL}/api/clients/{client_id}/portal-user", json={
        "email": email, "name": "Portal Test User"
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


def _login_portal_user(email, temp_password):
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": temp_password})
    assert resp.status_code == 200, resp.text
    return s


def test_payment_request_flow(admin_session):
    # 1. Create a client and portal access
    client = _create_client_via_won_lead(admin_session, "flow")
    email = f"test_pay_flow_{int(time.time())}@example.com"
    portal_data = _create_client_portal_user(admin_session, client["id"], email)
    client_session = _login_portal_user(email, portal_data["temp_password"])

    # 2. Create a draft invoice for this client
    inv_resp = admin_session.post(f"{BASE_URL}/api/invoices", json={
        "client_id": client["id"],
        "line_items": [{"description": "Services Rendered", "quantity": 1, "price": 1500}],
        "due_date": "2026-08-01T00:00:00Z"
    })
    assert inv_resp.status_code in (200, 201), inv_resp.text
    invoice = inv_resp.json()
    assert invoice["status"] == "draft"

    # 3. Client requests payment link
    req_resp = client_session.post(f"{BASE_URL}/api/invoices/{invoice['id']}/request-payment")
    assert req_resp.status_code == 200, req_resp.text
    req_data = req_resp.json()
    assert req_data["invoice_id"] == invoice["id"]
    assert req_data["status"] == "pending"
    assert req_data["amount"] == 1500

    # 4. Admin lists payment requests and finds the request
    list_resp = admin_session.get(f"{BASE_URL}/api/admin/payment-requests")
    assert list_resp.status_code == 200, list_resp.text
    all_reqs = list_resp.json()
    matched = [r for r in all_reqs if r["invoice_id"] == invoice["id"]]
    assert len(matched) == 1
    payment_request_id = matched[0]["id"]

    # 5. Admin sends the payment link
    send_resp = admin_session.post(
        f"{BASE_URL}/api/admin/payment-requests/{payment_request_id}/send-link",
        json={"payment_link": "https://checkout.stripe.com/pay/mock_session_123"}
    )
    assert send_resp.status_code == 200, send_resp.text
    send_data = send_resp.json()
    assert send_data["status"] == "sent"
    assert send_data["payment_link"] == "https://checkout.stripe.com/pay/mock_session_123"

    # 6. Verify invoice status is updated to 'sent'
    inv_verify = admin_session.get(f"{BASE_URL}/api/invoices/{invoice['id']}")
    assert inv_verify.status_code == 200
    assert inv_verify.json()["status"] == "sent"


def test_payment_request_security(admin_session):
    # Create two clients
    client1 = _create_client_via_won_lead(admin_session, "sec1")
    client2 = _create_client_via_won_lead(admin_session, "sec2")

    email1 = f"sec1_{int(time.time())}@example.com"
    portal1 = _create_client_portal_user(admin_session, client1["id"], email1)
    session1 = _login_portal_user(email1, portal1["temp_password"])

    email2 = f"sec2_{int(time.time())}@example.com"
    portal2 = _create_client_portal_user(admin_session, client2["id"], email2)
    session2 = _login_portal_user(email2, portal2["temp_password"])

    # Create invoice for client1
    inv_resp = admin_session.post(f"{BASE_URL}/api/invoices", json={
        "client_id": client1["id"],
        "line_items": [{"description": "Item", "quantity": 1, "price": 500}]
    })
    invoice1 = inv_resp.json()

    # Client2 should NOT be able to request payment for Client1's invoice
    req_bad = session2.post(f"{BASE_URL}/api/invoices/{invoice1['id']}/request-payment")
    assert req_bad.status_code == 403

    # Client1 should NOT be able to access the admin payment requests list
    admin_list_bad = session1.get(f"{BASE_URL}/api/admin/payment-requests")
    assert admin_list_bad.status_code in (401, 403)


def test_admin_can_record_invoice_payment_outcome(admin_session):
    client = _create_client_via_won_lead(admin_session, "paymentstatus")
    invoice_resp = admin_session.post(f"{BASE_URL}/api/invoices", json={
        "client_id": client["id"],
        "line_items": [{"description": "Retainer", "quantity": 1, "price": 2500}],
    })
    assert invoice_resp.status_code == 200, invoice_resp.text
    invoice_id = invoice_resp.json()["id"]

    for status in ("pending", "failed", "paid"):
        response = admin_session.post(
            f"{BASE_URL}/api/invoices/{invoice_id}/payment-status",
            json={"status": status},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == status
        assert data["payment_status"] == status

    assert data["paid_at"] is not None
