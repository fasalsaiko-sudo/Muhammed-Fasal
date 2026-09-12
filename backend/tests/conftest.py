"""Test fixtures for the Phase 2 foundation.

The suite runs against whichever ``DATABASE_URL`` is configured:

* SQLite (default) — fast, no setup. A green SQLite run is NOT PostgreSQL
  verification.
* PostgreSQL — run with ``DATABASE_URL=postgresql+psycopg://...`` and
  ``SKIP_SCHEMA_SETUP=1`` after ``alembic upgrade head``, which verifies the
  suite against the real migration rather than ``create_all``.

Isolation: every test gets a short-lived session and all rows are deleted
afterwards in foreign-key-safe order. An earlier revision wrapped each test in
an open transaction with savepoints; that is the usual SQLAlchemy recipe, but a
held-open transaction blocks other connections on serialized PostgreSQL
deployments, so explicit cleanup is used instead.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("SESSION_SECRET", "test-secret-0123456789abcdef0123456789abcdef0123456789")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("GOOGLE_DRIVE_ROOT_FOLDER_ID", "1gGcnYdfjX5PCWJP-gwwUwIFflHZlVqIW")
os.environ.setdefault("DATABASE_URL", "sqlite:///" + str(BACKEND_ROOT / ".test-portfolio.db"))

import pytest
from fastapi.testclient import TestClient

from app.config.database import (
    get_engine,
    get_session_factory,
    reset_engine,
)
from app.config.settings import get_settings
from app.main import create_app
from app.middleware.rate_limit import get_limiter
from app.models import Base


@pytest.fixture(scope="session", autouse=True)
def _database_schema():
    """Create the schema once per session, drop it at the end.

    ``SKIP_SCHEMA_SETUP=1`` runs the suite against a schema produced by
    ``alembic upgrade head`` instead of ``create_all``.
    """
    if os.environ.get("SKIP_SCHEMA_SETUP") == "1":
        yield
        return
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    reset_engine()


def _truncate_all() -> None:
    """Delete every row in dependency order so runs are repeatable."""
    session = get_session_factory()()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
    except Exception as exc:  # noqa: BLE001
        # Loud, never silent: a failed cleanup will otherwise show up later as a
        # confusing unique-constraint violation in an unrelated test.
        session.rollback()
        print(f"\n!! WARNING: test cleanup failed ({type(exc).__name__}: {exc})")
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _clean_state():
    get_limiter().reset()
    yield
    _truncate_all()
    get_limiter().reset()


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def db():
    """Short-lived session. Rows are removed by ``_clean_state`` afterwards."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
