from __future__ import annotations

from fastapi.testclient import TestClient

import main


def _auth_headers(wallet: str = "11111111111111111111111111111112"):
    token = main.SecurityUtils.create_jwt_token({"userId": 1, "walletAddress": wallet})
    return {"Authorization": f"Bearer {token}"}


class _FakeDB:
    def __init__(self):
        self.connected = False
        self.level = 1

    def connect(self):
        self.connected = True

    def close(self):
        self.connected = False

    def execute_query(self, query: str, params=None, fetch: str = "all"):
        q = " ".join(query.split()).lower()

        if q.startswith("select id from users"):
            return {"id": 1}

        if q.startswith("insert into user_skill_levels"):
            # simulate increment
            self.level += 1
            return {"level": self.level}

        return None


def test_skills_upgrade_rejects_invalid_burn(monkeypatch):
    monkeypatch.setattr(main.settings, "token_mint", "MINT")
    monkeypatch.setattr(main.settings, "token_decimals", 6)
    monkeypatch.setattr(main.settings, "burn_cost_per_level", 50000)

    async def _fake_tx(sig: str):
        return {"result": {"meta": {"err": None}, "transaction": {"message": {"instructions": []}}}}

    monkeypatch.setattr(main, "_solana_get_transaction", _fake_tx)

    c = TestClient(main.app)
    resp = c.post(
        "/api/skills/upgrade",
        headers=_auth_headers(),
        json={"skillKey": "bladeStrike", "txSignature": "S" * 64},
    )
    assert resp.status_code == 400


def test_skills_upgrade_accepts_valid_burn_and_updates_level(monkeypatch):
    monkeypatch.setattr(main.settings, "token_mint", "MINT")
    monkeypatch.setattr(main.settings, "token_decimals", 6)
    monkeypatch.setattr(main.settings, "burn_cost_per_level", 50000)

    wallet = "11111111111111111111111111111112"
    raw_amount = 50000 * (10**6)

    async def _fake_tx(sig: str):
        return {
            "result": {
                "meta": {"err": None},
                "transaction": {
                    "message": {
                        "instructions": [
                            {
                                "parsed": {
                                    "type": "burn",
                                    "info": {
                                        "mint": "MINT",
                                        "authority": wallet,
                                        "amount": str(raw_amount),
                                    },
                                }
                            }
                        ]
                    }
                },
            }
        }

    monkeypatch.setattr(main, "_solana_get_transaction", _fake_tx)

    db = _FakeDB()
    monkeypatch.setattr(main, "Database", lambda: db)

    c = TestClient(main.app)
    resp = c.post(
        "/api/skills/upgrade",
        headers=_auth_headers(wallet),
        json={"skillKey": "bladeStrike", "txSignature": "S" * 64},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["skillKey"] == "bladeStrike"
    assert body["level"] >= 2
