def test_no_free_skill_upgrade_bypass_present():
    """Ensure frontend skill upgrade cannot be done for free when token mint is not configured."""

    path = "frontend/js/game.js"
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    # Old bypass text must not exist
    assert "allowing free upgrade" not in src
    assert "burnSuccess = true" not in src

    # New behavior must exist
    assert "upgrade disabled" in src
