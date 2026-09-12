"""Public portfolio API (spec §25, §38, §44).

These tests are the enforcement point for the rule that anonymous visitors see
published content only, and never see admin users, sessions, audit data, Drive
internals or draft rows.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import (
    Certification,
    ContentStatus,
    CVVersion,
    Experience,
    Media,
    MediaCategory,
    MediaType,
    Profile,
    Project,
    SiteSettings,
    Skill,
    SkillCategory,
    SocialLink,
    Writeup,
    utcnow,
)
from app.models.enums import AccessPolicy
from app.services import portfolio_service
from app.utils.cache import get_cache

# Fields that must never appear anywhere in a public response.
FORBIDDEN_KEYS = {
    "session_token",
    "session_token_hash",
    "github_id",
    "ip_address",
    "user_agent",
    "revoked",
    "action",
    "resource_type",
    "resource_id",
    "drive_file_id",
    "drive_folder_id",
    "checksum",
    "deleted_at",
    "password",
    "private_key",
    "client_secret",
    "access_token",
}


def _media(db, *, filename="shot.png", drive_id="drive-public-1", policy=AccessPolicy.PUBLIC):
    media = Media(
        filename=filename,
        original_filename=filename,
        drive_file_id=drive_id,
        category=MediaCategory.PROJECT,
        mime_type="image/png",
        media_type=MediaType.IMAGE,
        size_bytes=2048,
        checksum="c" * 64,
        access_policy=policy,
        drive_url=f"https://drive.example/{drive_id}",
        thumbnail_url=f"https://drive.example/{drive_id}/thumb",
        download_url=f"https://drive.example/{drive_id}/download",
    )
    db.add(media)
    db.commit()
    return media


def _walk_keys(node, found: set[str]) -> None:
    if isinstance(node, dict):
        found.update(node.keys())
        for value in node.values():
            _walk_keys(value, found)
    elif isinstance(node, list):
        for item in node:
            _walk_keys(item, found)


def _collect_keys(client) -> set[str]:
    found: set[str] = set()
    for path in (
        "/api/profile",
        "/api/projects",
        "/api/certifications",
        "/api/experience",
        "/api/skills",
        "/api/writeups",
        "/api/cv",
        "/api/settings/public",
    ):
        response = client.get(path)
        if response.status_code == 200:
            _walk_keys(response.json(), found)
    return found


# ------------------------------------------------------------------- projects
def test_published_project_is_returned(client, db):
    db.add(Project(title="WebSafeScan", slug="websafescan", status=ContentStatus.PUBLISHED,
                   technologies=["Bash"], featured=True))
    db.commit()

    response = client.get("/api/projects")
    assert response.status_code == 200
    payload = response.json()
    assert [p["slug"] for p in payload] == ["websafescan"]
    assert payload[0]["title"] == "WebSafeScan"
    assert payload[0]["technologies"] == ["Bash"]
    assert payload[0]["featured"] is True


@pytest.mark.parametrize(
    "status,expect_hidden",
    [(ContentStatus.DRAFT, True), (ContentStatus.ARCHIVED, True), (ContentStatus.PUBLISHED, False)],
)
def test_only_published_projects_are_public(client, db, status, expect_hidden):
    db.add(Project(title="Filtered", slug=f"filtered-{status.value.lower()}", status=status))
    db.commit()

    listed = client.get("/api/projects").json()
    assert (len(listed) == 0) is expect_hidden

    detail = client.get(f"/api/projects/filtered-{status.value.lower()}")
    assert (detail.status_code == 404) is expect_hidden


def test_soft_deleted_project_is_hidden(client, db):
    project = Project(title="Gone", slug="gone", status=ContentStatus.PUBLISHED)
    db.add(project)
    db.commit()
    project.deleted_at = utcnow()
    db.commit()

    assert client.get("/api/projects").json() == []
    assert client.get("/api/projects/gone").status_code == 404


def test_draft_slug_404_does_not_reveal_that_the_row_exists(client, db):
    """A draft and a non-existent slug must be indistinguishable to a visitor."""
    db.add(Project(title="Secret", slug="secret-draft", status=ContentStatus.DRAFT))
    db.commit()

    draft = client.get("/api/projects/secret-draft")
    missing = client.get("/api/projects/never-existed")
    assert draft.status_code == missing.status_code == 404
    assert draft.json() == missing.json()
    assert "secret-draft" not in draft.text


def test_unknown_project_returns_404(client):
    assert client.get("/api/projects/nope").status_code == 404


# -------------------------------------------------------------------- profile
def test_profile_returns_only_public_fields(client, db):
    profile = Profile(id=1, name="Muhammed Fasal", headline="Security Researcher",
                      location="Kerala", email="public@example.com")
    db.add(profile)
    db.add(SocialLink(profile_id=1, platform="github", label="GitHub",
                      url="https://github.com/Fasal17", enabled=True, sort_order=1))
    db.add(SocialLink(profile_id=1, platform="hidden", label="Hidden",
                      url="https://example.com/private", enabled=False, sort_order=2))
    db.commit()

    response = client.get("/api/profile")
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Muhammed Fasal"
    assert [link["platform"] for link in payload["social_links"]] == ["github"]
    assert "id" not in payload
    assert "created_at" not in payload


def test_profile_missing_returns_404(client):
    assert client.get("/api/profile").status_code == 404


# --------------------------------------------------------------- media privacy
def test_restricted_media_never_exposes_direct_urls(client, db):
    restricted = _media(db, filename="cert.pdf", drive_id="drive-restricted",
                        policy=AccessPolicy.RESTRICTED)
    published = _media(db, filename="cover.png", drive_id="drive-public",
                       policy=AccessPolicy.PUBLIC)
    project = Project(title="Media host", slug="media-host", status=ContentStatus.PUBLISHED)
    db.add(project)
    db.commit()
    from app.models.project import ProjectMedia

    db.add_all(
        [
            ProjectMedia(project_id=project.id, media_id=published.id,
                         media_type=MediaType.IMAGE, is_featured=True, sort_order=0),
            ProjectMedia(project_id=project.id, media_id=restricted.id,
                         media_type=MediaType.PDF, sort_order=1),
        ]
    )
    db.commit()

    payload = client.get("/api/projects/media-host").json()
    by_id = {item["id"]: item for item in payload["media"]}
    assert by_id[published.id]["url"] == "https://drive.example/drive-public"
    restricted_item = by_id[restricted.id]
    assert restricted_item["url"] is None
    assert restricted_item["thumbnail_url"] is None
    assert restricted_item["download_url"] is None


# --------------------------------------------------------------- other modules
def test_certifications_only_published(client, db):
    db.add(Certification(title="Live", issuer="TryHackMe", status=ContentStatus.PUBLISHED))
    db.add(Certification(title="Draft cert", issuer="TryHackMe", status=ContentStatus.DRAFT))
    db.commit()
    titles = [row["title"] for row in client.get("/api/certifications").json()]
    assert titles == ["Live"]


def test_invisible_experience_is_hidden(client, db):
    db.add(Experience(company="Visible Co", role="Security Analyst", visible=True))
    db.add(Experience(company="Hidden Co", role="Contractor", visible=False))
    db.commit()
    companies = [row["company"] for row in client.get("/api/experience").json()]
    assert companies == ["Visible Co"]


def test_skills_are_grouped_by_category(client, db):
    category = SkillCategory(name="Web Security")
    db.add(category)
    db.commit()
    db.add(Skill(name="Burp Suite", level="EXPERT", category_id=category.id))
    db.commit()

    payload = client.get("/api/skills").json()
    assert payload[0]["name"] == "Web Security"
    assert payload[0]["skills"][0]["name"] == "Burp Suite"
    assert payload[0]["skills"][0]["level"] == "EXPERT"


def test_writeups_only_published_and_limit_is_enforced(client, db):
    for index in range(5):
        db.add(Writeup(title=f"Write-up {index}", slug=f"writeup-{index}",
                       status=ContentStatus.PUBLISHED, content="body"))
    db.add(Writeup(title="Draft write-up", slug="writeup-draft",
                   status=ContentStatus.DRAFT, content="body"))
    db.commit()

    payload = client.get("/api/writeups").json()
    assert len(payload) == 5
    assert all("writeup-draft" != row["slug"] for row in payload)

    assert len(client.get("/api/writeups", params={"limit": 2}).json()) == 2
    # Out-of-range limit is a validation error, not a silent clamp.
    assert client.get("/api/writeups", params={"limit": 999}).status_code == 422
    assert client.get("/api/writeups", params={"limit": 0}).status_code == 422


def test_writeup_detail_is_404_for_drafts(client, db):
    db.add(Writeup(title="Unpublished", slug="unpublished", status=ContentStatus.DRAFT,
                   content="secret findings"))
    db.commit()
    response = client.get("/api/writeups/unpublished")
    assert response.status_code == 404
    assert "secret findings" not in response.text


# ------------------------------------------------------------------------- CV
def test_current_cv_is_public_without_authentication(client, db):
    media = _media(db, filename="muhammed-fasal-cv.pdf", drive_id="drive-cv")
    db.add(CVVersion(media_id=media.id, version_name="2026-Q3", version_number=3,
                     is_current=True))
    db.commit()

    response = client.get("/api/cv")
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "muhammed-fasal-cv.pdf"
    assert payload["version"] == "2026-Q3"
    assert payload["download_url"] == "https://drive.example/drive-cv/download"


def test_archived_or_non_current_cv_is_not_public(client, db):
    media = _media(db, filename="old-cv.pdf", drive_id="drive-old-cv")
    db.add(CVVersion(media_id=media.id, version_name="2025", version_number=1,
                     is_current=True, archived=True))
    db.commit()
    assert client.get("/api/cv").status_code == 404


# ------------------------------------------------------------------- settings
def test_public_settings_expose_only_public_keys(client, db):
    db.add(SiteSettings(id=1, portfolio_title="Muhammed Fasal", seo_description="desc",
                        theme="dark", feature_flags={"show_writeups": True}))
    db.commit()

    response = client.get("/api/settings/public")
    assert response.status_code == 200
    payload = response.json()
    assert payload["portfolio_title"] == "Muhammed Fasal"
    assert payload["theme"] == "dark"
    assert payload["feature_flags"] == {"show_writeups": True}


def test_public_settings_default_to_empty_object_when_unconfigured(client):
    response = client.get("/api/settings/public")
    assert response.status_code == 200
    assert response.json() == {} or set(response.json()) <= {
        "portfolio_title", "seo_description", "keywords", "og_title", "og_description",
        "og_image_url", "canonical_url", "contact_email", "availability_status",
        "footer_text", "theme", "feature_flags",
    }


# --------------------------------------------------- leakage across all routes
def test_no_public_endpoint_leaks_admin_or_drive_internals(client, db):
    media = _media(db)
    db.add(Profile(id=1, name="Owner"))
    db.add(Project(title="P", slug="p", status=ContentStatus.PUBLISHED))
    db.add(CVVersion(media_id=media.id, version_name="v1", version_number=1, is_current=True))
    db.add(SiteSettings(id=1, portfolio_title="Site"))
    db.commit()

    leaked = _collect_keys(client) & FORBIDDEN_KEYS
    assert not leaked, f"public API leaked internal keys: {sorted(leaked)}"


# --------------------------------------------------------------------- caching
def test_public_reads_are_cached_and_invalidated(client, db):
    db.add(Project(title="Cached", slug="cached", status=ContentStatus.PUBLISHED))
    db.commit()
    assert len(client.get("/api/projects").json()) == 1

    # A new row is invisible until the cache is invalidated, proving the read is
    # served from cache rather than the database.
    db.add(Project(title="Fresh", slug="fresh", status=ContentStatus.PUBLISHED))
    db.commit()
    assert len(client.get("/api/projects").json()) == 1

    portfolio_service.invalidate("projects")
    slugs = [row["slug"] for row in client.get("/api/projects").json()]
    assert sorted(slugs) == ["cached", "fresh"]


def test_cache_ttl_zero_disables_caching(client, db, settings, monkeypatch):
    monkeypatch.setattr(settings, "public_cache_ttl_seconds", 0)
    from app.utils.cache import reset_cache

    reset_cache()
    db.add(Project(title="Uncached", slug="uncached", status=ContentStatus.PUBLISHED))
    db.commit()
    assert len(client.get("/api/projects").json()) == 1
    db.add(Project(title="Also uncached", slug="also-uncached", status=ContentStatus.PUBLISHED))
    db.commit()
    # With TTL 0 nothing is stored, so the second read sees both rows.
    assert len(client.get("/api/projects").json()) == 2
    assert len(get_cache()) == 0


def test_openapi_documents_every_public_endpoint(client):
    paths = client.get("/openapi.json").json()["paths"]
    for expected in (
        "/api/profile", "/api/projects", "/api/projects/{slug}", "/api/certifications",
        "/api/experience", "/api/skills", "/api/writeups", "/api/writeups/{slug}",
        "/api/cv", "/api/settings/public",
    ):
        assert expected in paths, f"{expected} missing from OpenAPI"


def test_public_routes_require_no_authentication(client, db):
    """Sanity check that nothing in the public surface demands a session."""
    db.add(Project(title="Open", slug="open", status=ContentStatus.PUBLISHED))
    db.commit()
    assert client.get("/api/projects").status_code == 200
    assert client.get("/api/projects/open").status_code == 200
    assert db.scalar(select(Project).where(Project.slug == "open")) is not None
