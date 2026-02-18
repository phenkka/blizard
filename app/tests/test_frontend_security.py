"""WORLDOFBINDER — Frontend access security tests.

These are backend unit tests that ensure protected HTML pages cannot be accessed
without authentication, even if the user opens them directly by URL.

Important: tests intentionally avoid DB usage so they can run without Docker.
"""

from datetime import datetime, timedelta

import jwt

from fastapi.testclient import TestClient

from main import app, settings


def _make_jwt(payload_overrides: dict | None = None, *, expired: bool = False) -> str:
    now = datetime.utcnow()
    exp = now - timedelta(minutes=5) if expired else now + timedelta(hours=1)
    payload = {
        "userId": 123,
        "walletAddress": "11111111111111111111111111111112",
        "exp": exp,
    }
    if payload_overrides:
        payload.update(payload_overrides)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


class TestHtmlProtection:
    def setup_method(self):
        self.client = TestClient(app)

    def test_app_html_redirects_when_unauthorized(self):
        resp = self.client.get("/app.html", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers.get("location") == "/index.html"

    def test_arena_html_redirects_when_unauthorized(self):
        resp = self.client.get("/arena.html", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers.get("location") == "/index.html"

    def test_app_html_allows_with_cookie_token(self):
        token = _make_jwt()
        self.client.cookies.set("wb_token", token)
        resp = self.client.get("/app.html")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_arena_html_allows_with_cookie_token(self):
        token = _make_jwt()
        self.client.cookies.set("wb_token", token)
        resp = self.client.get("/arena.html")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_app_html_redirects_with_expired_cookie_token(self):
        token = _make_jwt(expired=True)
        self.client.cookies.set("wb_token", token)
        resp = self.client.get("/app.html", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers.get("location") == "/index.html"

    def test_app_html_redirects_with_malformed_cookie_token(self):
        self.client.cookies.set("wb_token", "not-a-jwt")
        resp = self.client.get("/app.html", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers.get("location") == "/index.html"


class TestApiAuthGuards:
    def setup_method(self):
        self.client = TestClient(app)

    def test_protected_api_requires_auth_header(self):
        # These endpoints have Depends(get_current_user) and should reject missing Authorization
        endpoints = [
            ("GET", "/api/user/profile"),
            ("PATCH", "/api/user/profile"),
            ("POST", "/api/user/nfts"),
        ]

        for method, url in endpoints:
            resp = self.client.request(method, url)
            # FastAPI HTTPBearer returns 403 when header is missing
            assert resp.status_code in (401, 403)

    def test_protected_api_rejects_invalid_bearer_token(self):
        endpoints = [
            ("GET", "/api/user/profile"),
            ("PATCH", "/api/user/profile"),
            ("POST", "/api/user/nfts"),
        ]

        headers = {"Authorization": "Bearer not-a-jwt"}
        for method, url in endpoints:
            resp = self.client.request(method, url, headers=headers)
            assert resp.status_code == 401

    def test_protected_api_rejects_expired_token(self):
        expired = _make_jwt(expired=True)
        headers = {"Authorization": f"Bearer {expired}"}
        resp = self.client.get("/api/user/profile", headers=headers)
        assert resp.status_code == 401
