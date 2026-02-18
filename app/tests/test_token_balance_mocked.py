from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

import main


def _auth_headers(wallet: str = "11111111111111111111111111111112"):
    token = main.SecurityUtils.create_jwt_token({"userId": 1, "walletAddress": wallet})
    return {"Authorization": f"Bearer {token}"}


def test_token_balance_endpoint_uses_backend_helper(monkeypatch):
    monkeypatch.setattr(main.settings, "token_mint", "MINT")

    async def _fake_balance(wallet: str, mint: str):
        assert wallet
        assert mint == "MINT"
        return 123.0

    monkeypatch.setattr(main, "_solana_get_token_balance", _fake_balance)

    c = TestClient(main.app)
    resp = c.post(
        "/api/wallet/token-balance",
        headers=_auth_headers(),
        json={"walletAddress": "11111111111111111111111111111112"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["mint"] == "MINT"
    assert body["balance"] == 123.0


def test_solana_get_token_balance_parses_json(monkeypatch):
    monkeypatch.setattr(main.settings, "solana_rpc", "http://rpc.local")

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "result": {
                    "value": [
                        {
                            "account": {
                                "data": {
                                    "parsed": {
                                        "info": {
                                            "tokenAmount": {
                                                "uiAmount": 42.5,
                                                "uiAmountString": "42.5",
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    ]
                }
            }

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json):
            assert url == "http://rpc.local"
            assert json["method"] == "getTokenAccountsByOwner"
            return _Resp()

    monkeypatch.setattr(main.httpx, "AsyncClient", _Client)

    bal = asyncio.run(main._solana_get_token_balance("W" * 32, "M" * 32))
    assert bal == 42.5
