"""SQLAlchemy models exercised against the configured database."""

from __future__ import annotations

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.models import (
    AdminSession,
    AuditLog,
    Certification,
    CertificationMedia,
    ContentStatus,
    ContentVersion,
    CVVersion,
    Experience,
    Media,
    MediaCategory,
    MediaType,
    Profile,
    Project,
    ProjectMedia,
    SiteSettings,
    Skill,
    SkillCategory,
    SocialLink,
    Tag,
    User,
    UserRole,
    Writeup,
    utcnow,
)


def _media(db, drive_id="drive-model-test"):
    media = Media(
        filename="test.png",
        original_filename="test.png",
        drive_file_id=drive_id,
        category=MediaCategory.PROJECT,
        mime_type="image/png",
        media_type=MediaType.IMAGE,
        size_bytes=1024,
        checksum="a" * 64,
    )
    db.add(media)
    db.commit()
    return media


def test_timestamps_are_timezone_aware(db):
    """Regression test: naive/aware mixing broke session expiry checks."""
    user = User(github_id=11_001, github_username="tz-check", role=UserRole.ADMIN)
    db.add(user)
    db.commit()
    fetched = db.get(User, user.id)
    assert fetched.created_at.tzinfo is not None
    assert fetched.updated_at.tzinfo is not None
    # Direct comparison must not raise.
    assert fetched.created_at <= utcnow()


def test_datetime_columns_are_timezone_aware_on_read(db):
    session = AdminSession(
        user_id=db.scalar(select(User).limit(1)).id
        if db.scalar(select(User).limit(1))
        else _ensure_user(db).id,
        session_token_hash="b" * 64,
        expires_at=utcnow(),
    )
    db.add(session)
    db.commit()
    fetched = db.get(AdminSession, session.id)
    assert fetched.expires_at.tzinfo is not None
    assert isinstance(fetched.is_expired, bool)


def _ensure_user(db):
    user = db.scalar(select(User).where(User.github_username == "session-owner"))
    if user is None:
        user = User(github_id=11_002, github_username="session-owner", role=UserRole.ADMIN)
        db.add(user)
        db.commit()
    return user


def test_project_persists_json_and_enum_columns(db):
    project = Project(
        title="WebSafeScan",
        slug="websafescan-model",
        technologies=["Bash", "Curl"],
        tools_used=["OpenSSL"],
        status=ContentStatus.PUBLISHED,
        cvss_score=6.1,
    )
    db.add(project)
    db.commit()
    fetched = db.get(Project, project.id)
    assert fetched.technologies == ["Bash", "Curl"]
    assert fetched.status is ContentStatus.PUBLISHED
    assert fetched.cvss_score == 6.1
    assert fetched.deleted_at is None
    assert fetched.is_deleted is False


def _engine_of(db):
    """The session may be bound to a Connection; reach the Engine through it."""
    bind = db.get_bind()
    return getattr(bind, "engine", bind)


def _constraint_error(db, statement: str) -> IntegrityError:
    """Execute ``statement`` on its own connection inside a SAVEPOINT.

    PGlite harness limitation, reproduced against PostgreSQL 18.3 / PGlite 0.5.8:
    when ``Session.commit()`` fails, SQLAlchemy issues an implicit ROLLBACK on
    that same connection. PGlite's wire server answers it with ``received 0
    results from command 'ROLLBACK'``, which psycopg surfaces as
    ``InternalError`` and which therefore *masks* the genuine constraint error.

    Issuing the statement on a dedicated connection behind an explicit SAVEPOINT
    keeps the transaction recoverable, so what is asserted below is the
    database's own ``IntegrityError``. This narrows the assertion - it never
    widens it to a generic exception, and the constraint that fired is checked by
    name so an unrelated error cannot pass.
    """
    connection = _engine_of(db).connect()
    try:
        connection.execute(text("SAVEPOINT constraint_probe"))
        with pytest.raises(IntegrityError) as excinfo:
            connection.execute(text(statement))
        connection.execute(text("ROLLBACK TO SAVEPOINT constraint_probe"))
        connection.execute(text("COMMIT"))
        return excinfo.value
    finally:
        connection.close()


def _is_unique_violation(error: IntegrityError) -> bool:
    """PostgreSQL raises UniqueViolation; SQLite reports it as IntegrityError text."""
    return (
        type(error.orig).__name__ == "UniqueViolation"
        or "UNIQUE CONSTRAINT FAILED" in str(error.orig).upper()
    )


def _is_check_violation(error: IntegrityError) -> bool:
    return (
        type(error.orig).__name__ == "CheckViolation"
        or "CHECK CONSTRAINT FAILED" in str(error.orig).upper()
    )


def test_project_slug_is_unique(db):
    """A duplicate projects.slug is rejected by the database, not just the ORM."""
    db.add(Project(title="Dup", slug="unique-slug-check"))
    db.commit()

    duplicate = (
        "INSERT INTO projects (title, slug, status, sort_order, featured, created_at, "
        "updated_at) VALUES ('Dup 2', 'unique-slug-check', 'DRAFT', 0, false, now(), now())"
        if _engine_of(db).dialect.name == "postgresql"
        else "INSERT INTO projects (title, slug, status, sort_order, featured, created_at, "
        "updated_at) VALUES ('Dup 2', 'unique-slug-check', 'DRAFT', 0, 0, "
        "'2026-01-01', '2026-01-01')"
    )

    error = _constraint_error(db, duplicate)
    assert _is_unique_violation(error), f"expected a unique violation, got {error.orig!r}"
    reported = str(error).lower()
    assert "ix_projects_slug" in reported or "projects.slug" in reported, str(error)

    # The original row survived and the duplicate never landed.
    remaining = db.scalar(
        select(func.count()).select_from(Project).where(Project.slug == "unique-slug-check")
    )
    assert remaining == 1, f"expected exactly 1 row, found {remaining}"


def test_invalid_enum_value_is_rejected_by_the_database(db):
    """The CHECK constraint exists in the DDL, not only in Python."""
    statement = (
        "INSERT INTO projects (title, slug, status, sort_order, featured, "
        "created_at, updated_at) VALUES ('x', 'bad-enum', 'NOT_A_STATUS', 0, "
        "false, now(), now())"
        if _engine_of(db).dialect.name == "postgresql"
        else "INSERT INTO projects (title, slug, status, sort_order, featured, "
        "created_at, updated_at) VALUES ('x', 'bad-enum', 'NOT_A_STATUS', 0, "
        "0, '2026-01-01', '2026-01-01')"
    )

    error = _constraint_error(db, statement)
    assert _is_check_violation(error), f"expected a check violation, got {error.orig!r}"
    assert "ck_projects_content_status" in str(error).lower(), str(error)


def test_soft_delete_is_cooperative(db):
    project = Project(title="Archive me", slug="archive-me", status=ContentStatus.PUBLISHED)
    db.add(project)
    db.commit()
    project.deleted_at = utcnow()
    db.commit()
    fetched = db.get(Project, project.id)
    assert fetched.is_deleted is True
    assert db.scalar(select(Project).where(Project.deleted_at.is_(None), Project.id == project.id)) is None


def test_project_media_cascade(db):
    project = Project(title="Media host", slug="media-host")
    media = _media(db, drive_id="drive-cascade")
    db.add(project)
    db.flush()
    db.add(
        ProjectMedia(
            project_id=project.id,
            media_id=media.id,
            media_type=MediaType.IMAGE,
            caption="Shot",
            is_featured=True,
        )
    )
    db.commit()
    project_id = project.id
    db.delete(project)
    db.commit()
    assert (
        db.scalar(select(ProjectMedia).where(ProjectMedia.project_id == project_id)) is None
    )


def test_tags_many_to_many(db):
    tag = Tag(name="owasp")
    project = Project(title="Tagged", slug="tagged-project")
    db.add_all([tag, project])
    db.flush()
    project.tags = [tag]
    db.commit()
    fetched = db.scalar(select(Project).where(Project.slug == "tagged-project"))
    assert [t.name for t in fetched.tags] == ["owasp"]


def test_profile_and_social_links(db):
    profile = Profile(id=1, name="Muhammed Fasal", location="Kerala, India")
    db.add(profile)
    db.flush()
    db.add(
        SocialLink(
            profile_id=1, platform="github", label="GitHub", url="https://github.com/Fasal17"
        )
    )
    db.commit()
    fetched = db.get(Profile, 1)
    assert fetched.name == "Muhammed Fasal"
    assert fetched.social_links[0].platform == "github"


def test_certification_experience_skill_writeup_rows(db):
    media = _media(db, drive_id="drive-cert")
    certification = Certification(title="CCST", issuer="Cisco", status=ContentStatus.PUBLISHED)
    db.add(certification)
    db.flush()
    db.add(CertificationMedia(certification_id=certification.id, media_id=media.id))
    db.add(Experience(company="Encrypt Bytes Labs", role="Researcher Intern"))
    category = SkillCategory(name="Tools")
    db.add(category)
    db.flush()
    db.add(Skill(category_id=category.id, name="Burp Suite"))
    db.add(Writeup(title="XSS write-up", slug="xss-writeup", content="body"))
    db.commit()

    assert db.scalar(select(Certification).where(Certification.title == "CCST")) is not None
    assert db.scalar(select(Experience)).company == "Encrypt Bytes Labs"
    assert db.scalar(select(Skill)).name == "Burp Suite"
    assert db.scalar(select(Writeup)).slug == "xss-writeup"
    assert certification.primary_image is not None


def test_cv_version_current_flag(db):
    media = _media(db, drive_id="drive-cv")
    version = CVVersion(media_id=media.id, version_name="CV v1", version_number=1, is_current=True)
    db.add(version)
    db.commit()
    payload = db.get(CVVersion, version.id).public_payload()
    assert set(payload) == {
        "name",
        "version",
        "updated_at",
        "download_url",
        "view_url",
        "size_bytes",
        "mime_type",
    }


def test_site_settings_feature_flags_roundtrip(db):
    settings_row = SiteSettings(id=1, portfolio_title="Title", feature_flags={"show_writeups": True})
    db.add(settings_row)
    db.commit()
    assert db.get(SiteSettings, 1).public_payload()["feature_flags"] == {"show_writeups": True}


def test_audit_log_stores_redacted_json_metadata(db):
    from app.utils.security import redact_secrets

    entry = AuditLog(
        action="TEST_ACTION",
        resource_type="project",
        resource_id="1",
        metadata_=redact_secrets({"access_token": "abc", "safe": 1}),
    )
    db.add(entry)
    db.commit()
    fetched = db.get(AuditLog, entry.id)
    assert fetched.metadata_["access_token"] == "***redacted***"
    assert fetched.metadata_["safe"] == 1


def test_content_version_history(db):
    first = ContentVersion(
        resource_type="project", resource_id=999, version_number=1, snapshot={"title": "v1"}
    )
    second = ContentVersion(
        resource_type="project", resource_id=999, version_number=2, snapshot={"title": "v2"}
    )
    db.add_all([first, second])
    db.commit()
    rows = db.scalars(
        select(ContentVersion)
        .where(ContentVersion.resource_id == 999)
        .order_by(ContentVersion.version_number.desc())
    ).all()
    assert [row.version_number for row in rows] == [2, 1]
    assert rows[0].snapshot["title"] == "v2"


def test_media_public_payload_hides_restricted_urls(db):
    from app.models import AccessPolicy

    media = _media(db, drive_id="drive-restricted")
    media.drive_url = "https://drive.example/private"
    media.access_policy = AccessPolicy.RESTRICTED
    db.commit()
    assert db.get(Media, media.id).public_payload()["url"] is None

    media.access_policy = AccessPolicy.PUBLIC
    db.commit()
    assert db.get(Media, media.id).public_payload()["url"] == "https://drive.example/private"


def test_all_tables_have_primary_keys(db):
    inspector = inspect(db.bind)
    for table in inspector.get_table_names():
        if table == "alembic_version":
            continue
        assert inspector.get_pk_constraint(table)["constrained_columns"], table
