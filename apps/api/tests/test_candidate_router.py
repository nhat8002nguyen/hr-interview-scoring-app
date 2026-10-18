from datetime import UTC, datetime
from hashlib import sha256

from api.candidates.application.service import SubmitResult
from api.candidates.domain.entities import Answer, Candidate
from api.candidates.presentation.candidate_router import candidate_router
from api.candidates.presentation.errors import register_candidates_exception_handlers
from api.catalog.domain.entities import Question, Role
from api.catalog.domain.exceptions import QuestionNotFoundError, RoleNotFoundError
from api.catalog.presentation.errors import register_catalog_exception_handlers
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from iam import register_iam_exception_handlers

ROLE = Role(id=1, name="Backend Engineer")

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
SUBMITTED_AT_ISO = "2026-09-14T10:15:00Z"


class FakeCatalogService:
    def __init__(self, questions: list[Question], role: Role = ROLE) -> None:
        self._questions = questions
        self._role = role

    async def list_questions(self) -> list[Question]:
        return list(self._questions)

    async def get_role(self, role_id: int) -> Role:
        if role_id != self._role.id:
            raise RoleNotFoundError(role_id)
        return self._role


class FakeCandidatesService:
    def __init__(self, candidates: list[Candidate]) -> None:
        self._by_token = {candidate.session_token: candidate for candidate in candidates}

    async def get_by_session_token(self, token: str) -> Candidate | None:
        return self._by_token.get(token)


class FakeAnswersService:
    def __init__(
        self,
        question_ids: set[int],
        answers: list[Answer] | None = None,
    ) -> None:
        self._question_ids = question_ids
        self._answers: dict[tuple[int, int], Answer] = {
            (answer.candidate_id, answer.question_id): answer for answer in answers or []
        }
        self._next_id = max((answer.id for answer in self._answers.values()), default=0) + 1

    async def list_for_candidate(self, candidate_id: int) -> list[Answer]:
        return [answer for answer in self._answers.values() if answer.candidate_id == candidate_id]

    async def submit_text(self, candidate_id: int, question_id: int, text: str) -> SubmitResult:
        if question_id not in self._question_ids:
            raise QuestionNotFoundError(question_id)
        return self._submit(
            candidate_id=candidate_id,
            question_id=question_id,
            answer_type="text",
            text=text,
            content_hash=sha256(text.encode("utf-8")).hexdigest(),
        )

    async def submit_audio(
        self,
        candidate_id: int,
        question_id: int,
        data: bytes,
        filename: str,
    ) -> SubmitResult:
        if question_id not in self._question_ids:
            raise QuestionNotFoundError(question_id)
        return self._submit(
            candidate_id=candidate_id,
            question_id=question_id,
            answer_type="audio",
            text=None,
            content_hash=sha256(data).hexdigest(),
        )

    def _submit(
        self,
        *,
        candidate_id: int,
        question_id: int,
        answer_type: str,
        text: str | None,
        content_hash: str,
    ) -> SubmitResult:
        key = (candidate_id, question_id)
        existing = self._answers.get(key)
        if existing is not None and existing.content_hash == content_hash:
            return SubmitResult(status="received", unchanged=True, answer=existing)
        answer = Answer(
            id=existing.id if existing else self._next_id,
            candidate_id=candidate_id,
            question_id=question_id,
            answer_type=answer_type,
            text=text,
            audio_key=None,
            content_hash=content_hash,
            version=(existing.version + 1) if existing else 1,
            external_ref=None,
            submitted_at=SUBMITTED_AT,
        )
        if existing is None:
            self._next_id += 1
        self._answers[key] = answer
        return SubmitResult(status="received", unchanged=False, answer=answer)


def _candidate(candidate_id: int, name: str, token: str) -> Candidate:
    return Candidate(
        id=candidate_id,
        name=name,
        email=f"candidate{candidate_id}@example.com",
        role_id=1,
        session_token=token,
        external_ref=None,
        created_at=SUBMITTED_AT,
    )


def _answer(
    answer_id: int,
    candidate_id: int,
    question_id: int,
    *,
    text: str | None = "hello",
    answer_type: str = "text",
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


def _app(
    candidates: FakeCandidatesService,
    answers: FakeAnswersService,
    catalog: FakeCatalogService,
) -> FastAPI:
    app = FastAPI()
    app.state.candidates_service = candidates
    app.state.answers_service = answers
    app.state.catalog_service = catalog
    register_iam_exception_handlers(app)
    register_catalog_exception_handlers(app)
    register_candidates_exception_handlers(app)
    app.include_router(candidate_router)
    return app


def _transport(app: FastAPI) -> ASGITransport:
    return ASGITransport(app=app)


def _assert_no_grades(value: object) -> None:
    forbidden = {"grading_guide", "suggested_score", "final_score"}
    if isinstance(value, dict):
        for key in value:
            assert key not in forbidden, f"candidate area leaked {key}"
            _assert_no_grades(value[key])
    elif isinstance(value, list):
        for item in value:
            _assert_no_grades(item)


async def test_interview_returns_questions_without_grades() -> None:
    candidate = _candidate(1, "Nhi Tran", "token-a")
    answer = _answer(10, 1, 1)
    app = _app(
        FakeCandidatesService([candidate]),
        FakeAnswersService({1, 2}, answers=[answer]),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
    )

    async with AsyncClient(transport=_transport(app), base_url="http://test") as client:
        response = await client.get(
            "/candidate/interview",
            headers={"X-Candidate-Token": "token-a"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["candidate"] == {"id": 1, "name": "Nhi Tran", "role": "Backend Engineer"}
    assert body["progress"] == {"answered": 1, "total": 2}
    assert body["questions"] == [
        {
            "id": 1,
            "code": "Q1",
            "sort_order": 1,
            "prompt": "Prompt 1",
            "answer": {
                "answer_type": "text",
                "text": "hello",
                "version": 1,
                "submitted_at": SUBMITTED_AT_ISO,
            },
        },
        {
            "id": 2,
            "code": "Q2",
            "sort_order": 2,
            "prompt": "Prompt 2",
            "answer": None,
        },
    ]
    _assert_no_grades(body)


async def test_submit_text_201_and_received() -> None:
    candidate = _candidate(1, "Nhi Tran", "token-a")
    app = _app(
        FakeCandidatesService([candidate]),
        FakeAnswersService({1, 2}),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
    )

    async with AsyncClient(transport=_transport(app), base_url="http://test") as client:
        response = await client.post(
            "/candidate/interview/answers/1",
            headers={"X-Candidate-Token": "token-a"},
            json={"answer_type": "text", "text": "my answer"},
        )

    assert response.status_code == 201
    assert response.json() == {
        "status": "received",
        "unchanged": False,
        "answer": {
            "answer_type": "text",
            "version": 1,
            "submitted_at": SUBMITTED_AT_ISO,
        },
    }


async def test_submit_unchanged_200() -> None:
    candidate = _candidate(1, "Nhi Tran", "token-a")
    app = _app(
        FakeCandidatesService([candidate]),
        FakeAnswersService({1, 2}),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
    )

    headers = {"X-Candidate-Token": "token-a"}
    payload = {"answer_type": "text", "text": "my answer"}
    async with AsyncClient(transport=_transport(app), base_url="http://test") as client:
        first = await client.post(
            "/candidate/interview/answers/1",
            headers=headers,
            json=payload,
        )
        second = await client.post(
            "/candidate/interview/answers/1",
            headers=headers,
            json=payload,
        )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == {
        "status": "received",
        "unchanged": True,
        "answer": {
            "answer_type": "text",
            "version": 1,
            "submitted_at": SUBMITTED_AT_ISO,
        },
    }


async def test_submit_empty_text_422() -> None:
    candidate = _candidate(1, "Nhi Tran", "token-a")
    app = _app(
        FakeCandidatesService([candidate]),
        FakeAnswersService({1, 2}),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
    )

    async with AsyncClient(transport=_transport(app), base_url="http://test") as client:
        response = await client.post(
            "/candidate/interview/answers/1",
            headers={"X-Candidate-Token": "token-a"},
            json={"answer_type": "text", "text": "   "},
        )

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Unprocessable Entity"
    assert body["status"] == 422


async def test_submit_non_text_answer_type_422() -> None:
    candidate = _candidate(1, "Nhi Tran", "token-a")
    app = _app(
        FakeCandidatesService([candidate]),
        FakeAnswersService({1, 2}),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
    )

    async with AsyncClient(transport=_transport(app), base_url="http://test") as client:
        response = await client.post(
            "/candidate/interview/answers/1",
            headers={"X-Candidate-Token": "token-a"},
            json={"answer_type": "audio", "text": "hello"},
        )

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Unprocessable Entity"
    assert body["status"] == 422


async def test_submit_unknown_question_404() -> None:
    candidate = _candidate(1, "Nhi Tran", "token-a")
    app = _app(
        FakeCandidatesService([candidate]),
        FakeAnswersService({1, 2}),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
    )

    async with AsyncClient(transport=_transport(app), base_url="http://test") as client:
        response = await client.post(
            "/candidate/interview/answers/99",
            headers={"X-Candidate-Token": "token-a"},
            json={"answer_type": "text", "text": "hello"},
        )

    assert response.status_code == 404
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Not Found"
    assert body["status"] == 404


async def test_submit_audio_201() -> None:
    candidate = _candidate(1, "Nhi Tran", "token-a")
    app = _app(
        FakeCandidatesService([candidate]),
        FakeAnswersService({1, 2}),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
    )

    async with AsyncClient(transport=_transport(app), base_url="http://test") as client:
        response = await client.post(
            "/candidate/interview/answers/1/audio",
            headers={"X-Candidate-Token": "token-a"},
            files={"file": ("clip.m4a", b"\x00audio", "audio/mp4")},
        )

    assert response.status_code == 201
    assert response.json() == {
        "status": "received",
        "unchanged": False,
        "answer": {
            "answer_type": "audio",
            "version": 1,
            "submitted_at": SUBMITTED_AT_ISO,
        },
    }


async def test_submit_audio_empty_file_422() -> None:
    candidate = _candidate(1, "Nhi Tran", "token-a")
    app = _app(
        FakeCandidatesService([candidate]),
        FakeAnswersService({1, 2}),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
    )

    async with AsyncClient(transport=_transport(app), base_url="http://test") as client:
        response = await client.post(
            "/candidate/interview/answers/1/audio",
            headers={"X-Candidate-Token": "token-a"},
            files={"file": ("clip.m4a", b"", "audio/mp4")},
        )

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Unprocessable Entity"
    assert body["status"] == 422


async def test_unknown_token_401() -> None:
    app = _app(
        FakeCandidatesService([_candidate(1, "Nhi Tran", "token-a")]),
        FakeAnswersService({1, 2}),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
    )

    async with AsyncClient(transport=_transport(app), base_url="http://test") as client:
        response = await client.get(
            "/candidate/interview",
            headers={"X-Candidate-Token": "nope"},
        )

    assert response.status_code == 401
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Unauthorized"
    assert body["status"] == 401


async def test_missing_token_401() -> None:
    app = _app(
        FakeCandidatesService([_candidate(1, "Nhi Tran", "token-a")]),
        FakeAnswersService({1, 2}),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
    )

    async with AsyncClient(transport=_transport(app), base_url="http://test") as client:
        response = await client.get("/candidate/interview")

    assert response.status_code == 401


async def test_no_cross_candidate_read() -> None:
    candidate_a = _candidate(1, "Alice", "token-a")
    candidate_b = _candidate(2, "Bob", "token-b")
    answer_b = _answer(10, 2, 1, text="Bob's secret answer")
    app = _app(
        FakeCandidatesService([candidate_a, candidate_b]),
        FakeAnswersService({1, 2}, answers=[answer_b]),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
    )

    async with AsyncClient(transport=_transport(app), base_url="http://test") as client:
        response = await client.get(
            "/candidate/interview",
            headers={"X-Candidate-Token": "token-a"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["candidate"] == {"id": 1, "name": "Alice", "role": "Backend Engineer"}
    assert body["progress"] == {"answered": 0, "total": 2}
    assert [question["answer"] for question in body["questions"]] == [None, None]
