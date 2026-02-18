from __future__ import annotations

import concurrent.futures
import threading

from fastapi.testclient import TestClient

import main


class _LeaderboardState:
    def __init__(self):
        self._lock = threading.Lock()
        self.rows = [
            {
                "user_id": 1,
                "points": 10,
                "wins": 1,
                "losses": 0,
                "username": "a",
                "wallet_address": "w1",
            },
            {
                "user_id": 2,
                "points": 9,
                "wins": 9,
                "losses": 0,
                "username": "b",
                "wallet_address": "w2",
            },
        ]

    def snapshot(self):
        with self._lock:
            return [dict(r) for r in self.rows]

    def update_points(self, user_id: int, points: int, wins: int | None = None):
        with self._lock:
            for r in self.rows:
                if r["user_id"] == user_id:
                    r["points"] = points
                    if wins is not None:
                        r["wins"] = wins
                    return
            self.rows.append(
                {
                    "user_id": user_id,
                    "points": points,
                    "wins": wins or 0,
                    "losses": 0,
                    "username": f"u{user_id}",
                    "wallet_address": f"w{user_id}",
                }
            )


def test_leaderboard_contract_sorting_and_limit(monkeypatch):
    state = _LeaderboardState()

    class _FakeDB:
        def connect(self):
            return None

        def close(self):
            return None

        def execute_query(self, query: str, params=None, fetch: str = "all"):
            # Return UNSORTED and >100 rows to verify app-level contract enforcement
            rows = state.snapshot()
            for i in range(3, 130):
                rows.append(
                    {
                        "user_id": i,
                        "points": i % 7,
                        "wins": i % 3,
                        "losses": 0,
                        "username": f"u{i}",
                        "wallet_address": f"w{i}",
                    }
                )
            return rows[::-1]

    monkeypatch.setattr(main, "Database", _FakeDB)
    main.app.state.testing = True

    c = TestClient(main.app)
    resp = c.get("/api/leaderboard")
    assert resp.status_code == 200

    data = resp.json()
    assert "leaderboard" in data
    entries = data["leaderboard"]

    # Limit
    assert len(entries) == 100

    # Schema
    for e in entries[:5]:
        assert "user_id" in e
        assert "points" in e
        assert "wins" in e
        assert "losses" in e
        assert "username" in e
        assert "wallet_address" in e

    # Sorted by points desc, wins desc
    for prev, nxt in zip(entries, entries[1:]):
        prev_key = (-int(prev.get("points", 0)), -int(prev.get("wins", 0)))
        nxt_key = (-int(nxt.get("points", 0)), -int(nxt.get("wins", 0)))
        assert prev_key <= nxt_key


def test_leaderboard_realtime_polling_sees_updates(monkeypatch):
    state = _LeaderboardState()

    class _FakeDB:
        def connect(self):
            return None

        def close(self):
            return None

        def execute_query(self, query: str, params=None, fetch: str = "all"):
            return state.snapshot()

    monkeypatch.setattr(main, "Database", _FakeDB)
    main.app.state.testing = True

    c = TestClient(main.app)

    r1 = c.get("/api/leaderboard")
    assert r1.status_code == 200
    top1 = r1.json()["leaderboard"][0]["user_id"]

    # Update state as if a battle finished
    state.update_points(user_id=2, points=999, wins=10)

    r2 = c.get("/api/leaderboard")
    assert r2.status_code == 200
    top2 = r2.json()["leaderboard"][0]["user_id"]

    assert top1 != top2
    assert top2 == 2


def test_leaderboard_parallel_requests_no_5xx(monkeypatch):
    state = _LeaderboardState()

    class _FakeDB:
        def connect(self):
            return None

        def close(self):
            return None

        def execute_query(self, query: str, params=None, fetch: str = "all"):
            return state.snapshot()

    monkeypatch.setattr(main, "Database", _FakeDB)
    main.app.state.testing = True

    c = TestClient(main.app)

    def hit():
        r = c.get("/api/leaderboard")
        return r.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        statuses = list(ex.map(lambda _: hit(), range(80)))

    assert all(s == 200 for s in statuses)
