from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.auth.domain.exceptions import (
    EmailAlreadyExistsError,
    UserNotFoundError,
    WeakPasswordError,
)


def register_authentication_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(UserNotFoundError)
    async def user_not_found(_: Request, exc: UserNotFoundError) -> JSONResponse:
        return _problem(404, "Not Found", str(exc))

    @app.exception_handler(EmailAlreadyExistsError)
    async def email_already_exists(_: Request, exc: EmailAlreadyExistsError) -> JSONResponse:
        return _problem(409, "Conflict", str(exc))

    @app.exception_handler(WeakPasswordError)
    async def weak_password(_: Request, exc: WeakPasswordError) -> JSONResponse:
        return _problem(422, "Unprocessable Entity", str(exc))


def _problem(status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"type": "about:blank", "title": title, "status": status, "detail": detail},
    )
