#!/usr/bin/env python3
"""Seed the portfolio CMS from ``database/seed/portfolio_seed.json``.

The seed file is a faithful extraction of the content that was hardcoded in the
static ``index.html``. Running this script is how the existing portfolio moves
into the database without losing a single project, certificate, skill or
paragraph.

    cd backend
    DATABASE_URL=postgresql+psycopg://... python ../scripts/seed_database.py [--reset]

The script is idempotent: rows that already exist are updated rather than
duplicated, so it is safe to re-run after edits to the seed file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import sys
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy import select  # noqa: E402

from app.config.database import get_session_factory, reset_engine  # noqa: E402
from app.config.settings import get_settings  # noqa: E402
from app.models.certification import Certification, CertificationMedia  # noqa: E402
from app.models.cv import CVVersion  # noqa: E402
from app.models.enums import (  # noqa: E402
    AccessPolicy,
    CertificationStatus,
    ContentStatus,
    MediaCategory,
    MediaType,
    Severity,
    SkillLevel,
)
from app.models.experience import Experience  # noqa: E402
from app.models.media import Media  # noqa: E402
from app.models.profile import Profile, SocialLink  # noqa: E402
from app.models.project import Project, Tag  # noqa: E402
from app.models.settings import SiteSettings, default_feature_flags  # noqa: E402
from app.models.skill import Skill, SkillCategory  # noqa: E402
from app.models.writeup import Writeup  # noqa: E402
from app.utils.helpers import reading_time_minutes, utcnow  # noqa: E402
from app.utils.security import sanitize_filename  # noqa: E402

SEED_PATH = REPO_ROOT / "database" / "seed" / "portfolio_seed.json"

EXTENSION_TO_MEDIA = {
    ".jpg": MediaType.IMAGE,
    ".jpeg": MediaType.IMAGE,
    ".png": MediaType.IMAGE,
    ".webp": MediaType.IMAGE,
    ".pdf": MediaType.PDF,
    ".mp4": MediaType.VIDEO,
}


def parse_date(value):
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def local_media(db, *, path: str, category: MediaCategory, caption: str | None = None) -> Media:
    """Create (or reuse) a media row that still points at a repository asset.

    ``drive_file_id`` uses a ``local:`` prefix so it is obviously not a Drive id.
    ``scripts/sync_media_to_drive.py`` replaces it with a real Drive identifier
    once the service account is configured — the public URL stays valid either
    way, which is what keeps the site working through the migration.
    """
    marker = f"local:{path}"
    existing = db.scalar(select(Media).where(Media.drive_file_id == marker))
    if existing is not None:
        return existing

    absolute = REPO_ROOT / path
    checksum = size = None
    if absolute.is_file():
        data = absolute.read_bytes()
        checksum = hashlib.sha256(data).hexdigest()
        size = len(data)
    mime, _ = mimetypes.guess_type(path)
    media = Media(
        filename=sanitize_filename(path.split("/")[-1]),
        original_filename=sanitize_filename(path.split("/")[-1]),
        drive_file_id=marker,
        drive_folder_id=None,
        category=category,
        mime_type=mime or "application/octet-stream",
        media_type=EXTENSION_TO_MEDIA.get(Path(path).suffix.lower(), MediaType.OTHER),
        size_bytes=size or 0,
        checksum=checksum or hashlib.sha256(marker.encode()).hexdigest(),
        drive_url=path,
        download_url=path,
        thumbnail_url=path,
        access_policy=AccessPolicy.PUBLIC,
        last_verified_at=utcnow(),
    )
    db.add(media)
    db.flush()
    return media


def tags_for(db, names):
    result = []
    for name in names or []:
        tag = db.scalar(select(Tag).where(Tag.name == name))
        if tag is None:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
        result.append(tag)
    return result


def seed_profile(db, data):
    payload = data.get("profile") or {}
    profile = db.get(Profile, 1)
    if profile is None:
        profile = Profile(id=1, name=payload.get("name", "Muhammed Fasal"))
        db.add(profile)
        db.flush()
    for key in (
        "name",
        "headline",
        "short_bio",
        "long_bio",
        "location",
        "availability_status",
        "email",
        "phone",
    ):
        if payload.get(key):
            setattr(profile, key, payload[key])
    image = payload.get("profile_image")
    if image:
        media = local_media(db, path=image["path"], category=MediaCategory.PROFILE)
        profile.profile_image_media_id = media.id
    db.flush()

    existing = {link.platform.lower(): link for link in profile.social_links}
    for item in data.get("social_links") or []:
        platform = item["platform"].lower()
        link = existing.get(platform)
        if link is None:
            link = SocialLink(profile_id=1, platform=platform, label=item["label"], url=item["url"])
            db.add(link)
        link.label = item["label"]
        link.url = item["url"]
        link.icon = item.get("icon")
        link.enabled = True
        link.sort_order = item.get("sort_order", 0)
    db.flush()
    return profile


def seed_experience(db, data):
    count = 0
    for item in data.get("experience") or []:
        row = db.scalar(
            select(Experience).where(
                Experience.company == item["company"], Experience.role == item["role"]
            )
        )
        if row is None:
            row = Experience(company=item["company"], role=item["role"])
            db.add(row)
        for key, value in item.items():
            if key in {"company", "role", "start_date", "end_date"}:
                continue
            setattr(row, key, value)
        row.start_date = parse_date(item.get("start_date"))
        row.end_date = parse_date(item.get("end_date"))
        count += 1
    db.flush()
    return count


def seed_skills(db, data):
    categories = {}
    for item in data.get("skill_categories") or []:
        row = db.scalar(select(SkillCategory).where(SkillCategory.name == item["name"]))
        if row is None:
            row = SkillCategory(name=item["name"])
            db.add(row)
            db.flush()
        row.description = item.get("description")
        row.icon = item.get("icon")
        row.sort_order = item.get("sort_order", 0)
        categories[item["name"]] = row
    db.flush()

    count = 0
    for item in data.get("skills") or []:
        category = categories.get(item["category"])
        if category is None:
            continue
        row = db.scalar(
            select(Skill).where(Skill.category_id == category.id, Skill.name == item["name"])
        )
        if row is None:
            row = Skill(category_id=category.id, name=item["name"])
            db.add(row)
        row.level = SkillLevel(str(item.get("level", "INTERMEDIATE")).upper())
        row.featured = bool(item.get("featured", False))
        row.sort_order = item.get("sort_order", 0)
        count += 1
    db.flush()
    return count


def seed_projects(db, data):
    count = 0
    for item in data.get("projects") or []:
        slug = item["slug"]
        row = db.scalar(select(Project).where(Project.slug == slug))
        if row is None:
            row = Project(slug=slug, title=item["title"])
            db.add(row)
            db.flush()
        for key, value in item.items():
            if key in {"slug", "tags", "status", "severity"}:
                continue
            if hasattr(row, key):
                setattr(row, key, value)
        row.status = ContentStatus(str(item.get("status", "DRAFT")).upper())
        if item.get("severity"):
            row.severity = Severity(str(item["severity"]).upper())
        if row.status is ContentStatus.PUBLISHED and row.published_at is None:
            row.published_at = utcnow()
        row.tags = tags_for(db, item.get("tags"))
        count += 1
    db.flush()
    return count


def seed_certifications(db, data):
    count = 0
    for item in data.get("certifications") or []:
        title = item["title"]
        row = db.scalar(select(Certification).where(Certification.title == title))
        if row is None:
            row = Certification(title=title, issuer=item.get("issuer", "Unknown"))
            db.add(row)
            db.flush()
        row.issuer = item.get("issuer", row.issuer)
        row.description = item.get("description")
        row.credential_id = item.get("credential_id")
        row.credential_url = item.get("credential_url")
        row.issue_date = parse_date(item.get("issue_date"))
        row.expiry_date = parse_date(item.get("expiry_date"))
        row.expiry_status = CertificationStatus(str(item.get("expiry_status", "NO_EXPIRY")).upper())
        row.featured = bool(item.get("featured", False))
        row.status = ContentStatus(str(item.get("status", "DRAFT")).upper())
        row.sort_order = item.get("sort_order", 0)
        for index, media_item in enumerate(item.get("media") or []):
            media = local_media(
                db, path=media_item["path"], category=MediaCategory.CERTIFICATION
            )
            already = db.scalar(
                select(CertificationMedia).where(
                    CertificationMedia.certification_id == row.id,
                    CertificationMedia.media_id == media.id,
                )
            )
            if already is None:
                db.add(
                    CertificationMedia(
                        certification_id=row.id,
                        media_id=media.id,
                        caption=media_item.get("caption"),
                        sort_order=index,
                        is_primary=index == 0,
                    )
                )
        count += 1
    db.flush()
    return count


def seed_writeups(db, data):
    count = 0
    for item in data.get("writeups") or []:
        slug = item["slug"]
        row = db.scalar(select(Writeup).where(Writeup.slug == slug))
        if row is None:
            row = Writeup(slug=slug, title=item["title"], content="")
            db.add(row)
            db.flush()
        for key, value in item.items():
            if key in {"slug", "tags", "status", "severity"}:
                continue
            if hasattr(row, key):
                setattr(row, key, value)
        row.status = ContentStatus(str(item.get("status", "DRAFT")).upper())
        if item.get("severity"):
            row.severity = Severity(str(item["severity"]).upper())
        row.reading_time_minutes = reading_time_minutes(row.content)
        row.tags = tags_for(db, item.get("tags"))
        count += 1
    db.flush()
    return count


def seed_cv(db, data):
    payload = data.get("cv")
    if not payload:
        return 0
    drive_file_id = payload["drive_file_id"]
    media = db.scalar(select(Media).where(Media.drive_file_id == drive_file_id))
    if media is None:
        media = Media(
            filename=payload.get("filename", "cv.pdf"),
            original_filename=payload.get("filename", "cv.pdf"),
            drive_file_id=drive_file_id,
            drive_folder_id=None,
            category=MediaCategory.CV,
            mime_type=payload.get("mime_type", "application/pdf"),
            media_type=MediaType.PDF,
            size_bytes=0,
            checksum=hashlib.sha256(drive_file_id.encode()).hexdigest(),
            drive_url=f"https://drive.google.com/file/d/{drive_file_id}/view",
            download_url=f"https://drive.google.com/uc?export=download&id={drive_file_id}",
            thumbnail_url=None,
            access_policy=AccessPolicy.PUBLIC,
            last_verified_at=utcnow(),
        )
        db.add(media)
        db.flush()

    existing = db.scalar(select(CVVersion).where(CVVersion.media_id == media.id))
    if existing is not None:
        return 1
    for other in db.scalars(select(CVVersion)):
        other.is_current = False
    db.add(
        CVVersion(
            media_id=media.id,
            version_name=payload.get("version_name", "Current CV"),
            version_number=1,
            is_current=True,
            notes=payload.get("notes"),
            uploaded_at=datetime.now(),
        )
    )
    db.flush()
    return 1


def seed_settings(db, data):
    payload = data.get("settings") or {}
    row = db.get(SiteSettings, 1)
    if row is None:
        row = SiteSettings(id=1, feature_flags=default_feature_flags())
        db.add(row)
        db.flush()
    for key, value in payload.items():
        if key == "feature_flags":
            row.feature_flags = {**default_feature_flags(), **(value or {})}
        elif value is not None:
            setattr(row, key, value)
    db.flush()
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the portfolio CMS database")
    parser.add_argument(
        "--seed-file", default=str(SEED_PATH), help="Path to the seed JSON document"
    )
    args = parser.parse_args()

    settings = get_settings()
    print(f"Environment : {settings.environment}")
    print(f"Database    : {settings.database_url.split('@')[-1]}")
    print(f"Seed file   : {args.seed_file}")

    data = json.loads(Path(args.seed_file).read_text(encoding="utf-8"))
    reset_engine()
    db = get_session_factory()()
    try:
        results = {
            "profile": 1 if seed_profile(db, data) else 0,
            "social_links": len(data.get("social_links") or []),
            "experience": seed_experience(db, data),
            "skills": seed_skills(db, data),
            "projects": seed_projects(db, data),
            "certifications": seed_certifications(db, data),
            "writeups": seed_writeups(db, data),
            "cv_versions": seed_cv(db, data),
            "settings": seed_settings(db, data),
        }
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print("\nSeeded:")
    for key, value in results.items():
        print(f"  {key:<16} {value}")
    print(
        "\nMedia referencing repository assets use a 'local:' drive_file_id.\n"
        "Run scripts/sync_media_to_drive.py after configuring the Google service\n"
        "account to move those files into the Portfolio CMS Drive folder."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
