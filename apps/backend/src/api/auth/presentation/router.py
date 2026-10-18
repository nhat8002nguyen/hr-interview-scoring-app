from fastapi import APIRouter, Depends, status

from api.auth.application.service import AuthTokens
from api.auth.presentation.dependencies import AuthenticationServiceDep
from api.auth.presentation.schemas import (
    AuthTokensResponse,
    CredentialsBody,
    HrUserResponse,
    RefreshTokenBody,
    SignOutBody,
)
from iam import AuthType, require_auth

auth_router = APIRouter(prefix="/auth", tags=["auth"])

_require_none = require_auth(AuthType.NONE)


@auth_router.post(
    "/sign-in",
    response_model=AuthTokensResponse,
    dependencies=[Depends(_require_none)],
)
async def sign_in(
    body: CredentialsBody,
    service: AuthenticationServiceDep,
) -> AuthTokensResponse:
    tokens = await service.sign_in(body.email, body.password)
    return _to_response(tokens)


@auth_router.post(
    "/refresh-tokens",
    response_model=AuthTokensResponse,
    dependencies=[Depends(_require_none)],
)
async def refresh_tokens(
    body: RefreshTokenBody,
    service: AuthenticationServiceDep,
) -> AuthTokensResponse:
    tokens = await service.refresh(body.refresh_token)
    return _to_response(tokens)


@auth_router.post(
    "/sign-out",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_none)],
)
async def sign_out(
    body: SignOutBody,
    service: AuthenticationServiceDep,
) -> None:
    await service.sign_out(body.refresh_token)


def _to_response(tokens: AuthTokens) -> AuthTokensResponse:
    return AuthTokensResponse(
        user=HrUserResponse(
            id=tokens.user.id,
            email=tokens.user.email,
            role=tokens.user.role,
        ),
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
    )
