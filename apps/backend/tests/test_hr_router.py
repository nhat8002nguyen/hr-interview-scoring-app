from datetime import UTC, datetime

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.candidates.application.ports import ScoringSnapshot
from api.candidates.domain.entities import Answer, Candidate
from api.candidates.domain.exceptions import AnswerNotFoundError, CandidateNotFoundError
from api.candidates.presentation.errors import register_candidates_exception_handlers
from api.candidates.presentation.hr_router import hr_router
from api.catalog.domain.entities import Question
from api.catalog.domain.exceptions import QuestionNotFoundError
from api.catalog.presentation.errors import register_catalog_exception_handlers
from api.config import Settings
from iam import ActiveUserData, JwtService, Role, register_iam_exception_handlers

SECRET = "test-secret-key-at-least-32-bytes"

QUESTION_1 = Question(
    id=1,
    code="Q1",
    sort_order=1,
    prompt="Prompt 1",
    grading_guide={"1": "Bad", "2": "Ok", "3": "Good", "4": "Great"},
)
QUESTION_2 = Question(
    id=2,
    code="Q2",
    sort_order=2,
    prompt="Prompt 2",
    grading_guide={"1": "Bad", "2": "Ok", "3": "Good", "4": "Great"},
)

SUBMITTED_AT = datetime(2026, 9, 14, 10, 15, 0, tzinfo=UTC)
SCORED_AT = datetime(2026, 9, 14, 10, 16, 0, tzinfo=UTC)
SUBMITTED_AT_ISO = "2026-09-14T10:15:00Z"
SCORED_AT_ISO = "2026-09-14T10:16:00Z"


class FakeCandidatesService:
    def __init__(self, candidates: list[Candidate]) -> None:
        self._candidates = {candidate.id: candidate for candidate in candidates}
        self._next_id = max(self._candidates, default=0) + 1

    async def list_candidates_for_role(self, role_id: int) -> list[Candidate]:
        return [c for c in self._candidates.values() if c.role_id == role_id]

    async def get_candidate(self, candidate_id: int) -> Candidate:
        candidate = self._candidates.get(candidate_id)
        if candidate is None:
            raise CandidateNotFoundError(candidate_id)
        return candidate

    async def create_candidate(
        self,
        *,
        name: str,
        email: str,
        role_id: int,
        owner_id: int,
        external_ref: str | None = None,
    ) -> Candidate:
        if any(c.email == email for c in self._candidates.values()):
            from api.candidates.domain.exceptions import CandidateAlreadyExistsError

            raise CandidateAlreadyExistsError(email)
        candidate = Candidate(
            id=self._next_id,
            name=name,
            email=email,
            role_id=role_id,
            owner_id=owner_id,
            session_token="generated-token",
            external_ref=external_ref,
            created_at=datetime.now(UTC),
        )
        self._candidates[candidate.id] = candidate
        self._next_id += 1
        return candidate


class FakeAnswersService:
    def __init__(
        self,
        answers: list[Answer] | None = None,
        audio: dict[int, tuple[bytes, str]] | None = None,
    ) -> None:
        self._answers = {answer.id: answer for answer in answers or []}
        self._audio = audio or {}

    async def list_for_candidate(self, candidate_id: int) -> list[Answer]:
        return [a for a in self._answers.values() if a.candidate_id == candidate_id]

    async def get(self, answer_id: int) -> Answer:
        answer = self._answers.get(answer_id)
        if answer is None:
            raise AnswerNotFoundError(answer_id)
        return answer

    async def read_audio(self, answer_id: int) -> tuple[bytes, str]:
        data = self._audio.get(answer_id)
        if data is None:
            raise AnswerNotFoundError(answer_id)
        return data


class FakeCatalogService:
    def __init__(self, questions: list[Question]) -> None:
        self._questions = questions

    async def list_questions(self) -> list[Question]:
        return list(self._questions)

    async def get_question(self, question_id: int) -> Question:
        question = next((q for q in self._questions if q.id == question_id), None)
        if question is None:
            raise QuestionNotFoundError(question_id)
        return question


class FakeScoringReader:
    def __init__(self, snapshots: dict[int, ScoringSnapshot] | None = None) -> None:
        self._snapshots = snapshots or {}

    async def get_snapshot(self, answer_id: int) -> ScoringSnapshot | None:
        return self._snapshots.get(answer_id)


def _candidate(candidate_id: int, name: str, token: str, *, role_id: int = 1) -> Candidate:
    return Candidate(
        id=candidate_id,
        name=name,
        email=f"candidate{candidate_id}@example.com",
        role_id=role_id,
        owner_id=1,
        session_token=token,
        external_ref=None,
        created_at=SUBMITTED_AT,
    )


def _answer(
    answer_id: int,
    candidate_id: int,
    question_id: int,
    *,
    answer_type: str = "text",
    text: str | None = "hello",
) -> Answer:
    return Answer(
        id=answer_id,
        candidate_id=candidate_id,
        question_id=question_id,
        answer_type=answer_type,
        text=text,
        audio_key=None,
        content_hash="hash",
        version=1,
        external_ref=None,
        submitted_at=SUBMITTED_AT,
    )


def _snapshot(
    *,
    status: str = "scored",
    suggested_score: int | None = 3,
    suggested_reasoning: str | None = "Candidate described measurable impact.",
    final_score: int | None = 3,
    override_reason: str | None = None,
    overridden_by: int | None = None,
    attempt_count: int = 1,
    last_error: str | None = None,
    scored_at: datetime | None = SCORED_AT,
) -> ScoringSnapshot:
    return ScoringSnapshot(
        status=status,
        suggested_score=suggested_score,
        suggested_reasoning=suggested_reasoning,
        final_score=final_score,
        override_reason=override_reason,
        overridden_by=overridden_by,
        attempt_count=attempt_count,
        last_error=last_error,
        scored_at=scored_at,
    )


def _app(
    candidates: FakeCandidatesService,
    answers: FakeAnswersService,
    catalog: FakeCatalogService,
    scoring: FakeScoringReader,
    *,
    candidate_web_origin: str = "https://candidate.example.com",
) -> tuple[FastAPI, JwtService]:
    jwt_service = JwtService(secret=SECRET)
    settings = Settings(candidate_web_origin=candidate_web_origin)
    app = FastAPI()
    app.state.jwt_service = jwt_service
    app.state.settings = settings
    app.state.candidates_service = candidates
    app.state.answers_service = answers
    app.state.catalog_service = catalog
    app.state.scoring_reader = scoring
    register_iam_exception_handlers(app)
    register_catalog_exception_handlers(app)
    register_candidates_exception_handlers(app)
    app.include_router(hr_router)
    return app, jwt_service


def _token(jwt_service: JwtService, role: Role = Role.HR) -> str:
    return jwt_service.sign_access_token(
        ActiveUserData(sub=1, email="hr@example.com", role=role),
    )


def _headers(jwt_service: JwtService, role: Role = Role.HR) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(jwt_service, role)}"}


async def test_list_candidates_for_role() -> None:
    candidate = _candidate(12, "Nhi Tran", "tok-12")
    answer = _answer(31, 12, 1)
    app, jwt_service = _app(
        FakeCandidatesService([candidate]),
        FakeAnswersService(answers=[answer]),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
        FakeScoringReader({31: _snapshot()}),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/hr/roles/1/candidates",
            headers=_headers(jwt_service),
        )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 12,
            "name": "Nhi Tran",
            "email": "candidate12@example.com",
            "answer_progress": {"answered": 1, "total": 2},
            "answers": [
                {
                    "id": 31,
                    "question_id": 1,
                    "question_code": "Q1",
                    "answer_type": "text",
                    "version": 1,
                    "scoring": {
                        "status": "scored",
                        "suggested_score": 3,
                        "final_score": 3,
                        "override_reason": None,
                    },
                }
            ],
        }
    ]


async def test_get_candidate_detail_has_link() -> None:
    candidate = _candidate(12, "Nhi Tran", "tok-12")
    answer = _answer(31, 12, 1)
    app, jwt_service = _app(
        FakeCandidatesService([candidate]),
        FakeAnswersService(answers=[answer]),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
        FakeScoringReader({31: _snapshot()}),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/hr/candidates/12",
            headers=_headers(jwt_service),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["role_id"] == 1
    assert body["session_token"] == "tok-12"
    assert body["interview_link"] == "https://candidate.example.com/interview/tok-12"
    assert body["answers"][0]["scoring"] == {
        "status": "scored",
        "suggested_score": 3,
        "suggested_reasoning": "Candidate described measurable impact.",
        "final_score": 3,
        "override_reason": None,
        "overridden_by": None,
        "attempt_count": 1,
        "last_error": None,
        "scored_at": SCORED_AT_ISO,
    }


async def test_create_candidate_201() -> None:
    app, jwt_service = _app(
        FakeCandidatesService([]),
        FakeAnswersService(),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
        FakeScoringReader(),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/hr/candidates",
            headers=_headers(jwt_service),
            json={"name": "Nhi Tran", "email": "nhi@example.com", "role_id": 1},
        )

    assert response.status_code == 201
    assert response.json() == {
        "id": 1,
        "name": "Nhi Tran",
        "email": "nhi@example.com",
        "role_id": 1,
        "session_token": "generated-token",
        "interview_link": "https://candidate.example.com/interview/generated-token",
    }


async def test_create_candidate_duplicate_email_409() -> None:
    app, jwt_service = _app(
        FakeCandidatesService([]),
        FakeAnswersService(),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
        FakeScoringReader(),
    )
    payload = {"name": "Nhi Tran", "email": "nhi@example.com", "role_id": 1}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/hr/candidates",
            headers=_headers(jwt_service),
            json=payload,
        )
        second = await client.post(
            "/hr/candidates",
            headers=_headers(jwt_service),
            json=payload,
        )

    assert first.status_code == 201
    assert second.status_code == 409
    body = second.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Conflict"
    assert body["status"] == 409


async def test_get_answer_detail_has_grading_guide() -> None:
    answer = _answer(31, 12, 1)
    app, jwt_service = _app(
        FakeCandidatesService([]),
        FakeAnswersService(answers=[answer]),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
        FakeScoringReader({31: _snapshot()}),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/hr/answers/31",
            headers=_headers(jwt_service),
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
            "final_score": 3,
            "override_reason": None,
            "overridden_by": None,
            "attempt_count": 1,
            "last_error": None,
            "scored_at": SCORED_AT_ISO,
        },
    }


async def test_get_audio_streams() -> None:
    audio_answer = _answer(5, 12, 1, answer_type="audio", text=None)
    text_answer = _answer(6, 12, 2, answer_type="text", text="hello")
    app, jwt_service = _app(
        FakeCandidatesService([]),
        FakeAnswersService(
            answers=[audio_answer, text_answer],
            audio={5: (b"\x00\x01audio", "audio/mp4")},
        ),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
        FakeScoringReader(),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        audio_response = await client.get(
            "/hr/answers/5/audio",
            headers=_headers(jwt_service),
        )
        missing_response = await client.get(
            "/hr/answers/6/audio",
            headers=_headers(jwt_service),
        )

    assert audio_response.status_code == 200
    assert audio_response.headers["content-type"] == "audio/mp4"
    assert audio_response.content == b"\x00\x01audio"

    assert missing_response.status_code == 404
    body = missing_response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Not Found"
    assert body["status"] == 404


async def test_hr_requires_authentication() -> None:
    app, _ = _app(
        FakeCandidatesService([]),
        FakeAnswersService(),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
        FakeScoringReader(),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/hr/roles/1/candidates")

    assert response.status_code == 401


async def test_hr_requires_hr_role() -> None:
    app, jwt_service = _app(
        FakeCandidatesService([]),
        FakeAnswersService(),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
        FakeScoringReader(),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/hr/roles/1/candidates",
            headers=_headers(jwt_service, Role.REGULAR),
        )

    assert response.status_code == 403
