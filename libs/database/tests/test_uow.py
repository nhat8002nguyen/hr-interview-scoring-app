import pytest
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from database import Base, UnitOfWork, create_engine, create_session_factory


class Item(Base):
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


async def test_unit_of_work_commits_on_success() -> None:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    session_factory = create_session_factory(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with UnitOfWork(session_factory) as uow:
        uow.session.add(Item(name="tower"))

    async with session_factory() as session:
        stored = await session.get(Item, 1)

    assert stored is not None
    assert stored.name == "tower"
    await engine.dispose()


async def test_unit_of_work_rolls_back_on_error() -> None:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    session_factory = create_session_factory(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    with pytest.raises(RuntimeError):
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(Item(name="tower"))
            raise RuntimeError("boom")

    async with session_factory() as session:
        assert await session.get(Item, 1) is None
    await engine.dispose()


def test_session_factory_returns_async_sessions() -> None:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    session = create_session_factory(engine)()

    assert isinstance(session, AsyncSession)
