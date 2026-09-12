"""Read model for the public portfolio.

Every function here returns only content an anonymous visitor may see:
``PUBLISHED`` rows, no drafts, no audit data, no Drive internals. Results are
cached in-process and invalidated whenever the admin publishes something.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config.settings import get_settings
from app.models.certification import Certification, CertificationMedia
from app.models.cv import CVVersion
from app.models.enums import ContentStatus
from app.models.experience import Experience
from app.models.media import Media
from app.models.profile import Profile
from app.models.project import Project, ProjectMedia
from app.models.settings import SiteSettings
from app.models.skill import SkillCategory
from app.models.writeup import Writeup
from app.utils.cache import CacheNamespace, get_cache
from app.utils.helpers import iso, reading_time_minutes, utcnow

PUBLISHED = ContentStatus.PUBLISHED


def cached(key: str, producer: Callable[[], Any]):
    """Return a cached payload or compute and store it."""
    cache = get_cache(get_settings().public_cache_ttl_seconds)
    hit = cache.get(key)
    if hit is not None:
        return hit
    value = producer()
    cache.set(key, value)
    return value


def invalidate(*namespaces: str) -> None:
    get_cache().invalidate(*(namespaces or ()))
    get_cache().invalidate(CacheNamespace.SNAPSHOT)


# --------------------------------------------------------------------- profile
def profile_payload(db: Session) -> dict[str, Any] | None:
    def build() -> dict[str, Any] | None:
        profile = db.get(Profile, 1)
        if profile is None:
            return None
        image: Media | None = profile.profile_image
        return {
            "name": profile.name,
            "headline": profile.headline,
            "short_bio": profile.short_bio,
            "long_bio": profile.long_bio,
            "location": profile.location,
            "availability_status": profile.availability_status,
            "email": profile.email,
            "phone": profile.phone,
            "profile_image": image.public_payload() if image else None,
            "social_links": [
                {
                    "platform": link.platform,
                    "label": link.label,
                    "url": link.url,
                    "icon": link.icon,
                    "sort_order": link.sort_order,
                }
                for link in profile.social_links
                if link.enabled
            ],
            "updated_at": iso(profile.updated_at),
        }

    return cached(CacheNamespace.PROFILE, build)


# -------------------------------------------------------------------- projects
def _project_summary(project: Project) -> dict[str, Any]:
    featured_image = next(
        (item.media_item for item in project.media if item.is_featured and item.media_item),
        next((item.media_item for item in project.media if item.media_item), None),
    )
    return {
        "id": project.id,
        "title": project.title,
        "slug": project.slug,
        "short_description": project.short_description,
        "category": project.category,
        "security_focus": project.security_focus,
        "technologies": project.technologies or [],
        "tags": [tag.name for tag in project.tags],
        "featured": project.featured,
        "severity": project.severity.value if project.severity else None,
        "github_url": project.github_url,
        "demo_url": project.demo_url,
        "cover_image": featured_image.public_payload() if featured_image else None,
        "published_at": iso(project.published_at),
    }


def _project_detail(project: Project) -> dict[str, Any]:
    payload = _project_summary(project)
    payload.update(
        {
            "description": project.description,
            "problem": project.problem,
            "solution": project.solution,
            "methodology": project.methodology,
            "vulnerability_type": project.vulnerability_type,
            "cvss_score": project.cvss_score,
            "cwe": project.cwe,
            "owasp_category": project.owasp_category,
            "target_type": project.target_type,
            "testing_methodology": project.testing_methodology,
            "tools_used": project.tools_used or [],
            "findings_summary": project.findings_summary,
            "remediation_summary": project.remediation_summary,
            "writeup_url": project.writeup_url,
            "media": [
                {
                    "caption": item.caption,
                    "alt_text": item.alt_text,
                    "is_featured": item.is_featured,
                    "sort_order": item.sort_order,
                    **(item.media_item.public_payload() if item.media_item else {}),
                }
                for item in project.media
                if item.media_item
            ],
        }
    )
    return payload


def projects_payload(db: Session, *, category: str | None = None, featured: bool | None = None) -> list[dict[str, Any]]:
    def build() -> list[dict[str, Any]]:
        statement = (
            select(Project)
            .options(
                selectinload(Project.tags),
                selectinload(Project.media).selectinload(ProjectMedia.media_item),
            )
            .where(Project.status == PUBLISHED, Project.deleted_at.is_(None))
            .order_by(Project.sort_order, Project.published_at.desc().nullslast(), Project.id.desc())
        )
        rows = list(db.scalars(statement))
        return [_project_summary(row) for row in rows]

    items = cached(CacheNamespace.PROJECTS, build)
    if category:
        items = [item for item in items if (item.get("category") or "").lower() == category.lower()]
    if featured is not None:
        items = [item for item in items if item["featured"] is featured]
    return items


def project_by_slug(db: Session, slug: str) -> dict[str, Any] | None:
    def build() -> dict[str, Any] | None:
        project = db.scalar(
            select(Project)
            .options(
                selectinload(Project.tags),
                selectinload(Project.media).selectinload(ProjectMedia.media_item),
            )
            .where(Project.slug == slug, Project.status == PUBLISHED, Project.deleted_at.is_(None))
        )
        return _project_detail(project) if project else None

    return cached(f"{CacheNamespace.PROJECTS}:{slug}", build)


# --------------------------------------------------------------- certifications
def certifications_payload(db: Session) -> list[dict[str, Any]]:
    def build() -> list[dict[str, Any]]:
        statement = (
            select(Certification)
            .options(selectinload(Certification.media).selectinload(CertificationMedia.media_item))
            .where(Certification.status == PUBLISHED, Certification.deleted_at.is_(None))
            .order_by(Certification.sort_order, Certification.id.desc())
        )
        rows = list(db.scalars(statement))
        result = []
        for row in rows:
            image = row.primary_image
            result.append(
                {
                    "id": row.id,
                    "title": row.title,
                    "issuer": row.issuer,
                    "description": row.description,
                    "credential_id": row.credential_id,
                    "credential_url": row.credential_url,
                    "issue_date": row.issue_date.isoformat() if row.issue_date else None,
                    "expiry_date": row.expiry_date.isoformat() if row.expiry_date else None,
                    "expiry_status": row.expiry_status.value,
                    "featured": row.featured,
                    "image": image.public_payload() if image else None,
                }
            )
        return result

    return cached(CacheNamespace.CERTIFICATIONS, build)


# ------------------------------------------------------------------ experience
def experience_payload(db: Session) -> list[dict[str, Any]]:
    def build() -> list[dict[str, Any]]:
        rows = db.scalars(
            select(Experience)
            .where(Experience.visible.is_(True), Experience.deleted_at.is_(None))
            .order_by(Experience.sort_order, Experience.start_date.desc().nullslast(), Experience.id.desc())
        ).all()
        return [
            {
                "id": row.id,
                "company": row.company,
                "role": row.role,
                "location": row.location,
                "employment_type": row.employment_type,
                "date_range": row.date_range,
                "start_date": row.start_date.isoformat() if row.start_date else None,
                "end_date": row.end_date.isoformat() if row.end_date else None,
                "is_current": row.is_current,
                "description": row.description,
                "highlights": row.highlights or [],
                "technologies": row.technologies or [],
            }
            for row in rows
        ]

    return cached(CacheNamespace.EXPERIENCE, build)


# ---------------------------------------------------------------------- skills
def skills_payload(db: Session) -> list[dict[str, Any]]:
    def build() -> list[dict[str, Any]]:
        categories = db.scalars(
            select(SkillCategory).options(selectinload(SkillCategory.skills)).order_by(SkillCategory.sort_order)
        ).all()
        result = []
        for category in categories:
            skills = [
                {
                    "id": skill.id,
                    "name": skill.name,
                    "level": skill.level.value,
                    "icon": skill.icon,
                    "featured": skill.featured,
                }
                for skill in category.skills
                if skill.deleted_at is None
            ]
            if skills:
                result.append(
                    {
                        "id": category.id,
                        "name": category.name,
                        "description": category.description,
                        "icon": category.icon,
                        "skills": skills,
                    }
                )
        return result

    return cached(CacheNamespace.SKILLS, build)


# -------------------------------------------------------------------- writeups
def _writeup_summary(row: Writeup) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "slug": row.slug,
        "summary": row.summary,
        "category": row.category,
        "severity": row.severity.value if row.severity else None,
        "cvss_score": row.cvss_score,
        "cwe": row.cwe,
        "owasp_category": row.owasp_category,
        "tags": [tag.name for tag in row.tags],
        "featured": row.featured,
        "published_at": iso(row.published_at),
        "reading_time_minutes": row.reading_time_minutes,
    }


def writeups_payload(db: Session, *, category: str | None = None, limit: int = 24) -> list[dict[str, Any]]:
    def build() -> list[dict[str, Any]]:
        statement = (
            select(Writeup)
            .options(selectinload(Writeup.tags))
            .where(Writeup.status == PUBLISHED, Writeup.deleted_at.is_(None))
            .order_by(Writeup.published_at.desc().nullslast(), Writeup.id.desc())
            .limit(200)
        )
        return [_writeup_summary(row) for row in db.scalars(statement)]

    items = cached(CacheNamespace.WRITEUPS, build)
    if category:
        items = [item for item in items if (item.get("category") or "").lower() == category.lower()]
    return items[:limit]


def writeup_by_slug(db: Session, slug: str) -> dict[str, Any] | None:
    def build() -> dict[str, Any] | None:
        row = db.scalar(
            select(Writeup)
            .options(selectinload(Writeup.tags))
            .where(Writeup.slug == slug, Writeup.status == PUBLISHED, Writeup.deleted_at.is_(None))
        )
        if row is None:
            return None
        payload = _writeup_summary(row)
        payload["content"] = row.content
        payload["target_summary"] = row.target_summary
        payload["reading_time_minutes"] = row.reading_time_minutes or reading_time_minutes(row.content)
        return payload

    return cached(f"{CacheNamespace.WRITEUPS}:{slug}", build)


# -------------------------------------------------------------------------- CV
def cv_payload(db: Session) -> dict[str, Any] | None:
    def build() -> dict[str, Any] | None:
        current = db.scalar(
            select(CVVersion).where(
                CVVersion.is_current.is_(True),
                CVVersion.archived.is_(False),
                CVVersion.deleted_at.is_(None),
            )
        )
        return current.public_payload() if current else None

    return cached(CacheNamespace.CV, build)


# -------------------------------------------------------------------- settings
def settings_payload(db: Session) -> dict[str, Any]:
    def build() -> dict[str, Any]:
        row = db.get(SiteSettings, 1)
        return row.public_payload() if row else {}

    return cached(CacheNamespace.SETTINGS, build)


# -------------------------------------------------------------------- snapshot
def snapshot(db: Session) -> dict[str, Any]:
    """Sanitized public snapshot — safe to publish as a static JSON file."""

    def build() -> dict[str, Any]:
        return {
            "generated_at": iso(utcnow()),
            "profile": profile_payload(db),
            "projects": projects_payload(db),
            "certifications": certifications_payload(db),
            "experience": experience_payload(db),
            "skills": skills_payload(db),
            "writeups": writeups_payload(db),
            "cv": cv_payload(db),
            "settings": settings_payload(db),
        }

    return cached(CacheNamespace.SNAPSHOT, build)
