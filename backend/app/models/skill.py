from __future__ import annotations

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin
from app.models.enums import SkillLevel


class SkillCategory(TimestampMixin, Base):
    __tablename__ = "skill_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    icon: Mapped[str | None] = mapped_column(String(48))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    skills: Mapped[list[Skill]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
        order_by="Skill.sort_order",
        passive_deletes=True,
    )


class Skill(SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("category_id", "name", name="skills_category_name_unique"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("skill_categories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(96), nullable=False)
    level: Mapped[SkillLevel] = mapped_column(
        Enum(SkillLevel, native_enum=False, length=16, name="skill_level", create_constraint=True),
        default=SkillLevel.INTERMEDIATE,
        nullable=False,
    )
    icon: Mapped[str | None] = mapped_column(String(48))
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    category: Mapped[SkillCategory] = relationship(back_populates="skills")
