import pytest


@pytest.fixture(autouse=True)
def _disable_rate_limiting():
    """Disable rate limiting for unit tests.

    The app uses an in-memory rate limiter middleware which can make tests flaky.
    We mark app.state.testing=True so middleware bypasses the limiter.
    """
    try:
        from main import app
    except Exception:
        # If import fails, let tests surface the error normally.
        yield
        return

    prev = getattr(app.state, "testing", False)
    app.state.testing = True
    try:
        yield
    finally:
        app.state.testing = prev
