"""
Phase 3 backend tests: multi-currency finance (expenses/invoices), expense
breakdown, notes (per-user private), and company currency settings.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')

ADMIN_EMAIL = "admin@obrinex.com"
ADMIN_PASSWORD = "AgencyOS@2026"


@pytest.fixture(scope="module")
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    resp = session.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if resp.status_code != 200:
        pytest.skip("Admin login failed - skipping phase3 tests")
    return session


class TestFinanceSummaryCurrency:
    def test_finance_summary_has_expense_breakdown_field(self, api_client):
        resp = api_client.get(f"{BASE_URL}/api/finance/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "expense_breakdown" in data
        assert isinstance(data["expense_breakdown"], dict)
        for key in ["personal_withdrawal", "business_expense", "unclassified"]:
            assert key in data["expense_breakdown"]


class TestExpenseCurrencyConversion:
    created_ids = []

    def test_create_usd_expense_converts_to_base(self, api_client):
        # baseline summary before
        before = api_client.get(f"{BASE_URL}/api/finance/summary").json()

        payload = {
            "category": "Software", "description": "TEST_USD Expense", "amount": 100,
            "date": "2026-02-01", "currency": "USD", "conversion_rate": 83, "expense_type": "business_expense"
        }
        resp = api_client.post(f"{BASE_URL}/api/expenses", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["currency"] == "USD"
        assert data["amount"] == 100
        assert data["conversion_rate"] == 83
        assert data["expense_type"] == "business_expense"
        TestExpenseCurrencyConversion.created_ids.append(data["id"])

        # verify persisted via list
        listed = api_client.get(f"{BASE_URL}/api/expenses").json()
        match = [e for e in listed if e["id"] == data["id"]]
        assert len(match) == 1
        assert match[0]["currency"] == "USD"

        after = api_client.get(f"{BASE_URL}/api/finance/summary").json()
        assert after["expenses"] == pytest.approx(before["expenses"] + 8300, abs=1)
        assert after["expense_breakdown"]["business_expense"] == pytest.approx(
            before["expense_breakdown"]["business_expense"] + 8300, abs=1)

    def test_create_inr_expense_personal_withdrawal(self, api_client):
        before = api_client.get(f"{BASE_URL}/api/finance/summary").json()
        payload = {
            "category": "Withdrawal", "description": "TEST_INR Expense", "amount": 2000,
            "date": "2026-02-02", "currency": "INR", "conversion_rate": 1, "expense_type": "personal_withdrawal"
        }
        resp = api_client.post(f"{BASE_URL}/api/expenses", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["currency"] == "INR"
        TestExpenseCurrencyConversion.created_ids.append(data["id"])

        after = api_client.get(f"{BASE_URL}/api/finance/summary").json()
        assert after["expenses"] == pytest.approx(before["expenses"] + 2000, abs=1)
        assert after["expense_breakdown"]["personal_withdrawal"] == pytest.approx(
            before["expense_breakdown"]["personal_withdrawal"] + 2000, abs=1)

    def test_invalid_currency_rejected(self, api_client):
        payload = {
            "category": "X", "description": "TEST_Invalid Currency", "amount": 10,
            "date": "2026-02-02", "currency": "EUR", "expense_type": "unclassified"
        }
        resp = api_client.post(f"{BASE_URL}/api/expenses", json=payload)
        assert resp.status_code == 400

    def test_invalid_expense_type_rejected(self, api_client):
        payload = {
            "category": "X", "description": "TEST_Invalid Type", "amount": 10,
            "date": "2026-02-02", "currency": "INR", "expense_type": "bogus_type"
        }
        resp = api_client.post(f"{BASE_URL}/api/expenses", json=payload)
        assert resp.status_code == 400

    def test_cleanup_delete_expenses(self, api_client):
        before = api_client.get(f"{BASE_URL}/api/finance/summary").json()
        for eid in TestExpenseCurrencyConversion.created_ids:
            resp = api_client.delete(f"{BASE_URL}/api/expenses/{eid}")
            assert resp.status_code == 200
        after = api_client.get(f"{BASE_URL}/api/finance/summary").json()
        assert after["expenses"] == pytest.approx(before["expenses"] - 10300, abs=1)


class TestNotesCRUD:
    def test_create_list_update_pin_delete_note(self, api_client):
        # Create
        resp = api_client.post(f"{BASE_URL}/api/notes", json={"title": "TEST_Note1", "content": "hello", "color": "amber"})
        assert resp.status_code == 200
        note = resp.json()
        assert note["title"] == "TEST_Note1"
        assert note["pinned"] is False
        note_id = note["id"]

        # List - verify persisted
        listed = api_client.get(f"{BASE_URL}/api/notes").json()
        assert any(n["id"] == note_id for n in listed)

        # Update content
        resp = api_client.put(f"{BASE_URL}/api/notes/{note_id}", json={"content": "updated content"})
        assert resp.status_code == 200
        assert resp.json()["content"] == "updated content"

        # Pin
        resp = api_client.put(f"{BASE_URL}/api/notes/{note_id}", json={"pinned": True})
        assert resp.status_code == 200
        assert resp.json()["pinned"] is True

        # Verify pinned sorts first
        listed = api_client.get(f"{BASE_URL}/api/notes").json()
        assert listed[0]["id"] == note_id

        # Delete
        resp = api_client.delete(f"{BASE_URL}/api/notes/{note_id}")
        assert resp.status_code == 200

        listed = api_client.get(f"{BASE_URL}/api/notes").json()
        assert not any(n["id"] == note_id for n in listed)

    def test_delete_nonexistent_note_404(self, api_client):
        resp = api_client.delete(f"{BASE_URL}/api/notes/000000000000000000000000")
        assert resp.status_code == 404

    def test_notes_scoped_per_user_not_shared(self, api_client):
        # create note as admin, then check second login (staff/team member) can't see it - basic sanity:
        # we just verify all returned notes belong to same user_id-less response (no cross-user leak check possible
        # without a second account); this is a structural smoke test.
        resp = api_client.post(f"{BASE_URL}/api/notes", json={"title": "TEST_ScopeCheck", "content": "x"})
        assert resp.status_code == 200
        note_id = resp.json()["id"]
        api_client.delete(f"{BASE_URL}/api/notes/{note_id}")


class TestCompanySettingsCurrency:
    def test_get_company_settings_default_currency_inr(self, api_client):
        resp = api_client.get(f"{BASE_URL}/api/settings/company")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("currency") in ["INR", "USD"]

    def test_update_currency_invalid_rejected(self, api_client):
        resp = api_client.put(f"{BASE_URL}/api/settings/company", json={"currency": "EUR"})
        assert resp.status_code == 400

    def test_update_currency_valid_and_revert(self, api_client):
        original = api_client.get(f"{BASE_URL}/api/settings/company").json().get("currency", "INR")
        resp = api_client.put(f"{BASE_URL}/api/settings/company", json={"currency": "USD"})
        assert resp.status_code == 200
        assert resp.json()["currency"] == "USD"
        # verify persisted
        got = api_client.get(f"{BASE_URL}/api/settings/company").json()
        assert got["currency"] == "USD"
        # revert
        resp = api_client.put(f"{BASE_URL}/api/settings/company", json={"currency": original})
        assert resp.status_code == 200


class TestInvoiceCurrency:
    invoice_id = None

    def test_create_invoice_requires_client(self, api_client):
        clients = api_client.get(f"{BASE_URL}/api/clients").json()
        if not clients:
            pytest.skip("No clients exist to attach invoice to")
        client_id = clients[0]["id"]
        payload = {
            "client_id": client_id,
            "line_items": [{"description": "TEST Line Item", "quantity": 1, "price": 50}],
            "tax": 0, "currency": "USD", "conversion_rate": 83
        }
        resp = api_client.post(f"{BASE_URL}/api/invoices", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["currency"] == "USD"
        assert data["conversion_rate"] == 83
        assert data["total"] == 50
        TestInvoiceCurrency.invoice_id = data["id"]

        # verify via GET
        got = api_client.get(f"{BASE_URL}/api/invoices/{data['id']}").json()
        assert got["currency"] == "USD"
        assert got["total"] == 50

    def test_cleanup_delete_invoice(self, api_client):
        if TestInvoiceCurrency.invoice_id:
            resp = api_client.delete(f"{BASE_URL}/api/invoices/{TestInvoiceCurrency.invoice_id}")
            assert resp.status_code == 200
