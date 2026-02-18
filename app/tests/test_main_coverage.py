import pytest

from fastapi.testclient import TestClient

import main


@pytest.fixture()
def client():
    return TestClient(main.app)


def test_root_api(client):
    resp = client.get("/api")
    assert resp.status_code == 200
    assert resp.json().get("status") == "running"


def test_frontend_config(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "API_BASE_URL" in data


def test_refresh_not_implemented(client):
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 404


def test_health_check_returns_503_when_db_unavailable(client):
    # In local unit test env DB host "db" is not reachable; endpoint should return 503 JSON
    resp = client.get("/api/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body.get("status") == "unhealthy"


def test_protected_html_allows_authorization_header(client):
    token = main.SecurityUtils.create_jwt_token({
        "userId": 1,
        "walletAddress": "11111111111111111111111111111112",
    })
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/app.html", headers=headers, follow_redirects=False)
    assert resp.status_code == 200


def test_rate_limit_middleware_blocks_when_not_allowed(monkeypatch):
    # Ensure we exercise the 429 branch.
    main.app.state.testing = False

    def deny(_client_id, limit=None, window=None):
        return False

    monkeypatch.setattr(main.rate_limiter, "is_allowed", deny)

    c = TestClient(main.app)
    resp = c.get("/api")
    assert resp.status_code == 429


def test_rate_limit_middleware_bypasses_in_testing(monkeypatch):
    # Ensure we exercise the bypass branch.
    main.app.state.testing = True

    def deny(_client_id, limit=None, window=None):
        return False

    monkeypatch.setattr(main.rate_limiter, "is_allowed", deny)

    c = TestClient(main.app)
    resp = c.get("/api")
    assert resp.status_code == 200
    assert resp.json().get("status") == "running"
