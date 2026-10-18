from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.auth.infrastructure.models import UserModel  # noqa: F401
from api.candidates.infrastructure.models import AnswerModel  # noqa: F401
from database import Base


class ScoringJobModel(Base):
    __tablename__ = "scoring_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    answer_id: Mapped[int] = mapped_column(ForeignKey("answers.id"), unique=True)
    status: Mapped[str] = mapped_column(String(32))
    suggested_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggested_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
