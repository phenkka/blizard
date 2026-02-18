from __future__ import annotations

from fastapi.testclient import TestClient

import main


def _auth_headers(wallet: str = "11111111111111111111111111111112"):
    token = main.SecurityUtils.create_jwt_token({"userId": 1, "walletAddress": wallet})
    return {"Authorization": f"Bearer {token}"}


def test_wallet_scan_filters_collection_limits_and_attack_bonus(monkeypatch):
    # Arrange
    monkeypatch.setattr(main.settings, "collection_address", "COLLECTION_ABC")

    async def _fake_helius(owner: str):
        assert owner
        return {
            "result": {
                "items": [
                    {
                        "id": "nft1",
                        "grouping": [{"group_key": "collection", "group_value": "COLLECTION_ABC"}],
                        "content": {
                            "metadata": {"name": "NFT #1", "attributes": [{"trait_type": "a", "value": "b"}]},
                            "files": [{"uri": "http://example.com/1.png"}],
                        },
                    },
                    {
                        "id": "nft2",
                        "grouping": [{"group_key": "collection", "group_value": "COLLECTION_ABC"}],
                        "content": {
                            "metadata": {"name": "NFT #2", "attributes": []},
                            "files": [{"uri": "http://example.com/2.png"}],
                        },
                    },
                    {
                        "id": "nft3",
                        "grouping": [{"group_key": "collection", "group_value": "COLLECTION_ABC"}],
                        "content": {
                            "metadata": {"name": "NFT #3"},
                            "files": [{"uri": "http://example.com/3.png"}],
                        },
                    },
                    # Should be ignored due to limit 3
                    {
                        "id": "nft4",
                        "grouping": [{"group_key": "collection", "group_value": "COLLECTION_ABC"}],
                        "content": {"metadata": {"name": "NFT #4"}, "files": [{"uri": "http://example.com/4.png"}]},
                    },
                    # Should be ignored due to different collection
                    {
                        "id": "other",
                        "grouping": [{"group_key": "collection", "group_value": "OTHER"}],
                        "content": {"metadata": {"name": "Other"}, "files": [{"uri": "http://example.com/x.png"}]},
                    },
                ]
            }
        }

    monkeypatch.setattr(main, "_helius_get_assets_by_owner", _fake_helius)

    c = TestClient(main.app)

    # Act
    resp = c.post(
        "/api/wallet/scan",
        headers=_auth_headers(),
        json={"walletAddress": "11111111111111111111111111111112"},
    )

    # Assert
    assert resp.status_code == 200
    body = resp.json()
    assert body["attackBonus"] == 20
    assert len(body["nfts"]) == 3
    assert body["nfts"][0]["id"] == "nft1"
    assert body["nfts"][0]["name"] == "NFT #1"
    assert body["nfts"][0]["image"] == "http://example.com/1.png"
