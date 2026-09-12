"""Response models for the public portfolio API.

These double as the public contract: FastAPI serialises responses *through*
them, so any field a service accidentally adds is dropped before it reaches a
visitor. That is the enforcement point for the rule that the public API never
exposes admin users, audit logs, Drive internals or draft content.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PublicModel(BaseModel):
    """Base for public responses: unknown fields are never emitted."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class PublicMedia(PublicModel):
    id: int
    media_type: str
    mime_type: str | None = None
    url: str | None = None
    thumbnail_url: str | None = None
    download_url: str | None = None
    size_bytes: int | None = None


class SocialLink(PublicModel):
    platform: str
    label: str | None = None
    url: str
    icon: str | None = None
    sort_order: int = 0


class PublicProfile(PublicModel):
    name: str
    headline: str | None = None
    short_bio: str | None = None
    long_bio: str | None = None
    location: str | None = None
    availability_status: str | None = None
    email: str | None = None
    phone: str | None = None
    profile_image: PublicMedia | None = None
    social_links: list[SocialLink] = Field(default_factory=list)
    updated_at: str | None = None


class ProjectSummary(PublicModel):
    id: int
    title: str
    slug: str
    short_description: str | None = None
    category: str | None = None
    security_focus: str | None = None
    technologies: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    featured: bool = False
    severity: str | None = None
    github_url: str | None = None
    demo_url: str | None = None
    cover_image: PublicMedia | None = None
    published_at: str | None = None


class ProjectMediaItem(PublicMedia):
    caption: str | None = None
    alt_text: str | None = None
    is_featured: bool = False
    sort_order: int = 0


class ProjectDetail(ProjectSummary):
    description: str | None = None
    problem: str | None = None
    solution: str | None = None
    methodology: str | None = None
    vulnerability_type: str | None = None
    cvss_score: float | None = None
    cwe: str | None = None
    owasp_category: str | None = None
    target_type: str | None = None
    testing_methodology: str | None = None
    tools_used: list[str] = Field(default_factory=list)
    findings_summary: str | None = None
    remediation_summary: str | None = None
    writeup_url: str | None = None
    media: list[ProjectMediaItem] = Field(default_factory=list)


class PublicCertification(PublicModel):
    id: int
    title: str
    issuer: str | None = None
    description: str | None = None
    credential_id: str | None = None
    credential_url: str | None = None
    issue_date: str | None = None
    expiry_date: str | None = None
    expiry_status: str | None = None
    featured: bool = False
    image: PublicMedia | None = None


class PublicExperience(PublicModel):
    id: int
    company: str
    role: str | None = None
    location: str | None = None
    employment_type: str | None = None
    date_range: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool = False
    description: str | None = None
    highlights: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class PublicSkill(PublicModel):
    id: int
    name: str
    level: str
    icon: str | None = None
    featured: bool = False


class PublicSkillCategory(PublicModel):
    id: int
    name: str
    description: str | None = None
    icon: str | None = None
    skills: list[PublicSkill] = Field(default_factory=list)


class WriteupSummary(PublicModel):
    id: int
    title: str
    slug: str
    summary: str | None = None
    category: str | None = None
    severity: str | None = None
    cvss_score: float | None = None
    cwe: str | None = None
    owasp_category: str | None = None
    tags: list[str] = Field(default_factory=list)
    featured: bool = False
    published_at: str | None = None
    reading_time_minutes: int | None = None


class WriteupDetail(WriteupSummary):
    content: str | None = None
    target_summary: str | None = None


class PublicCV(PublicModel):
    name: str
    version: str | None = None
    updated_at: str | None = None
    download_url: str | None = None
    view_url: str | None = None
    size_bytes: int | None = None
    mime_type: str | None = None


class PublicSettings(PublicModel):
    portfolio_title: str | None = None
    seo_description: str | None = None
    keywords: str | None = None
    og_title: str | None = None
    og_description: str | None = None
    og_image_url: str | None = None
    canonical_url: str | None = None
    contact_email: str | None = None
    availability_status: str | None = None
    footer_text: str | None = None
    theme: str | None = None
    feature_flags: dict[str, bool] = Field(default_factory=dict)
