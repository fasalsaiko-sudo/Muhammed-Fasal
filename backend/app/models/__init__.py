"""ORM models.

Importing this package registers every table on ``Base.metadata`` which is what
Alembic autogenerate and ``Base.metadata.create_all`` rely on.
"""

from app.models.audit import AuditLog
from app.models.base import Base, SoftDeleteMixin, TimestampMixin, utcnow
from app.models.certification import Certification, CertificationMedia
from app.models.cv import CVVersion
from app.models.enums import (
    AccessPolicy,
    CertificationStatus,
    ContentStatus,
    MediaCategory,
    MediaType,
    Severity,
    SkillLevel,
    UserRole,
)
from app.models.experience import Experience
from app.models.media import Media
from app.models.profile import Profile, SocialLink
from app.models.project import Project, ProjectMedia, Tag, project_tags
from app.models.session import AdminSession
from app.models.settings import SiteSettings
from app.models.skill import Skill, SkillCategory
from app.models.user import User
from app.models.version import ContentVersion
from app.models.writeup import Writeup, WriteupMedia, writeup_tags

__all__ = [
    "AccessPolicy",
    "AdminSession",
    "AuditLog",
    "Base",
    "CVVersion",
    "Certification",
    "CertificationMedia",
    "CertificationStatus",
    "ContentStatus",
    "ContentVersion",
    "Experience",
    "Media",
    "MediaCategory",
    "MediaType",
    "Profile",
    "Project",
    "ProjectMedia",
    "Severity",
    "SiteSettings",
    "Skill",
    "SkillCategory",
    "SkillLevel",
    "SocialLink",
    "SoftDeleteMixin",
    "Tag",
    "TimestampMixin",
    "User",
    "UserRole",
    "Writeup",
    "WriteupMedia",
    "project_tags",
    "utcnow",
    "writeup_tags",
]
