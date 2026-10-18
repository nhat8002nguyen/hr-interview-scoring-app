from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Protocol, Self

from api.candidates.domain.repositories import AnswerRepository, CandidateRepository


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
