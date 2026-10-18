from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.config import Settings
from api.health.router import router
from api.main import create_app


class FakeConnection:
    async def execute(self, statement: object) -> None:
        return None


class FakeConnect:
    async def __aenter__(self) -> FakeConnection:
        return FakeConnection()

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class FakeEngine:
    def connect(self) -> FakeConnect:
        return FakeConnect()


def _app() -> FastAPI:
    app = FastAPI()
    app.state.engine = FakeEngine()
    app.include_router(router)
    return app


async def test_health_returns_ok() -> None:
    transport = ASGITransport(app=_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_create_app_exposes_health() -> None:
    app = create_app(Settings(database_url="sqlite+aiosqlite://"))
    assert app.title == "talotrace-api"
    assert str(app.state.engine.url) == "sqlite+aiosqlite://"

    app.state.engine = FakeEngine()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
