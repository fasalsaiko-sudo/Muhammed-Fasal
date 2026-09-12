"""Public portfolio API — anonymous, read-only.

Spec §25 public endpoints. Everything here is served to unauthenticated
visitors, so three rules hold throughout:

* only ``PUBLISHED``, non-deleted rows are ever selected (enforced in
  ``app.services.portfolio_service``);
* responses are serialised through the models in ``app.schemas.public``, which
  drop any field not in the public contract;
* nothing here touches admin users, sessions, audit logs or Drive credentials.

Admin mutation routes invalidate the cache; reads are cached in-process
(``PUBLIC_CACHE_TTL_SECONDS``) so the public site stays fast.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.middleware.rate_limit import rate_limit_dependency
from app.schemas.public import (
    ProjectDetail,
    ProjectSummary,
    PublicCertification,
    PublicCV,
    PublicExperience,
    PublicProfile,
    PublicSettings,
    PublicSkillCategory,
    WriteupDetail,
    WriteupSummary,
)
from app.services import portfolio_service

public_router = APIRouter(prefix="/api", tags=["public"])

_public_limit = rate_limit_dependency("public", "rate_limit_public_per_minute")

DbSession = Annotated[Session, Depends(get_db)]


def _not_found(resource: str) -> HTTPException:
    # Deliberately generic: does not reveal whether the row exists but is a draft.
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{resource} not found")


@public_router.get(
    "/profile",
    response_model=PublicProfile,
    summary="Public profile and social links",
    dependencies=[Depends(_public_limit)],
)
def get_profile(db: DbSession) -> dict[str, object]:
    payload = portfolio_service.profile_payload(db)
    if payload is None:
        raise _not_found("Profile")
    return payload


@public_router.get(
    "/projects",
    response_model=list[ProjectSummary],
    summary="Published projects",
    dependencies=[Depends(_public_limit)],
)
def get_projects(
    db: DbSession,
    category: Annotated[str | None, Query(max_length=120, description="Filter by category")] = None,
    featured: Annotated[bool | None, Query(description="Only featured projects")] = None,
) -> list[dict[str, object]]:
    return portfolio_service.projects_payload(db, category=category, featured=featured)


@public_router.get(
    "/projects/{slug}",
    response_model=ProjectDetail,
    summary="One published project by slug",
    dependencies=[Depends(_public_limit)],
)
def get_project(db: DbSession, slug: str) -> dict[str, object]:
    payload = portfolio_service.project_by_slug(db, slug)
    if payload is None:
        raise _not_found("Project")
    return payload


@public_router.get(
    "/certifications",
    response_model=list[PublicCertification],
    summary="Published certifications",
    dependencies=[Depends(_public_limit)],
)
def get_certifications(db: DbSession) -> list[dict[str, object]]:
    return portfolio_service.certifications_payload(db)


@public_router.get(
    "/experience",
    response_model=list[PublicExperience],
    summary="Visible experience entries",
    dependencies=[Depends(_public_limit)],
)
def get_experience(db: DbSession) -> list[dict[str, object]]:
    return portfolio_service.experience_payload(db)


@public_router.get(
    "/skills",
    response_model=list[PublicSkillCategory],
    summary="Skills grouped by category",
    dependencies=[Depends(_public_limit)],
)
def get_skills(db: DbSession) -> list[dict[str, object]]:
    return portfolio_service.skills_payload(db)


@public_router.get(
    "/writeups",
    response_model=list[WriteupSummary],
    summary="Published write-up summaries",
    dependencies=[Depends(_public_limit)],
)
def get_writeups(
    db: DbSession,
    category: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum entries returned")] = 24,
) -> list[dict[str, object]]:
    return portfolio_service.writeups_payload(db, category=category, limit=limit)


@public_router.get(
    "/writeups/{slug}",
    response_model=WriteupDetail,
    summary="One published write-up by slug",
    dependencies=[Depends(_public_limit)],
)
def get_writeup(db: DbSession, slug: str) -> dict[str, object]:
    payload = portfolio_service.writeup_by_slug(db, slug)
    if payload is None:
        raise _not_found("Write-up")
    return payload


@public_router.get(
    "/cv",
    response_model=PublicCV,
    summary="Current public CV",
    dependencies=[Depends(_public_limit)],
)
def get_cv(db: DbSession) -> dict[str, object]:
    """Public by design (spec §42): the current CV is downloadable by visitors."""
    payload = portfolio_service.cv_payload(db)
    if payload is None:
        raise _not_found("CV")
    return payload


@public_router.get(
    "/settings/public",
    response_model=PublicSettings,
    summary="Public site settings",
    dependencies=[Depends(_public_limit)],
)
def get_public_settings(db: DbSession) -> dict[str, object]:
    return portfolio_service.settings_payload(db)
