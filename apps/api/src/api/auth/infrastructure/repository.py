from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.auth.domain.entities import User
from api.auth.infrastructure.models import UserModel
from database import UnitOfWork
from iam import Role


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: User) -> User:
        row = UserModel(
            email=user.email,
            password_hash=user.password_hash,
            role=str(user.role),
        )
        self._session.add(row)
        await self._session.flush()
        return self._to_user(row)

    async def get(self, user_id: int) -> User | None:
        row = await self._session.get(UserModel, user_id)
        return None if row is None else self._to_user(row)

    async def get_by_email(self, email: str) -> User | None:
        row = await self._session.scalar(select(UserModel).where(UserModel.email == email))
        return None if row is None else self._to_user(row)

    def _to_user(self, row: UserModel) -> User:
        return User(
            id=row.id,
            email=row.email,
            password_hash=row.password_hash,
            role=Role(row.role),
        )


class TransactionalUserRepository:
    """Runs each repository operation in its own committed transaction."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, user: User) -> User:
        async with UnitOfWork(self._session_factory) as uow:
            return await SqlAlchemyUserRepository(uow.session).add(user)

    async def get(self, user_id: int) -> User | None:
        async with UnitOfWork(self._session_factory) as uow:
            return await SqlAlchemyUserRepository(uow.session).get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        async with UnitOfWork(self._session_factory) as uow:
            return await SqlAlchemyUserRepository(uow.session).get_by_email(email)
