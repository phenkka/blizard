from fastapi.testclient import TestClient

import main


def test_api_config_exposes_token_mint(monkeypatch):
    monkeypatch.setattr(main.settings, "token_mint", "TEST_MINT_123")
    c = TestClient(main.app)
    resp = c.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("TOKEN_MINT") == "TEST_MINT_123"
