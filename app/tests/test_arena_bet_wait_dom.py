def test_arena_has_bet_and_wait_overlays():
    path = "frontend/arena.html"
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    assert 'id="overlay-bet"' in html
    assert 'id="bet-amount"' in html
    assert 'id="btn-bet-confirm"' in html
    assert 'id="overlay-wait"' in html
    assert 'id="wait-seconds"' in html
