"""Configuration: environment-driven, validated, no hardcoded secrets."""

from __future__ import annotations

import pytest

from app.config.settings import Settings

TEST_DB = "sqlite:///./test.db"


def test_drive_root_folder_comes_from_environment(monkeypatch):
    monkeypatch.setenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", "folder-from-environment")
    settings = Settings(_env_file=None, database_url=TEST_DB, session_secret="x" * 40)
    assert settings.google_drive_root_folder_id == "folder-from-environment"


def test_drive_root_folder_is_not_hardcoded():
    """The literal Portfolio CMS folder id must never appear in the source."""
    import pathlib

    literal = "1gGcnYdfjX5PCWJP-gwwUwIFflHZlVqIW"
    offenders = []
    for path in pathlib.Path("app").rglob("*.py"):
        if literal in path.read_text(encoding="utf-8"):
            offenders.append(str(path))
    assert offenders == []


def test_production_requires_session_secret(monkeypatch):
    # conftest exports SESSION_SECRET; remove it so the check is actually exercised.
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with pytest.raises(ValueError, match="SESSION_SECRET"):
        Settings(_env_file=None, environment="production", database_url=TEST_DB)


def test_production_requires_secure_cookie():
    with pytest.raises(ValueError, match="COOKIE_SECURE"):
        Settings(
            _env_file=None,
            environment="production",
            database_url=TEST_DB,
            session_secret="s" * 40,
            cookie_secure=False,
            github_client_id="id",
            github_client_secret="secret",
        )


def test_production_requires_github_credentials():
    with pytest.raises(ValueError, match="GitHub OAuth"):
        Settings(
            _env_file=None,
            environment="production",
            database_url=TEST_DB,
            session_secret="s" * 40,
            cookie_secure=True,
        )


def test_short_session_secret_is_rejected():
    with pytest.raises(ValueError, match="at least 32"):
        Settings(_env_file=None, database_url=TEST_DB, session_secret="short")


def test_development_generates_an_ephemeral_secret():
    settings = Settings(_env_file=None, environment="development", database_url=TEST_DB)
    assert len(settings.session_secret) >= 32


def test_allowed_administrator_list_is_case_insensitive():
    settings = Settings(
        _env_file=None,
        database_url=TEST_DB,
        session_secret="s" * 40,
        allowed_github_username="Fasal17, SomeoneElse",
    )
    assert settings.allowed_github_usernames == {"fasal17", "someoneelse"}


def test_cors_origins_never_contain_wildcard():
    settings = Settings(_env_file=None, database_url=TEST_DB, session_secret="s" * 40)
    assert "*" not in settings.cors_origins


def test_private_key_newlines_are_decoded():
    settings = Settings(
        _env_file=None,
        database_url=TEST_DB,
        session_secret="s" * 40,
        google_private_key="-----BEGIN KEY-----\\nline\\n-----END KEY-----",
    )
    assert "\n" in settings.google_private_key


def test_google_drive_configured_requires_credentials():
    settings = Settings(
        _env_file=None,
        database_url=TEST_DB,
        session_secret="s" * 40,
        google_drive_root_folder_id="root",
    )
    assert settings.google_drive_configured is False
