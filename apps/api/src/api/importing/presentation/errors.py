from fastapi import FastAPI
from fastapi.responses import JSONResponse

from api.importing.domain import InvalidImportError


def register_importing_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(InvalidImportError)
    async def invalid_import(_: object, exc: InvalidImportError) -> JSONResponse:
        return _problem(400, "Bad Request", str(exc))


def _problem(status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"type": "about:blank", "title": title, "status": status, "detail": detail},
    )
