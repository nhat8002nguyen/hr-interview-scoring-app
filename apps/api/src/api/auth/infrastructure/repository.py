from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.domain.entities import User
from api.auth.infrastructure.models import UserModel
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
