from api.auth.application.seed import seed_hr_account
from api.auth.application.service import AuthTokens
from api.auth.domain.entities import User
from api.auth.infrastructure.models import UserModel
from api.auth.presentation.router import auth_router
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from database import Base, create_engine, create_session_factory
from iam import Role, UnauthorizedError, register_iam_exception_handlers

EMAIL = "hr@talotrace.ai"
PASSWORD = "correct-horse-battery-staple"


class FakeHashingService:
    async def hash(self, data: str) -> str:
        return f"hashed:{data}"


class FakeAuthenticationService:
    def __init__(self) -> None:
        self.user = User(id=1, email=EMAIL, password_hash="hashed", role=Role.HR)
        self.sign_in_calls: list[tuple[str, str]] = []
        self.refresh_calls: list[str] = []
        self.sign_out_calls: list[str | None] = []

    async def sign_in(self, email: str, password: str) -> AuthTokens:
        self.sign_in_calls.append((email, password))
        if email != EMAIL or password != PASSWORD:
            raise UnauthorizedError("Invalid credentials")
        return AuthTokens(
            user=self.user,
            access_token="access-token",
            refresh_token="refresh-token",
        )

    async def refresh(self, refresh_token: str) -> AuthTokens:
        self.refresh_calls.append(refresh_token)
        return AuthTokens(
            user=self.user,
            access_token="access-token-2",
            refresh_token="refresh-token-2",
        )

    async def sign_out(self, refresh_token: str | None) -> None:
        self.sign_out_calls.append(refresh_token)


def _app(service: FakeAuthenticationService) -> FastAPI:
    app = FastAPI()
    app.state.authentication_service = service
    register_iam_exception_handlers(app)
    app.include_router(auth_router)
    return app


async def test_sign_in_returns_tokens() -> None:
    service = FakeAuthenticationService()
    transport = ASGITransport(app=_app(service))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/auth/sign-in",
            json={"email": EMAIL, "password": PASSWORD},
        )

    assert response.status_code == 200
    assert response.json() == {
        "user": {"id": 1, "email": EMAIL, "role": "hr"},
        "access_token": "access-token",
        "refresh_token": "refresh-token",
    }
    assert service.sign_in_calls == [(EMAIL, PASSWORD)]


async def test_sign_in_invalid_credentials_401() -> None:
    service = FakeAuthenticationService()
    transport = ASGITransport(app=_app(service))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/auth/sign-in",
            json={"email": EMAIL, "password": "wrong"},
        )

    assert response.status_code == 401
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Unauthorized"
    assert body["status"] == 401


async def test_refresh_tokens_rotates() -> None:
    service = FakeAuthenticationService()
    transport = ASGITransport(app=_app(service))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/auth/refresh-tokens",
            json={"refresh_token": "old-refresh-token"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "user": {"id": 1, "email": EMAIL, "role": "hr"},
        "access_token": "access-token-2",
        "refresh_token": "refresh-token-2",
    }
    assert service.refresh_calls == ["old-refresh-token"]


async def test_sign_out_204() -> None:
    service = FakeAuthenticationService()
    transport = ASGITransport(app=_app(service))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/auth/sign-out",
            json={"refresh_token": "refresh-token"},
        )

    assert response.status_code == 204
    assert service.sign_out_calls == ["refresh-token"]


async def test_seed_hr_account_is_idempotent() -> None:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    session_factory = create_session_factory(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    hashing = FakeHashingService()
    await seed_hr_account(session_factory, EMAIL, PASSWORD, hashing)
    await seed_hr_account(session_factory, EMAIL, PASSWORD, hashing)

    async with session_factory() as session:
        rows = (await session.execute(select(UserModel))).scalars().all()

    assert len(rows) == 1
    assert rows[0].email == EMAIL
    assert rows[0].role == "hr"
    await engine.dispose()
