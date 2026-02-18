from fastapi.testclient import TestClient

import main


class _FakeDB:
    def __init__(self):
        self.connected = False

    def connect(self):
        self.connected = True

    def close(self):
        self.connected = False

    def execute_query(self, query: str, params=None, fetch: str = "all"):
        q = " ".join(query.split()).lower()

        # user/profile
        if "from users" in q and "where wallet_address" in q:
            return {
                "id": 1,
                "wallet_address": params[0],
                "username": "tester",
                "avatar_url": None,
                "created_at": main.datetime.utcnow(),
                "last_login": main.datetime.utcnow(),
            }

        # user_nfts
        if "from user_nfts" in q:
            return []

        # update users
        if q.strip().startswith("update users"):
            return {
                "id": 1,
                "wallet_address": params[3],
                "username": params[0],
                "avatar_url": params[1],
                "created_at": main.datetime.utcnow(),
                "last_login": main.datetime.utcnow(),
            }

        # insert nft
        if q.strip().startswith("insert into user_nfts"):
            return None

        # skills
        if "from skills" in q:
            return [
                {"id": 1, "name": "Blade Strike", "required_level": 1},
                {"id": 2, "name": "Energy Burst", "required_level": 2},
            ]

        # leaderboard
        if "from leaderboard" in q:
            return [
                {
                    "user_id": 1,
                    "points": 100,
                    "wins": 1,
                    "losses": 0,
                    "username": "tester",
                    "wallet_address": params[0] if params else "11111111111111111111111111111112",
                }
            ]

        return None


def _auth_headers():
    token = main.SecurityUtils.create_jwt_token(
        {"userId": 1, "walletAddress": "11111111111111111111111111111112"}
    )
    return {"Authorization": f"Bearer {token}"}


def test_profile_update_and_nft_and_lists_with_mock_db(monkeypatch):
    # Patch DB used by endpoints
    monkeypatch.setattr(main, "Database", _FakeDB)
    main.app.state.testing = True

    client = TestClient(main.app)
    headers = _auth_headers()

    # profile get
    resp = client.get("/api/user/profile", headers=headers)
    assert resp.status_code == 200

    # profile update
    resp = client.patch(
        "/api/user/profile",
        headers=headers,
        json={"username": "newname", "avatarUrl": None},
    )
    assert resp.status_code == 200

    # add nft
    resp = client.post(
        "/api/user/nfts",
        headers=headers,
        json={
            "mintAddress": "11111111111111111111111111111111111111111111",
            "name": "NFT",
            "imageUrl": "http://example.com/a.png",
            "rarity": "Common",
        },
    )
    assert resp.status_code in (200, 201)

    # skills list
    resp = client.get("/api/skills")
    assert resp.status_code == 200

    # leaderboard list
    resp = client.get("/api/leaderboard")
    assert resp.status_code == 200


def test_static_index_served(client=None):
    c = TestClient(main.app)
    resp = c.get("/index.html")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


def test_health_check_healthy_with_mock_db(monkeypatch):
    class _OkDB:
        def __init__(self):
            self.pool = True

        def connect(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(main, "Database", _OkDB)
    c = TestClient(main.app)
    resp = c.get("/api/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "healthy"


def test_app_html_cookie_auth_allows_access(monkeypatch):
    c = TestClient(main.app)
    token = main.SecurityUtils.create_jwt_token({
        "userId": 1,
        "walletAddress": "11111111111111111111111111111112",
    })
    c.cookies.set("wb_token", token)
    resp = c.get("/app.html", follow_redirects=False)
    assert resp.status_code == 200


def test_profile_returns_404_when_user_missing(monkeypatch):
    class _MissingUserDB(_FakeDB):
        def execute_query(self, query: str, params=None, fetch: str = "all"):
            q = " ".join(query.split()).lower()
            if "from users" in q and "where wallet_address" in q:
                return None
            return super().execute_query(query, params=params, fetch=fetch)

    monkeypatch.setattr(main, "Database", _MissingUserDB)
    main.app.state.testing = True
    c = TestClient(main.app)
    resp = c.get("/api/user/profile", headers=_auth_headers())
    assert resp.status_code == 404


def test_add_nft_returns_404_when_user_missing(monkeypatch):
    class _MissingUserIdDB(_FakeDB):
        def execute_query(self, query: str, params=None, fetch: str = "all"):
            q = " ".join(query.split()).lower()
            if q.strip().startswith("select id from users"):
                return None
            return super().execute_query(query, params=params, fetch=fetch)

    monkeypatch.setattr(main, "Database", _MissingUserIdDB)
    main.app.state.testing = True
    c = TestClient(main.app)
    resp = c.post(
        "/api/user/nfts",
        headers=_auth_headers(),
        json={
            "mintAddress": "11111111111111111111111111111111111111111111",
            "name": "NFT",
            "imageUrl": "http://example.com/a.png",
            "rarity": "Common",
        },
    )
    assert resp.status_code == 404
