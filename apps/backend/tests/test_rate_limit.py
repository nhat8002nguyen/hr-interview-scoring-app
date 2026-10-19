import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.auth.application.rate_limit import RateLimiter
from api.auth.application.service import AuthTokens
from api.auth.domain.entities import User
from api.auth.domain.exceptions import RateLimitExceededError
from api.auth.presentation.errors import register_authentication_exception_handlers
from api.auth.presentation.router import auth_router
from api.config import Settings
from iam import Role, register_iam_exception_handlers


async def test_rate_limiter_allows_up_to_max_then_raises() -> None:
    limiter = RateLimiter(max_requests=2, window_seconds=60.0)

    await limiter.check("ip:127.0.0.1")
    await limiter.check("ip:127.0.0.1")
    with pytest.raises(RateLimitExceededError):
        await limiter.check("ip:127.0.0.1")


async def test_rate_limiter_allows_again_after_window_elapses() -> None:
    limiter = RateLimiter(max_requests=2, window_seconds=0.05)

    await limiter.check("ip:127.0.0.1")
    await limiter.check("ip:127.0.0.1")
    with pytest.raises(RateLimitExceededError):
        await limiter.check("ip:127.0.0.1")

    await asyncio.sleep(0.1)
    await limiter.check("ip:127.0.0.1")


async def test_rate_limiter_tracks_keys_independently() -> None:
    limiter = RateLimiter(max_requests=1, window_seconds=60.0)

    await limiter.check("email:one@example.com")
    with pytest.raises(RateLimitExceededError):
        await limiter.check("email:one@example.com")

    await limiter.check("email:two@example.com")


class _FakeAuthenticationService:
    def __init__(self) -> None:
        self.user = User(id=1, email="hr@talotrace.ai", password_hash="hashed", role=Role.HR)

    async def sign_in(self, email: str, password: str) -> AuthTokens:
        return AuthTokens(
            user=self.user,
            access_token="access-token",
            refresh_token="refresh-token",
        )

    async def sign_up(self, email: str, password: str) -> AuthTokens:
        return AuthTokens(
            user=User(id=2, email=email, password_hash="hashed", role=Role.HR),
            access_token="access-token",
            refresh_token="refresh-token",
        )


def _app(service: _FakeAuthenticationService, *, auth_rate_limit: int) -> FastAPI:
    app = FastAPI()
    app.state.authentication_service = service
    app.state.settings = Settings(
        auth_rate_limit=auth_rate_limit,
        auth_rate_limit_window_seconds=60.0,
    )
    register_iam_exception_handlers(app)
    register_authentication_exception_handlers(app)
    app.include_router(auth_router)
    return app


async def test_sign_up_returns_429_after_rate_limit() -> None:
    app = _app(_FakeAuthenticationService(), auth_rate_limit=2)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        responses = [
            await client.post(
                "/auth/sign-up",
                json={"email": f"new{i}@example.com", "password": "password123"},
            )
            for i in range(3)
        ]

    assert [response.status_code for response in responses] == [201, 201, 429]
    body = responses[2].json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Too Many Requests"
    assert body["status"] == 429


async def test_sign_in_returns_429_after_rate_limit() -> None:
    app = _app(_FakeAuthenticationService(), auth_rate_limit=2)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        responses = [
            await client.post(
                "/auth/sign-in",
                json={"email": "hr@talotrace.ai", "password": "password123"},
            )
            for _ in range(3)
        ]

    assert [response.status_code for response in responses] == [200, 200, 429]


async def test_sign_up_rate_limit_is_keyed_by_email() -> None:
    app = _app(_FakeAuthenticationService(), auth_rate_limit=1)
    transport_a = ASGITransport(app=app, client=("1.2.3.4", 1))
    transport_b = ASGITransport(app=app, client=("5.6.7.8", 2))
    transport_c = ASGITransport(app=app, client=("9.9.9.9", 3))

    async with (
        AsyncClient(transport=transport_a, base_url="http://test") as client_a,
        AsyncClient(transport=transport_b, base_url="http://test") as client_b,
        AsyncClient(transport=transport_c, base_url="http://test") as client_c,
    ):
        first = await client_a.post(
            "/auth/sign-up",
            json={"email": "same@example.com", "password": "password123"},
        )
        second = await client_b.post(
            "/auth/sign-up",
            json={"email": "same@example.com", "password": "password123"},
        )
        third = await client_c.post(
            "/auth/sign-up",
            json={"email": "other@example.com", "password": "password123"},
        )

    assert first.status_code == 201
    assert second.status_code == 429  # same email from a different IP is still limited
    assert third.status_code == 201  # different email from a fresh IP is allowed
