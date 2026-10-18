from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.auth.domain.entities import User
from api.auth.infrastructure.repository import SqlAlchemyUserRepository
from database import UnitOfWork
from iam import HashingServiceProtocol, Role


async def seed_hr_account(
    session_factory: async_sessionmaker[AsyncSession],
    email: str,
    password: str,
    hashing: HashingServiceProtocol,
) -> None:
    """Create the seeded HR account once, idempotently, committing via UnitOfWork."""
    password_hash = await hashing.hash(password)
    async with UnitOfWork(session_factory) as uow:
        users = SqlAlchemyUserRepository(uow.session)
        if await users.get_by_email(email) is not None:
            return
        await users.add(
            User(id=0, email=email, password_hash=password_hash, role=Role.HR),
        )
