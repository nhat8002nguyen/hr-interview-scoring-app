from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ScoringJob:
    id: int
    answer_id: int
    status: str
    suggested_score: int | None
    suggested_reasoning: str | None
    final_score: int | None
    override_reason: str | None
    overridden_by: int | None
    attempt_count: int
    last_error: str | None
    claimed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    scored_at: datetime | None


@dataclass(frozen=True, slots=True)
class ScoringInput:
    answer_id: int
    prompt: str
    grading_guide: dict[str, str]
    answer_text: str


@dataclass(frozen=True, slots=True)
class ScoringJobSummary:
    id: int
    answer_id: int
    candidate_id: int
    candidate_name: str | None
    question_code: str
    status: str
    attempt_count: int
    last_error: str | None
    created_at: datetime
