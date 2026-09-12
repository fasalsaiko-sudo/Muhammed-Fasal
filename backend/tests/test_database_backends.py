"""Records which database backend the suite actually ran against.

A green SQLite run is NOT PostgreSQL verification. These tests print the engine
so the result is never ambiguous, and assert the Phase 3 table list exists.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

REQUIRED_TABLES = {
    "users",
    "admin_sessions",
    "profile",
    "social_links",
    "projects",
    "project_media",
    "project_tags",
    "tags",
    "certifications",
    "certification_media",
    "experience",
    "skill_categories",
    "skills",
    "writeups",
    "writeup_media",
    "writeup_tags",
    "media",
    "cv_versions",
    "site_settings",
    "audit_logs",
    "content_versions",
}


def _engine_of(db):
    """The ``db`` fixture binds to a Connection; reach the Engine through it."""
    bind = db.get_bind()
    return getattr(bind, "engine", bind)


def test_report_database_backend(db):
    engine = _engine_of(db)
    print(f"\nDATABASE UNDER TEST: {engine.dialect.name} -> {engine.url}")
    print(f"SERVER VERSION     : {engine.dialect.server_version_info}")
    assert engine.dialect.name in {"postgresql", "sqlite"}


def test_all_required_tables_exist(db):
    present = set(inspect(db.bind).get_table_names())
    missing = REQUIRED_TABLES - present
    assert not missing, f"Missing tables: {sorted(missing)}"


def test_json_columns_are_native_json(db):
    """JSON must be a real JSON type, not TEXT, so queries stay typed."""
    inspector = inspect(_engine_of(db))
    column = {c["name"]: c for c in inspector.get_columns("projects")}["technologies"]
    assert "JSON" in str(column["type"]).upper()


@pytest.mark.parametrize("table", sorted(REQUIRED_TABLES))
def test_table_is_queryable(db, table):
    from sqlalchemy import text

    db.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
