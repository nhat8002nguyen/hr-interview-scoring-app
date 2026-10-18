from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import Delete, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.auth.infrastructure.models import RefreshTokenModel
from database import UnitOfWork


def consume_refresh_token(token_id: str, now: datetime) -> Delete:
    return cast(
        Delete,
        (
            delete(RefreshTokenModel)
            .where(
                RefreshTokenModel.token_id == token_id,
                RefreshTokenModel.expires_at > now,
            )
            .returning(RefreshTokenModel.user_id)
        ),
    )


class SqlAlchemyRefreshTokenStorage:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, token_id: str, user_id: int, ttl_seconds: int) -> None:
        self._session.add(
            RefreshTokenModel(
                token_id=token_id,
                user_id=user_id,
                expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
            )
        )
        await self._session.flush()

    async def validate_and_consume(self, token_id: str) -> int | None:
        result = await self._session.execute(consume_refresh_token(token_id, datetime.now(UTC)))
        return result.scalar_one_or_none()

    async def revoke(self, token_id: str) -> None:
        await self._session.execute(
            delete(RefreshTokenModel).where(RefreshTokenModel.token_id == token_id)
        )


class TransactionalRefreshTokenStorage:
    """Runs each storage operation in its own committed transaction."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, token_id: str, user_id: int, ttl_seconds: int) -> None:
        async with UnitOfWork(self._session_factory) as uow:
            await SqlAlchemyRefreshTokenStorage(uow.session).save(token_id, user_id, ttl_seconds)

    async def validate_and_consume(self, token_id: str) -> int | None:
        async with UnitOfWork(self._session_factory) as uow:
            return await SqlAlchemyRefreshTokenStorage(uow.session).validate_and_consume(token_id)

    async def revoke(self, token_id: str) -> None:
        async with UnitOfWork(self._session_factory) as uow:
            await SqlAlchemyRefreshTokenStorage(uow.session).revoke(token_id)
