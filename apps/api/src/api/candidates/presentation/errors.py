from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.candidates.domain.exceptions import (
    AnswerNotFoundError,
    CandidateAlreadyExistsError,
    CandidateNotFoundError,
)


class CandidateValidationError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def register_candidates_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(CandidateNotFoundError)
    async def candidate_not_found(_: Request, exc: CandidateNotFoundError) -> JSONResponse:
        return _problem(404, "Not Found", str(exc))

    @app.exception_handler(CandidateAlreadyExistsError)
    async def candidate_exists(_: Request, exc: CandidateAlreadyExistsError) -> JSONResponse:
        return _problem(409, "Conflict", str(exc))

    @app.exception_handler(AnswerNotFoundError)
    async def answer_not_found(_: Request, exc: AnswerNotFoundError) -> JSONResponse:
        return _problem(404, "Not Found", str(exc))

    @app.exception_handler(CandidateValidationError)
    async def candidate_validation_error(
        _: Request,
        exc: CandidateValidationError,
    ) -> JSONResponse:
        return _problem(422, "Unprocessable Entity", exc.detail)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        detail = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        return _problem(422, "Unprocessable Entity", detail)


def _problem(status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"type": "about:blank", "title": title, "status": status, "detail": detail},
    )
