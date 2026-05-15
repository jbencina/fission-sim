"""Smoke tests for the fission_sim.api health endpoint.

These tests use FastAPI's TestClient (backed by httpx) so no real server
is started — the ASGI app is called directly in-process.
"""

from fastapi.testclient import TestClient

from fission_sim.api.app import app


def test_health_returns_200():
    """GET /api/health must return HTTP 200."""
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200


def test_health_returns_ok_json():
    """GET /api/health must return JSON body {"status": "ok"}."""
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.json() == {"status": "ok"}
