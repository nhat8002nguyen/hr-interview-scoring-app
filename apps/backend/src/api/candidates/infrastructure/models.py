from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.catalog.infrastructure.models import QuestionModel, RoleModel  # noqa: F401
from database import Base


class CandidateModel(Base):
    __tablename__ = "candidates"
    __table_args__ = (
        UniqueConstraint("owner_id", "email", name="uq_candidates_owner_email"),
        UniqueConstraint(
            "owner_id", "external_ref", name="uq_candidates_owner_external_ref"
        ),
        Index("ix_candidates_owner_role", "owner_id", "role_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(255))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_candidates_owner_id_users"),
        index=True,
    )
    session_token: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class AnswerModel(Base):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("candidate_id", "question_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"))
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    answer_type: Mapped[str] = mapped_column(String(16))
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    external_ref: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
