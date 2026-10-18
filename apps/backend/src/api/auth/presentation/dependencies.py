from typing import Annotated, cast

from fastapi import Depends, Request

from api.auth.application.service import AuthenticationService


async def get_authentication_service(request: Request) -> AuthenticationService:
    return cast(AuthenticationService, request.app.state.authentication_service)


AuthenticationServiceDep = Annotated[
    AuthenticationService,
    Depends(get_authentication_service),
]
