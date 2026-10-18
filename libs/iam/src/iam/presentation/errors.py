from fastapi import FastAPI
from fastapi.responses import JSONResponse

from iam.domain.exceptions import ForbiddenError, UnauthorizedError


def register_iam_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(UnauthorizedError)
    async def unauthorized(_: object, exc: UnauthorizedError) -> JSONResponse:
        return _problem(401, "Unauthorized", str(exc))

    @app.exception_handler(ForbiddenError)
    async def forbidden(_: object, exc: ForbiddenError) -> JSONResponse:
        return _problem(403, "Forbidden", str(exc))


def _problem(status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"type": "about:blank", "title": title, "status": status, "detail": detail},
    )
