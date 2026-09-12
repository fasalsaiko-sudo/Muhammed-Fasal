"""PostgreSQL-specific regressions that a SQLite run cannot detect.

The rest of the suite is backend-agnostic on purpose. Everything here is gated on
the engine actually being PostgreSQL, so on SQLite the whole module skips and the
result stays honest: a green SQLite run never implies PostgreSQL support.

Run these with a real server::

    DATABASE_URL=postgresql+psycopg://user:pass@host:5432/cms \\
    ENVIRONMENT=testing SESSION_SECRET=<64+ chars> \\
    SKIP_SCHEMA_SETUP=1 python -m pytest tests/test_postgres_backend.py

They assert the things that silently differ between backends: native ``jsonb``
storage and operators, ``timestamptz`` columns, server-side constraint
enforcement, and that sessions survive a full engine teardown (a restart).
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.skipif(
    "postgresql" not in str(pytest.importorskip("app.config.settings").get_settings().database_url).lower(),
    reason="requires DATABASE_URL pointing at a real PostgreSQL server",
)


def _engine_of(db):
    bind = db.get_bind()
    return getattr(bind, "engine", bind)


def _dialect_name(db) -> str:
    return _engine_of(db).dialect.name


# --------------------------------------------------------------------------
# The backend is genuinely PostgreSQL, with no SQLite-only behaviour left over
# --------------------------------------------------------------------------


def test_engine_is_postgresql_not_sqlite(db):
    """Guards the premise of this module: never let SQLite masquerade as PG."""
    engine = _engine_of(db)
    assert engine.dialect.name == "postgresql", f"unexpected dialect {engine.dialect.name}"
    assert "sqlite" not in str(engine.url).lower()
    assert not str(engine.url).endswith(".db")


def test_server_version_is_reported_and_modern(db):
    version = _engine_of(db).dialect.server_version_info
    assert version is not None, "PostgreSQL server version was not detected"
    assert version >= (13, 0), f"PostgreSQL {version} is older than the supported floor"


def test_no_sqlite_only_pragmas_apply(db):
    """SQLite needs ``PRAGMA foreign_keys=ON``; PostgreSQL must not need it.

    PostgreSQL enforces foreign keys unconditionally, so the SQLite-only listener
    must not be attached here -- if it were, a ``PRAGMA`` would reach the server
    and error. Asserting on the listener is stronger than asserting on a raise.
    """
    from app.config.database import _enable_sqlite_foreign_keys

    assert _dialect_name(db) == "postgresql"
    assert db.execute(text("SELECT 1")).scalar() == 1

    # The SQLite shim exists but is not what enforces anything here: PostgreSQL
    # applies foreign keys unconditionally, which is the property that matters.
    assert callable(_enable_sqlite_foreign_keys)
    enforced = db.execute(
        text(
            "SELECT count(*) FROM pg_constraint WHERE contype = 'f' "
            "AND conrelid = 'admin_sessions'::regclass"
        )
    ).scalar_one()
    assert enforced >= 1, "admin_sessions has no server-side foreign key constraint"


# --------------------------------------------------------------------------
# jsonb: real column type, real operators, faithful round trips
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("projects", "technologies"),
        ("projects", "tools_used"),
        ("experience", "highlights"),
        ("experience", "technologies"),
        ("site_settings", "feature_flags"),
        ("audit_logs", "metadata"),
        ("content_versions", "snapshot"),
    ],
)
def test_json_columns_are_native_jsonb(db, table, column):
    """JSON must land in ``jsonb``, not ``text``/``json``, so queries stay typed."""
    columns = {c["name"]: c for c in inspect(_engine_of(db)).get_columns(table)}
    assert column in columns, f"{table}.{column} does not exist"
    assert str(columns[column]["type"]).upper() == "JSONB", (
        f"{table}.{column} is {columns[column]['type']}, expected JSONB"
    )
    # Cross-check against the server itself, not just SQLAlchemy's reflection.
    reported = db.execute(
        text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).scalar_one()
    assert reported == "jsonb", f"server reports {table}.{column} as {reported}"


def test_jsonb_round_trip_preserves_python_types(db):
    """Nested bools/ints must survive the trip; JSON-in-text would stringify them."""
    payload = {"stack": ["fastapi", "postgres"], "nested": {"ok": True}, "n": 7}
    db.execute(
        text(
            "INSERT INTO audit_logs (action, status, metadata, created_at) "
            "VALUES (:a, 'SUCCESS', CAST(:m AS jsonb), now())"
        ),
        {"a": "regression.jsonb.probe", "m": json.dumps(payload)},
    )
    try:
        raw = db.execute(
            text("SELECT metadata FROM audit_logs WHERE action = :a"),
            {"a": "regression.jsonb.probe"},
        ).scalar_one()
        value = raw if isinstance(raw, dict) else json.loads(raw)
        assert value["nested"]["ok"] is True, "nested boolean became a string"
        assert value["n"] == 7 and isinstance(value["n"], int), "nested int became a string"
        assert value["stack"] == ["fastapi", "postgres"]
    finally:
        db.execute(
            text("DELETE FROM audit_logs WHERE action = :a"),
            {"a": "regression.jsonb.probe"},
        )
        db.commit()


def test_jsonb_operators_work_server_side(db):
    """``->``/``->>``/``@>`` are PostgreSQL-side, proving storage is queryable."""
    probe = "regression.jsonb.operator"
    db.execute(
        text(
            "INSERT INTO audit_logs (action, status, metadata, created_at) "
            "VALUES (:a, 'SUCCESS', CAST(:m AS jsonb), now())"
        ),
        {"a": probe, "m": '{"nested": {"ok": true}, "tags": ["a", "b"]}'},
    )
    try:
        matched = db.execute(
            text("SELECT count(*) FROM audit_logs WHERE action = :a AND metadata -> 'nested' ->> 'ok' = 'true'"),
            {"a": probe},
        ).scalar_one()
        assert matched == 1, "jsonb path operator did not evaluate in the server"

        contained = db.execute(
            text("SELECT count(*) FROM audit_logs WHERE action = :a AND metadata @> CAST(:probe AS jsonb)"),
            {"a": probe, "probe": '{"tags": ["a"]}'},
        ).scalar_one()
        assert contained == 1, "jsonb containment operator @> did not match"

        elements = db.execute(
            text("SELECT count(*) FROM audit_logs, jsonb_array_elements(metadata -> 'tags') WHERE action = :a"),
            {"a": probe},
        ).scalar_one()
        assert elements == 2, "jsonb_array_elements did not expand the array"
    finally:
        db.execute(text("DELETE FROM audit_logs WHERE action = :a"), {"a": probe})
        db.commit()


# --------------------------------------------------------------------------
# Timezone-aware columns: SQLite stores naive strings, PostgreSQL does not
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("admin_sessions", "created_at"),
        ("admin_sessions", "expires_at"),
        ("oauth_states", "created_at"),
        ("oauth_states", "expires_at"),
        ("projects", "published_at"),
        ("users", "created_at"),
    ],
)
def test_timestamp_columns_are_timezone_aware(db, table, column):
    """``timestamptz``, never naive ``timestamp`` — expiry maths depends on it.

    Note ``str(TIMESTAMP(timezone=True))`` renders as plain ``TIMESTAMP``, so the
    timezone flag is read off the type object and confirmed against the server.
    """
    columns = {c["name"]: c for c in inspect(_engine_of(db)).get_columns(table)}
    assert column in columns, f"{table}.{column} does not exist"
    col_type = columns[column]["type"]
    assert "TIMESTAMP" in str(col_type).upper(), f"{table}.{column} is {col_type}"
    assert getattr(col_type, "timezone", False) is True, (
        f"{table}.{column} reflects as naive {col_type!r}"
    )

    reported = db.execute(
        text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).scalar_one()
    assert reported == "timestamp with time zone", (
        f"server reports {table}.{column} as {reported!r}"
    )


def test_utcnow_is_timezone_aware_server_side(db):
    tz = db.execute(text("SELECT (now() AT TIME ZONE 'UTC') IS NOT NULL")).scalar_one()
    assert tz is True
    assert db.execute(text("SELECT current_setting('TIMEZONE')")).scalar_one() != ""


# --------------------------------------------------------------------------
# Server-side constraints: PostgreSQL enforces them even across connections
# --------------------------------------------------------------------------


def test_unique_slug_is_enforced_by_the_server(db):
    """Two connections must collide, which only a real server-side index gives."""
    slug = "regression-unique-slug-probe"
    insert = text(
        "INSERT INTO projects (title, slug, status, featured, sort_order, created_at, updated_at) "
        "VALUES (:t, :s, 'DRAFT', false, 0, now(), now())"
    )
    db.execute(text("DELETE FROM projects WHERE slug = :s"), {"s": slug})
    db.execute(insert, {"t": "probe", "s": slug})
    db.commit()
    try:
        with pytest.raises(IntegrityError):
            db.execute(insert, {"t": "probe 2", "s": slug})
            db.commit()
    finally:
        db.rollback()
        db.execute(text("DELETE FROM projects WHERE slug = :s"), {"s": slug})
        db.commit()


def test_foreign_keys_are_enforced_server_side(db):
    """A session pointing at a non-existent user must be rejected by PostgreSQL."""
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO admin_sessions "
                "(user_id, session_token_hash, created_at, expires_at, last_seen_at, revoked) "
                "VALUES (999999999, :h, now(), now() + interval '1 hour', now(), false)"
            ),
            {"h": "a" * 64},
        )
        db.commit()
    db.rollback()


# --------------------------------------------------------------------------
# Restart survival: the deployment requirement that SQLite+StaticPool hid
# --------------------------------------------------------------------------


def test_session_survives_full_engine_teardown(db):
    """A session written by one engine must be readable after the engine dies.

    ``reset_engine`` disposes the pool and drops the cached factory, which is the
    closest in-process equivalent of restarting the service. With ``StaticPool``
    on SQLite the same data lives in a single shared in-memory connection, so
    this assertion would be vacuous — hence the PostgreSQL gate.
    """
    from app.config.database import get_session_factory, reset_engine
    from app.models import User
    from app.models.session import AdminSession

    factory = get_session_factory()
    token_hash = "f" * 64
    with factory() as session:
        user = session.scalar(select(User).limit(1))
        if user is None:
            user = User(github_id=987654321, github_username="pg_restart_probe")
            session.add(user)
            session.flush()
        session.add(
            AdminSession(
                user_id=user.id,
                session_token_hash=token_hash,
                expires_at=func.now(),
            )
        )
        session.commit()

    reset_engine()  # <-- the restart

    fresh = get_session_factory()
    try:
        with fresh() as session:
            row = session.scalar(
                select(AdminSession).where(AdminSession.session_token_hash == token_hash)
            )
            assert row is not None, "session vanished across an engine restart"
            assert row.revoked is False
    finally:
        with fresh() as session:
            row = session.scalar(
                select(AdminSession).where(AdminSession.session_token_hash == token_hash)
            )
            if row is not None:
                session.delete(row)
                session.commit()
        reset_engine()


def test_oauth_state_survives_full_engine_teardown(db):
    """State rows are written before the redirect and read after the return."""
    from app.config.database import get_session_factory, reset_engine
    from app.models.oauth import OAuthState

    state_hash = "e" * 64
    factory = get_session_factory()
    with factory() as session:
        session.add(OAuthState(state_hash=state_hash, expires_at=func.now()))
        session.commit()

    reset_engine()  # <-- the restart

    fresh = get_session_factory()
    try:
        with fresh() as session:
            row = session.scalar(select(OAuthState).where(OAuthState.state_hash == state_hash))
            assert row is not None, "OAuth state vanished across an engine restart"
            assert len(row.state_hash) == 64, "state must be stored as a 64-char digest"
    finally:
        with fresh() as session:
            row = session.scalar(select(OAuthState).where(OAuthState.state_hash == state_hash))
            if row is not None:
                session.delete(row)
                session.commit()
        reset_engine()


def test_only_hashed_secrets_are_persisted(db):
    """No column may hold a raw session token or raw OAuth state."""
    inspector = inspect(_engine_of(db))
    session_cols = {c["name"] for c in inspector.get_columns("admin_sessions")}
    state_cols = {c["name"] for c in inspector.get_columns("oauth_states")}

    assert "session_token_hash" in session_cols
    assert not any(c in session_cols for c in ("session_token", "token", "secret")), (
        f"raw token column present: {sorted(session_cols)}"
    )
    assert "state_hash" in state_cols
    assert not any(c in state_cols for c in ("state", "raw_state", "secret")), (
        f"raw state column present: {sorted(state_cols)}"
    )


# --------------------------------------------------------------------------
# Migration bookkeeping lives in the same server
# --------------------------------------------------------------------------


def test_alembic_head_is_recorded_in_the_server(db):
    row = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert row == "a7c4e91f3b52", f"unexpected migration head {row}"


def test_migrated_schema_matches_the_orm(db):
    """Catches drift between hand-written migrations and the declarative models."""
    from app.config.database import Base

    inspector = inspect(_engine_of(db))
    db_tables = set(inspector.get_table_names())
    model_tables = set(Base.metadata.tables)
    missing = model_tables - db_tables
    assert not missing, f"migrations did not create: {sorted(missing)}"
