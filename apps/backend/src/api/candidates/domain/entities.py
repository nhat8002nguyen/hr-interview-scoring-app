from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Candidate:
    id: int
    name: str | None
    email: str
    role_id: int
    session_token: str
    external_ref: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Answer:
    id: int
    candidate_id: int
    question_id: int
    answer_type: str
    text: str | None
    audio_key: str | None
    content_hash: str
    version: int
    external_ref: str | None
    submitted_at: datetime
