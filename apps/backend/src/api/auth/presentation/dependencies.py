from typing import Annotated, cast

from fastapi import Depends, Request

from api.auth.application.rate_limit import RateLimiter
from api.auth.application.service import AuthenticationService
from api.config import Settings


async def get_authentication_service(request: Request) -> AuthenticationService:
    return cast(AuthenticationService, request.app.state.authentication_service)


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        settings = cast(Settings, request.app.state.settings)
        limiter = RateLimiter(
            max_requests=settings.auth_rate_limit,
            window_seconds=settings.auth_rate_limit_window_seconds,
        )
        request.app.state.rate_limiter = limiter
    return limiter


async def rate_limit_sign_in(request: Request) -> None:
    await get_rate_limiter(request).check(f"ip:{_client_ip(request)}")


async def rate_limit_sign_up(request: Request) -> None:
    await get_rate_limiter(request).check(f"ip:{_client_ip(request)}")


def _client_ip(request: Request) -> str:
    if request.client is None or request.client.host is None:
        return "unknown"
    return request.client.host


AuthenticationServiceDep = Annotated[
    AuthenticationService,
    Depends(get_authentication_service),
]
