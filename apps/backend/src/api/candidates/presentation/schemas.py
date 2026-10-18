from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# --- Candidate interview ---


class InterviewCandidate(BaseModel):
    id: int
    name: str | None
    role: str


class InterviewAnswer(BaseModel):
    answer_type: str
    text: str | None
    version: int
    submitted_at: datetime


class InterviewQuestion(BaseModel):
    id: int
    code: str
    sort_order: int
    prompt: str
    answer: InterviewAnswer | None


class Progress(BaseModel):
    answered: int
    total: int


class InterviewResponse(BaseModel):
    candidate: InterviewCandidate
    questions: list[InterviewQuestion]
    progress: Progress


# --- Candidate answer submission ---


class TextAnswerBody(BaseModel):
    answer_type: Literal["text"]
    text: str


class SubmittedAnswer(BaseModel):
    answer_type: str
    version: int
    submitted_at: datetime


class SubmitResponse(BaseModel):
    status: str
    unchanged: bool
    answer: SubmittedAnswer


# --- HR candidate list ---


class ScoringSummary(BaseModel):
    status: str
    suggested_score: int | None
    final_score: int | None
    override_reason: str | None


class CandidateAnswerSummary(BaseModel):
    id: int
    question_id: int
    question_code: str
    answer_type: str
    version: int
    scoring: ScoringSummary


class CandidateListItem(BaseModel):
    id: int
    name: str | None
    email: str
    answer_progress: Progress
    answers: list[CandidateAnswerSummary]


# --- HR candidate detail ---


class ScoringDetail(BaseModel):
    status: str
    suggested_score: int | None
    suggested_reasoning: str | None
    final_score: int | None
    override_reason: str | None
    overridden_by: int | None
    attempt_count: int
    last_error: str | None
    scored_at: datetime | None


class CandidateAnswerDetail(BaseModel):
    id: int
    question_id: int
    question_code: str
    answer_type: str
    version: int
    scoring: ScoringDetail


class CandidateDetailResponse(BaseModel):
    id: int
    name: str | None
    email: str
    role_id: int
    session_token: str
    interview_link: str
    answer_progress: Progress
    answers: list[CandidateAnswerDetail]


# --- HR candidate creation ---


class CreateCandidateBody(BaseModel):
    name: str
    email: str
    role_id: int


class CreateCandidateResponse(BaseModel):
    id: int
    name: str
    email: str
    role_id: int
    session_token: str
    interview_link: str


# --- HR answer detail ---


class AnswerDetailResponse(BaseModel):
    id: int
    candidate_id: int
    question_id: int
    question_code: str
    question_prompt: str
    grading_guide: dict[str, str]
    answer_type: str
    text: str | None
    version: int
    submitted_at: datetime
    scoring: ScoringDetail
