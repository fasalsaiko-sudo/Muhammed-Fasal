"""Domain enumerations.

Stored as ``VARCHAR + CHECK`` (``native_enum=False``) so the schema is identical
on PostgreSQL and SQLite and adding a value never requires an ALTER TYPE.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    # Reserved for future multi-user setups; the authorization layer already
    # understands roles, only the allowlist changes.
    EDITOR = "EDITOR"
    VIEWER = "VIEWER"


class ContentStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class CertificationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    NO_EXPIRY = "NO_EXPIRY"


class MediaType(StrEnum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    PDF = "PDF"
    DOCUMENT = "DOCUMENT"
    OTHER = "OTHER"


class MediaCategory(StrEnum):
    CV = "CV"
    PROFILE = "PROFILE"
    PROJECT = "PROJECT"
    CERTIFICATION = "CERTIFICATION"
    WRITEUP = "WRITEUP"
    EXPERIENCE = "EXPERIENCE"
    OTHER = "OTHER"


class AccessPolicy(StrEnum):
    """How the public site is allowed to reference a media object."""

    PUBLIC = "PUBLIC"
    # Delivered through the backend only (private Drive files), never as a
    # direct public link.
    RESTRICTED = "RESTRICTED"


class Severity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SkillLevel(StrEnum):
    BEGINNER = "BEGINNER"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"
    EXPERT = "EXPERT"


WRITEUP_CATEGORIES: tuple[str, ...] = (
    "Web Application Security",
    "Network Security",
    "Vulnerability Research",
    "Bug Bounty",
    "CTF",
    "Security Tooling",
    "Security Awareness",
)
