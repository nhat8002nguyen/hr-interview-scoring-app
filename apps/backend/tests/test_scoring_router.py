from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.candidates.domain.entities import Answer
from api.candidates.domain.exceptions import AnswerNotFoundError
from api.catalog.domain.entities import Question
from api.catalog.domain.exceptions import QuestionNotFoundError
from api.scoring.domain.entities import ScoringJob, ScoringJobSummary
from api.scoring.domain.exceptions import (
    ScoringJobInvalidTransitionError,
    ScoringJobNotFoundError,
)
from api.scoring.presentation.errors import register_scoring_exception_handlers
from api.scoring.presentation.router import scoring_router
from iam import ActiveUserData, JwtService, Role, register_iam_exception_handlers

SECRET = "test-secret-key-at-least-32-bytes"

QUESTION_1 = Question(
    id=1,
    code="Q1",
    sort_order=1,
    prompt="Prompt 1",
    grading_guide={"1": "Bad", "2": "Ok", "3": "Good", "4": "Great"},
)

SUBMITTED_AT = datetime(2026, 9, 14, 10, 15, 0, tzinfo=UTC)
SCORED_AT = datetime(2026, 9, 14, 10, 16, 0, tzinfo=UTC)
CREATED_AT = datetime(2026, 9, 14, 10, 14, 0, tzinfo=UTC)
SUBMITTED_AT_ISO = "2026-09-14T10:15:00Z"
SCORED_AT_ISO = "2026-09-14T10:16:00Z"
CREATED_AT_ISO = "2026-09-14T10:14:00Z"


def _answer(answer_id: int, candidate_id: int, question_id: int) -> Answer:
    return Answer(
        id=answer_id,
        candidate_id=candidate_id,
        question_id=question_id,
        answer_type="text",
        text="hello",
        audio_key=None,
        content_hash="hash",
        version=1,
        external_ref=None,
        submitted_at=SUBMITTED_AT,
    )


def _job(
    job_id: int,
    answer_id: int,
    status: str,
    *,
    suggested_score: int | None = None,
    suggested_reasoning: str | None = None,
    final_score: int | None = None,
    override_reason: str | None = None,
    overridden_by: int | None = None,
    attempt_count: int = 0,
    last_error: str | None = None,
    scored_at: datetime | None = None,
) -> ScoringJob:
    return ScoringJob(
        id=job_id,
        answer_id=answer_id,
        status=status,
        suggested_score=suggested_score,
        suggested_reasoning=suggested_reasoning,
        final_score=final_score,
        override_reason=override_reason,
        overridden_by=overridden_by,
        attempt_count=attempt_count,
        last_error=last_error,
        claimed_at=None,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
        scored_at=scored_at,
    )


class FakeScoringService:
    def __init__(
        self,
        *,
        override_result: ScoringJob | None = None,
        override_error: Exception | None = None,
        jobs: list[ScoringJobSummary] | None = None,
        retry_result: ScoringJob | None = None,
        retry_error: Exception | None = None,
    ) -> None:
        self._override_result = override_result
        self._override_error = override_error
        self._jobs = jobs or []
        self._retry_result = retry_result
        self._retry_error = retry_error
        self.override_calls: list[tuple[int, int, str, int]] = []
        self.list_calls: list[tuple[str | None, int]] = []
        self.retry_calls: list[tuple[int, int]] = []

    async def override_score(
        self,
        answer_id: int,
        *,
        final_score: int,
        override_reason: str,
        overridden_by: int,
    ) -> ScoringJob:
        self.override_calls.append((answer_id, final_score, override_reason, overridden_by))
        if self._override_error is not None:
            raise self._override_error
        if self._override_result is None:
            raise AssertionError("override_result not configured")
        return self._override_result

    async def list_jobs(self, status: str | None, owner_id: int) -> list[ScoringJobSummary]:
        self.list_calls.append((status, owner_id))
        return list(self._jobs)

    async def retry(self, job_id: int, owner_id: int) -> ScoringJob:
        self.retry_calls.append((job_id, owner_id))
        if self._retry_error is not None:
            raise self._retry_error
        if self._retry_result is None:
            raise AssertionError("retry_result not configured")
        return self._retry_result


class FakeAnswersService:
    def __init__(
        self,
        answers: list[Answer] | None = None,
        owners: dict[int, int] | None = None,
    ) -> None:
        self._answers = {answer.id: answer for answer in answers or []}
        self._owners = owners or {}

    async def get_owned(self, answer_id: int, owner_id: int) -> Answer:
        answer = self._answers.get(answer_id)
        if answer is None:
            raise AnswerNotFoundError(answer_id)
        candidate_owner = self._owners.get(answer.candidate_id)
        if candidate_owner is None or candidate_owner != owner_id:
            raise AnswerNotFoundError(answer_id)
        return answer


class FakeCatalogService:
    def __init__(self, questions: list[Question]) -> None:
        self._questions = questions

    async def get_question(self, question_id: int) -> Question:
        question = next((q for q in self._questions if q.id == question_id), None)
        if question is None:
            raise QuestionNotFoundError(question_id)
        return question


def _app(
    scoring: FakeScoringService,
    answers: FakeAnswersService | None = None,
    catalog: FakeCatalogService | None = None,
) -> tuple[FastAPI, JwtService]:
    jwt_service = JwtService(secret=SECRET)
    app = FastAPI()
    app.state.jwt_service = jwt_service
    app.state.scoring_service = scoring
    app.state.answers_service = answers or FakeAnswersService()
    app.state.catalog_service = catalog or FakeCatalogService([QUESTION_1])
    register_iam_exception_handlers(app)
    register_scoring_exception_handlers(app)
    app.include_router(scoring_router)
    return app, jwt_service


def _token(jwt_service: JwtService, role: Role = Role.HR) -> str:
    return jwt_service.sign_access_token(
        ActiveUserData(sub=1, email="hr@example.com", role=role),
    )


def _headers(jwt_service: JwtService, role: Role = Role.HR) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(jwt_service, role)}"}


async def test_override_200() -> None:
    answer = _answer(31, 12, 1)
    job = _job(
        1,
        31,
        "scored",
        suggested_score=3,
        suggested_reasoning="Candidate described measurable impact.",
        final_score=4,
        override_reason="reviewed",
        overridden_by=1,
        attempt_count=1,
        scored_at=SCORED_AT,
    )
    scoring = FakeScoringService(override_result=job)
    app, jwt_service = _app(scoring, FakeAnswersService([answer], owners={12: 1}))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/hr/answers/31/score",
            headers=_headers(jwt_service),
            json={"final_score": 4, "override_reason": "reviewed"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "id": 31,
        "candidate_id": 12,
        "question_id": 1,
        "question_code": "Q1",
        "question_prompt": "Prompt 1",
        "grading_guide": {"1": "Bad", "2": "Ok", "3": "Good", "4": "Great"},
        "answer_type": "text",
        "text": "hello",
        "version": 1,
        "submitted_at": SUBMITTED_AT_ISO,
        "scoring": {
            "status": "scored",
            "suggested_score": 3,
            "suggested_reasoning": "Candidate described measurable impact.",
            "final_score": 4,
            "override_reason": "reviewed",
            "overridden_by": 1,
            "attempt_count": 1,
            "last_error": None,
            "scored_at": SCORED_AT_ISO,
        },
    }
    assert scoring.override_calls == [(31, 4, "reviewed", 1)]


async def test_override_missing_reason_422() -> None:
    scoring = FakeScoringService()
    app, jwt_service = _app(scoring)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/hr/answers/31/score",
            headers=_headers(jwt_service),
            json={"final_score": 4},
        )

    assert response.status_code == 422
    assert scoring.override_calls == []


@pytest.mark.parametrize("final_score", [0, 5, "high"])
async def test_override_bad_score_422(final_score: object) -> None:
    scoring = FakeScoringService()
    app, jwt_service = _app(scoring)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/hr/answers/31/score",
            headers=_headers(jwt_service),
            json={"final_score": final_score, "override_reason": "reviewed"},
        )

    assert response.status_code == 422
    assert scoring.override_calls == []


async def test_override_wrong_status_409() -> None:
    scoring = FakeScoringService(
        override_error=ScoringJobInvalidTransitionError(1, "queued"),
    )
    app, jwt_service = _app(
        scoring, FakeAnswersService([_answer(31, 12, 1)], owners={12: 1})
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/hr/answers/31/score",
            headers=_headers(jwt_service),
            json={"final_score": 4, "override_reason": "reviewed"},
        )

    assert response.status_code == 409
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Conflict"
    assert body["status"] == 409


async def test_list_jobs_filtered() -> None:
    summary = ScoringJobSummary(
        id=51,
        answer_id=31,
        candidate_id=12,
        candidate_name="Nhi Tran",
        question_code="Q1",
        status="failed",
        attempt_count=3,
        last_error="LLM returned invalid output",
        created_at=CREATED_AT,
    )
    scoring = FakeScoringService(jobs=[summary])
    app, jwt_service = _app(scoring)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/hr/scoring-jobs?status=failed",
            headers=_headers(jwt_service),
        )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 51,
            "answer_id": 31,
            "candidate_id": 12,
            "candidate_name": "Nhi Tran",
            "question_code": "Q1",
            "status": "failed",
            "attempt_count": 3,
            "last_error": "LLM returned invalid output",
            "created_at": CREATED_AT_ISO,
        }
    ]
    assert scoring.list_calls == [("failed", 1)]


async def test_retry_200_and_409() -> None:
    retried = _job(1, 31, "queued", attempt_count=3)
    scoring = FakeScoringService(retry_result=retried)
    app, jwt_service = _app(scoring)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ok = await client.post(
            "/hr/scoring-jobs/1/retry",
            headers=_headers(jwt_service),
        )

    assert ok.status_code == 200
    assert ok.json() == {
        "id": 1,
        "answer_id": 31,
        "status": "queued",
        "suggested_score": None,
        "suggested_reasoning": None,
        "final_score": None,
        "override_reason": None,
        "overridden_by": None,
        "attempt_count": 3,
        "last_error": None,
        "scored_at": None,
    }
    assert scoring.retry_calls == [(1, 1)]

    conflict_scoring = FakeScoringService(
        retry_error=ScoringJobInvalidTransitionError(2, "scored"),
    )
    conflict_app, conflict_jwt = _app(conflict_scoring)

    async with AsyncClient(
        transport=ASGITransport(app=conflict_app), base_url="http://test"
    ) as client:
        conflict = await client.post(
            "/hr/scoring-jobs/2/retry",
            headers=_headers(conflict_jwt),
        )

    assert conflict.status_code == 409
    assert conflict.json()["status"] == 409

    missing_scoring = FakeScoringService(retry_error=ScoringJobNotFoundError(3))
    missing_app, missing_jwt = _app(missing_scoring)

    async with AsyncClient(
        transport=ASGITransport(app=missing_app), base_url="http://test"
    ) as client:
        missing = await client.post(
            "/hr/scoring-jobs/3/retry",
            headers=_headers(missing_jwt),
        )

    assert missing.status_code == 404
    assert missing.json()["status"] == 404


async def test_cross_tenant_scoring_job_retry_is_404() -> None:
    scoring = FakeScoringService(retry_error=ScoringJobNotFoundError(7))
    app, jwt_service = _app(scoring)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/hr/scoring-jobs/7/retry",
            headers=_headers(jwt_service),
        )

    assert response.status_code == 404
    assert response.json()["status"] == 404
    assert scoring.retry_calls == [(7, 1)]


async def test_scoring_jobs_list_scopes_by_owner() -> None:
    scoring = FakeScoringService(jobs=[])
    app, jwt_service = _app(scoring)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/hr/scoring-jobs",
            headers=_headers(jwt_service),
        )

    assert response.status_code == 200
    assert response.json() == []
    assert scoring.list_calls == [(None, 1)]


async def test_requires_authentication() -> None:
    app, _ = _app(FakeScoringService())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/hr/scoring-jobs")

    assert response.status_code == 401


async def test_requires_hr_role() -> None:
    app, jwt_service = _app(FakeScoringService())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/hr/scoring-jobs",
            headers=_headers(jwt_service, Role.REGULAR),
        )

    assert response.status_code == 403
