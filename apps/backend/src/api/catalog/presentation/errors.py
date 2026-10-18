from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.catalog.domain.exceptions import QuestionNotFoundError, RoleNotFoundError


def register_catalog_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(QuestionNotFoundError)
    async def question_not_found(_: Request, exc: QuestionNotFoundError) -> JSONResponse:
        return _problem(404, "Not Found", str(exc))

    @app.exception_handler(RoleNotFoundError)
    async def role_not_found(_: Request, exc: RoleNotFoundError) -> JSONResponse:
        return _problem(404, "Not Found", str(exc))


def _problem(status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"type": "about:blank", "title": title, "status": status, "detail": detail},
    )
