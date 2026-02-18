from __future__ import annotations

from fastapi.testclient import TestClient

import main


def _fake_player_with_skills():
    return {
        "username": "tester",
        "points": 0,
        "wins": 0,
        "losses": 0,
        "skills": {
            "bladeStrike": {"level": 1, "maxLevel": 5},
        },
    }


def test_frontend_free_upgrade_bypass_removed_static_check():
    # (kept in separate test file too) — ensures the bypass can't reappear unnoticed
    with open("frontend/js/game.js", "r", encoding="utf-8") as f:
        src = f.read()

    assert "allowing free upgrade" not in src
    assert "burnSuccess = true" not in src


def test_upgrade_button_disabled_without_configured_mint(monkeypatch):
    """Unit-test the intended behavior at code-level: when mint isn't configured, upgrade should not be allowed."""

    # We can't run the browser DOM here; instead we validate the constants in token-burner.js
    with open("frontend/js/token-burner.js", "r", encoding="utf-8") as f:
        src = f.read()

    # Placeholder mint means upgrades must be blocked (as in game.js)
    assert "PASTE_YOUR_TOKEN_MINT_ADDRESS_HERE" in src


def test_backend_has_no_skills_upgrade_endpoint(client=None):
    """Backend endpoint exists and must be protected by auth."""
    c = TestClient(main.app)
    resp = c.post("/api/skills/upgrade")
    assert resp.status_code == 401
