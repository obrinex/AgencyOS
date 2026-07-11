"""Auth: login, cookies, brute force lockout, /me, logout"""
import os
import time
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
ADMIN_EMAIL = "info@obrinex.space"
ADMIN_PASSWORD = "Obrinex@2009"


class TestLogin:
    def test_admin_login_success(self):
        s = requests.Session()
        resp = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"
        assert "password_hash" not in data
        assert "two_fa_secret" not in data

    def test_httponly_cookies_set(self):
        s = requests.Session()
        resp = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert resp.status_code == 200
        cookie_names = [c.name for c in s.cookies]
        assert "access_token" in cookie_names
        assert "refresh_token" in cookie_names

    def test_invalid_credentials(self):
        s = requests.Session()
        resp = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrongpassword"})
        assert resp.status_code == 401

    def test_me_endpoint_requires_auth(self):
        s = requests.Session()
        resp = s.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 401

    def test_me_endpoint_with_auth(self):
        s = requests.Session()
        s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        resp = s.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200
        assert resp.json()["email"] == ADMIN_EMAIL

    def test_logout(self):
        s = requests.Session()
        s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        resp = s.post(f"{BASE_URL}/api/auth/logout")
        assert resp.status_code == 200
        resp2 = s.get(f"{BASE_URL}/api/auth/me")
        assert resp2.status_code == 401


class TestBruteForce:
    def test_lockout_after_5_failed_attempts(self):
        s = requests.Session()
        email = "brutetest_TEST@obrinex.com"
        for i in range(5):
            resp = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "wrong"})
            assert resp.status_code in (401,)
        resp = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "wrong"})
        assert resp.status_code == 429


class TestCORS:
    def test_cors_allows_credentials_explicit_origin(self):
        resp = requests.options(
            f"{BASE_URL}/api/auth/login",
            headers={
                "Origin": BASE_URL,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        acao = resp.headers.get("access-control-allow-origin")
        acac = resp.headers.get("access-control-allow-credentials")
        assert acao is not None, "CORS allow-origin header missing"
        assert acao != "*", "CORS should not use wildcard origin when credentials enabled"
        assert acac == "true"
