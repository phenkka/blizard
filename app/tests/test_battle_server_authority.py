import asyncio
from fastapi.testclient import TestClient

import main


class _BattleDB:
    def __init__(self):
        self.connected = False
        self.user_id = 1
        self.wallet = "11111111111111111111111111111112"
        self.leaderboard = {self.user_id: {"points": 500, "wins": 0, "losses": 0}}

    def connect(self):
        self.connected = True

    def close(self):
        self.connected = False

    def execute_query(self, query: str, params=None, fetch: str = "all"):
        q = " ".join(query.split()).lower()

        if q.startswith("select id from users") and "where wallet_address" in q:
            return {"id": self.user_id}

        if q.startswith("update leaderboard") and "set points = points -" in q:
            bet = int(params[0])
            uid = int(params[1])
            min_required = int(params[2])
            row = self.leaderboard.get(uid)
            if not row:
                return None
            if row["points"] < min_required:
                return None
            row["points"] -= bet
            return {"points": row["points"], "wins": row["wins"], "losses": row["losses"]}

        if q.startswith("update leaderboard") and "set points = points +" in q and "wins = wins + 1" in q:
            payout = int(params[0])
            uid = int(params[1])
            row = self.leaderboard.setdefault(uid, {"points": 0, "wins": 0, "losses": 0})
            row["points"] += payout
            row["wins"] += 1
            return {"points": row["points"], "wins": row["wins"], "losses": row["losses"]}

        if q.startswith("update leaderboard") and "set losses = losses + 1" in q:
            uid = int(params[0])
            row = self.leaderboard.setdefault(uid, {"points": 0, "wins": 0, "losses": 0})
            row["losses"] += 1
            return {"points": row["points"], "wins": row["wins"], "losses": row["losses"]}

        return None


def _auth_headers(wallet: str = "11111111111111111111111111111112"):
    token = main.SecurityUtils.create_jwt_token({"userId": 1, "walletAddress": wallet})
    return {"Authorization": f"Bearer {token}"}


def test_nft_stats_deterministic_with_salt(monkeypatch):
    monkeypatch.setattr(main.settings, "nft_stats_salt", "salt-A")
    a1 = main.generate_nft_stats("1" * 44, "Common", main.settings.nft_stats_salt)
    a2 = main.generate_nft_stats("1" * 44, "Common", main.settings.nft_stats_salt)
    assert a1 == a2

    monkeypatch.setattr(main.settings, "nft_stats_salt", "salt-B")
    b1 = main.generate_nft_stats("1" * 44, "Common", main.settings.nft_stats_salt)
    assert b1 != a1


def test_battle_start_rejects_insufficient_points(monkeypatch):
    db = _BattleDB()
    db.leaderboard[db.user_id]["points"] = 10
    monkeypatch.setattr(main, "Database", lambda: db)

    c = TestClient(main.app)
    resp = c.post(
        "/api/battle/start",
        headers=_auth_headers(db.wallet),
        json={"mintAddress": "1" * 44, "bet": 11},
    )
    assert resp.status_code == 400
    assert resp.json().get("detail") == "Insufficient points"


def test_battle_start_debits_and_resolves_updates_leaderboard(monkeypatch):
    db = _BattleDB()
    monkeypatch.setattr(main, "Database", lambda: db)

    c = TestClient(main.app)

    # start
    resp = c.post(
        "/api/battle/start",
        headers=_auth_headers(db.wallet),
        json={"mintAddress": "1" * 44, "bet": 100},
    )
    assert resp.status_code == 200
    body = resp.json()
    battle_id = body["battle_id"]

    # server-authoritative debit happened immediately
    assert db.leaderboard[db.user_id]["points"] == 400

    # force resolve now
    main.app.state.battles[battle_id]["resolve_at"] = main.time.time() - 1
    asyncio.run(main._resolve_battle(main.app, battle_id))

    status = c.get(f"/api/battle/{battle_id}", headers=_auth_headers(db.wallet))
    assert status.status_code == 200
    data = status.json()
    assert data["status"] == "resolved"
    assert data["result"] is not None
    assert data["result"]["bet"] == 100

    # result should match leaderboard (either win added payout or loss increments)
    res = data["result"]
    assert res["points"] == db.leaderboard[db.user_id]["points"]
    assert res["wins"] == db.leaderboard[db.user_id]["wins"]
    assert res["losses"] == db.leaderboard[db.user_id]["losses"]
