"""Error handling: correct status codes, no internal detail in responses."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError

from app.main import create_app


class ProbePayload(BaseModel):
    """Declared at module scope: FastAPI cannot resolve forward refs to a class
    defined inside a test function."""

    name: str


def _probe_app(settings, *handlers):
    """Build the real app and bolt probe routes onto it.

    Probing through the production factory means the tests exercise the actual
    middleware stack and exception handlers, not a copy of them.
    """
    app = create_app(settings)
    probe = APIRouter()
    for handler in handlers:
        probe.add_api_route(
            f"/_probe/{handler.__name__}", handler, methods=["GET", "POST"]
        )
    app.include_router(probe)
    return app


def _unknown_route():
    raise HTTPException(status_code=404, detail="Probe not found.")


def _boom():
    raise RuntimeError("secret internal detail /home/user/private")


def _db_error():
    raise OperationalError("SELECT 1", {}, Exception("password=hunter2 host=internal"))


def _validate(payload: ProbePayload = Body(...)):  # noqa: B008 - FastAPI dependency idiom
    return {"ok": True, "name": payload.name}


def test_unknown_route_returns_404(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json()["detail"] == "Not Found"


def test_http_exception_detail_is_preserved(settings):
    with TestClient(_probe_app(settings, _unknown_route), raise_server_exceptions=False) as c:
        response = c.get("/_probe/_unknown_route")
    assert response.status_code == 404
    assert response.json()["detail"] == "Probe not found."


def test_unhandled_error_hides_internals(settings):
    with TestClient(_probe_app(settings, _boom), raise_server_exceptions=False) as c:
        response = c.get("/_probe/_boom")
    assert response.status_code == 500
    for forbidden in ("secret internal detail", "/home/user", "Traceback", "RuntimeError"):
        assert forbidden not in response.text
    assert "unexpected error" in response.json()["detail"].lower()


def test_unhandled_error_shows_detail_when_secure_errors_disabled(settings):
    settings.secure_errors = False
    try:
        with TestClient(_probe_app(settings, _boom), raise_server_exceptions=False) as c:
            response = c.get("/_probe/_boom")
        assert response.status_code == 500
        assert "RuntimeError" in response.text
    finally:
        settings.secure_errors = True


def test_request_id_is_present_on_success_and_error(client):
    assert len(client.get("/health").headers["x-request-id"]) >= 8
    assert len(client.get("/does-not-exist").headers["x-request-id"]) >= 8


def test_validation_error_shape_is_stable(settings):
    """A 422 must be machine-readable and must not echo the submitted value."""
    with TestClient(_probe_app(settings, _validate), raise_server_exceptions=False) as c:
        response = c.post("/_probe/_validate", json={"wrong": "hunter2-secret"})
    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == "Validation failed."
    assert body["errors"][0]["field"] == "name"
    assert "hunter2-secret" not in response.text


def test_valid_payload_passes_validation(settings):
    with TestClient(_probe_app(settings, _validate), raise_server_exceptions=False) as c:
        response = c.post("/_probe/_validate", json={"name": "ok"})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "name": "ok"}


def test_database_failure_returns_503_not_500(settings):
    with TestClient(_probe_app(settings, _db_error), raise_server_exceptions=False) as c:
        response = c.get("/_probe/_db_error")
    assert response.status_code == 503
    assert "hunter2" not in response.text
    assert "internal" not in response.text
    assert "temporarily unavailable" in response.json()["detail"].lower()
