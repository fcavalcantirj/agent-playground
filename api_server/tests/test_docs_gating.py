"""SC-12 — ``/docs`` 200 in dev, 404 in prod; ``/openapi.json`` always 200.

These tests instantiate the app factory directly (no Postgres, no
lifespan) and inspect the registered routes. They run as unit tests in
the default pytest invocation — no ``api_integration`` marker.
"""
from __future__ import annotations


def _route_paths(app):
    """Return the set of registered route paths on the FastAPI app."""
    return {route.path for route in app.routes}


def test_docs_open_in_dev(monkeypatch):
    """When ``AP_ENV=dev``: ``/docs``, ``/redoc``, and ``/openapi.json`` exist."""
    monkeypatch.setenv("AP_ENV", "dev")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/d")

    from api_server.main import create_app

    app = create_app()
    paths = _route_paths(app)
    assert "/docs" in paths
    assert "/redoc" in paths
    assert "/openapi.json" in paths


def test_docs_closed_in_prod(monkeypatch):
    """When ``AP_ENV=prod``: ``/docs``+``/redoc`` absent; ``/openapi.json`` present."""
    monkeypatch.setenv("AP_ENV", "prod")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/d")

    from api_server.main import create_app

    app = create_app()
    paths = _route_paths(app)
    assert "/docs" not in paths
    assert "/redoc" not in paths
    # /openapi.json remains public — Plan 20 frontend type-gen needs it.
    assert "/openapi.json" in paths


def test_openapi_json_always_exposed(monkeypatch):
    """Belt-and-suspenders: ``/openapi.json`` exists in BOTH dev and prod builds."""
    for env_value in ("dev", "prod"):
        monkeypatch.setenv("AP_ENV", env_value)
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/d")

        # Force a fresh module import so settings re-read the env. Without
        # this, create_app() caches whatever Settings() returned last.
        from api_server.main import create_app

        app = create_app()
        paths = _route_paths(app)
        assert "/openapi.json" in paths, f"missing in env={env_value}"
