from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.scoring.domain.repositories import ScoringJobRepository
from api.scoring.infrastructure.repository import SqlAlchemyScoringJobRepository
from database import UnitOfWork


class SqlAlchemyScoringUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._uow = UnitOfWork(session_factory)
        self.session: AsyncSession
        self.scoring_jobs: ScoringJobRepository

    async def __aenter__(self) -> Self:
        await self._uow.__aenter__()
        self.session = self._uow.session
        self.scoring_jobs = SqlAlchemyScoringJobRepository(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        await self._uow.__aexit__(exc_type, exc, traceback)
