from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.candidates.domain.repositories import AnswerRepository, CandidateRepository
from api.candidates.infrastructure.repository import (
    SqlAlchemyAnswerRepository,
    SqlAlchemyCandidateRepository,
)
from database import UnitOfWork


class CandidatesUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._uow = UnitOfWork(session_factory)
        self.session: AsyncSession
        self.candidates: CandidateRepository
        self.answers: AnswerRepository

    async def __aenter__(self) -> Self:
        await self._uow.__aenter__()
        self.session = self._uow.session
        self.candidates = SqlAlchemyCandidateRepository(self.session)
        self.answers = SqlAlchemyAnswerRepository(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        await self._uow.__aexit__(exc_type, exc, traceback)
