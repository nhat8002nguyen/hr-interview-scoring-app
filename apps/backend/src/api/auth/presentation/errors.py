from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.auth.domain.exceptions import UserNotFoundError


def register_authentication_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(UserNotFoundError)
    async def user_not_found(_: Request, exc: UserNotFoundError) -> JSONResponse:
        return _problem(404, "Not Found", str(exc))


def _problem(status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"type": "about:blank", "title": title, "status": status, "detail": detail},
    )
