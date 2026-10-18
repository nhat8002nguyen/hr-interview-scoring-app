import re
from collections.abc import Awaitable, Callable
from typing import Annotated, cast

from fastapi import Depends, Request

from iam.application.jwt import JwtService
from iam.domain.entities import AccessScope, ActiveUserData, AuthType, Role
from iam.domain.exceptions import ForbiddenError, UnauthorizedError
from iam.domain.ports import ApiKeyValidatorProtocol

_BEARER = re.compile(r"^Bearer\s+(.+)$", re.IGNORECASE)


def require_auth(
    *auth_types: AuthType,
) -> Callable[[Request], Awaitable[ActiveUserData | None]]:
    allowed = auth_types or (AuthType.JWT,)

    async def dependency(request: Request) -> ActiveUserData | None:
        if allowed == (AuthType.NONE,):
            request.state.user = None
            return None
        errors: list[str] = []
        bearer = _bearer_token(request)
        api_key = _api_key(request)
        if AuthType.NONE in allowed and bearer is None and api_key is None:
            request.state.user = None
            return None
        for auth_type in allowed:
            if auth_type == AuthType.NONE:
                continue
            try:
                user = await _authenticate(request, auth_type, bearer, api_key)
            except UnauthorizedError as exc:
                errors.append(str(exc))
                continue
            if user is None:
                errors.append("Invalid credentials")
                continue
            request.state.user = user
            return user
        raise UnauthorizedError(" || ".join(errors) or "Unauthorized")

    return dependency


def require_roles(*roles: Role) -> Callable[[ActiveUserData], Awaitable[ActiveUserData]]:
    async def dependency(user: CurrentUserDep) -> ActiveUserData:
        if user.role not in roles:
            raise ForbiddenError("Insufficient role permissions")
        return user

    return dependency


async def get_current_user(request: Request) -> ActiveUserData:
    existing = getattr(request.state, "user", None)
    if isinstance(existing, ActiveUserData):
        return existing
    user = await require_auth(AuthType.JWT)(request)
    if user is None:
        raise UnauthorizedError("Unauthorized")
    return user


def get_access_scope(user: CurrentUserDep) -> AccessScope:
    return user.to_access_scope()


CurrentUserDep = Annotated[ActiveUserData, Depends(get_current_user)]
CurrentAccessScopeDep = Annotated[AccessScope, Depends(get_access_scope)]


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if header is None:
        return None
    match = _BEARER.match(header)
    if match is None:
        return None
    return match.group(1)


def _api_key(request: Request) -> str | None:
    return request.headers.get("api_key") or request.headers.get("x-api-key")


async def _authenticate(
    request: Request,
    auth_type: AuthType,
    bearer: str | None,
    api_key: str | None,
) -> ActiveUserData | None:
    if auth_type == AuthType.JWT:
        if bearer is None:
            raise UnauthorizedError("Missing Authorization header")
        return _jwt_service(request).verify_access_token(bearer)
    if auth_type == AuthType.API_KEY:
        if api_key is None:
            raise UnauthorizedError("Missing API key")
        validator = getattr(request.app.state, "api_key_validator", None)
        if validator is None:
            raise UnauthorizedError("API key authentication is not configured")
        return await cast(ApiKeyValidatorProtocol, validator).validate_api_key(api_key)
    raise UnauthorizedError("Unsupported authentication type")


def _jwt_service(request: Request) -> JwtService:
    service = getattr(request.app.state, "jwt_service", None)
    if not isinstance(service, JwtService):
        raise UnauthorizedError("JWT authentication is not configured")
    return service
