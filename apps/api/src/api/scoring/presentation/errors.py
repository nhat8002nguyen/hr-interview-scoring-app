from fastapi import FastAPI
from fastapi.responses import JSONResponse

from api.candidates.domain.exceptions import AnswerNotFoundError
from api.scoring.domain.exceptions import (
    ScoringJobInvalidTransitionError,
    ScoringJobNotFoundError,
)


def register_scoring_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ScoringJobNotFoundError)
    async def scoring_job_not_found(
        _: object,
        exc: ScoringJobNotFoundError,
    ) -> JSONResponse:
        return _problem(404, "Not Found", str(exc))

    @app.exception_handler(ScoringJobInvalidTransitionError)
    async def scoring_job_invalid_transition(
        _: object,
        exc: ScoringJobInvalidTransitionError,
    ) -> JSONResponse:
        return _problem(409, "Conflict", str(exc))

    @app.exception_handler(AnswerNotFoundError)
    async def answer_not_found(_: object, exc: AnswerNotFoundError) -> JSONResponse:
        return _problem(404, "Not Found", str(exc))


def _problem(status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"type": "about:blank", "title": title, "status": status, "detail": detail},
    )
