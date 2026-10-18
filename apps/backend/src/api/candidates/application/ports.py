from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Self

from api.candidates.domain.repositories import AnswerRepository, CandidateRepository


@dataclass(frozen=True, slots=True)
class ScoringSnapshot:
    status: str
    suggested_score: int | None
    suggested_reasoning: str | None
    final_score: int | None
    override_reason: str | None
    overridden_by: int | None
    attempt_count: int
    last_error: str | None
    scored_at: datetime | None


class ScoringReader(Protocol):
    async def get_snapshot(self, answer_id: int) -> ScoringSnapshot | None: ...


class ScoringJobPort(Protocol):
    async def reset_for_answer(self, answer_id: int, *, status: str) -> None: ...


class FileStorage(Protocol):
    async def save(self, key: str, data: bytes) -> None: ...

    async def read(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...


TokenGenerator = Callable[[], str]


class CandidatesUnitOfWork(Protocol):
    candidates: CandidateRepository
    answers: AnswerRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None: ...


CandidatesUnitOfWorkFactory = Callable[[], AbstractAsyncContextManager[CandidatesUnitOfWork]]
