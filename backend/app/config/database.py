"""SQLAlchemy engine / session wiring.

The ORM is the only supported path to the database: every query in this project
is either an ORM expression or a Core construct with bound parameters, so user
input never reaches the database as raw SQL text.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings
from app.models.base import Base

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def _engine_kwargs(settings) -> dict[str, Any]:
    url = settings.database_url
    kwargs: dict[str, Any] = {"future": True}
    if url.startswith("postgresql"):
        mode = settings.database_pool_class
        if mode == "auto":
            # Historically: no pooling while testing, so a failed transaction
            # cannot leave a connection in a state that breaks later tests.
            mode = "null" if settings.environment == "testing" else "queue"
        if mode == "static":
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
            kwargs["pool_pre_ping"] = True
        elif mode == "null":
            from sqlalchemy.pool import NullPool

            kwargs["poolclass"] = NullPool
        else:
            kwargs.update(
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_pre_ping=True,
            )
    elif url.startswith("sqlite"):
        # SQLite (tests / local exploration) needs the same-thread check relaxed
        # because FastAPI serves requests from a thread pool.
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    """SQLite ignores foreign keys unless asked, which hides cascade bugs.

    Enabling them makes a SQLite test run behave like PostgreSQL for ON DELETE
    rules. It does NOT make SQLite a substitute for PostgreSQL verification.
    """
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, _record):  # pragma: no cover - driver callback
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.database_url, **_engine_kwargs(settings))
        if settings.database_url.startswith("sqlite"):
            _enable_sqlite_foreign_keys(_engine)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionFactory


def reset_engine() -> None:
    """Dispose the pooled engine (used when tests point at a new database)."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a scoped session and always closes it."""
    session = get_session_factory()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def database_is_reachable() -> bool:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - health checks must never raise
        return False


__all__ = [
    "Base",
    "database_is_reachable",
    "get_db",
    "get_engine",
    "get_session_factory",
    "reset_engine",
]
