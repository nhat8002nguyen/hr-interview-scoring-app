from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.catalog.domain.repositories import QuestionRepository, RoleRepository
from api.catalog.infrastructure.repository import (
    SqlAlchemyQuestionRepository,
    SqlAlchemyRoleRepository,
)
from database import UnitOfWork


class CatalogUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._uow = UnitOfWork(session_factory)
        self.session: AsyncSession
        self.roles: RoleRepository
        self.questions: QuestionRepository

    async def __aenter__(self) -> Self:
        await self._uow.__aenter__()
        self.session = self._uow.session
        self.roles = SqlAlchemyRoleRepository(self.session)
        self.questions = SqlAlchemyQuestionRepository(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        await self._uow.__aexit__(exc_type, exc, traceback)
