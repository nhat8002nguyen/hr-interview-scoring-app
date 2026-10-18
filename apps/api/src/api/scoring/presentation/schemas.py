from datetime import datetime

from pydantic import BaseModel, Field


class ScoreOverrideBody(BaseModel):
    final_score: int = Field(ge=1, le=4)
    override_reason: str = Field(min_length=1)


class ScoringJobResponse(BaseModel):
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
    scored_at: datetime | None


class ScoringJobSummaryResponse(BaseModel):
    id: int
    answer_id: int
    candidate_id: int
    candidate_name: str | None
    question_code: str
    status: str
    attempt_count: int
    last_error: str | None
    created_at: datetime
