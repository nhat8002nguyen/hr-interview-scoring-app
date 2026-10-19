from datetime import UTC, datetime
from hashlib import sha256

import pytest

from api.candidates.application.service import AnswersService, CandidatesService
from api.candidates.domain.entities import Answer, Candidate
from api.candidates.domain.exceptions import (
    AttemptsExhaustedError,
    CandidateAlreadyExistsError,
)
from api.candidates.infrastructure.storage import LocalFileStorage
from api.catalog.domain.entities import Question
from api.catalog.domain.exceptions import QuestionNotFoundError


class FakeCandidateRepository:
    def __init__(self, candidates: list[Candidate] | None = None) -> None:
        self._candidates = {candidate.id: candidate for candidate in candidates or []}
        self._next_id = max(self._candidates, default=0) + 1

    async def add(self, candidate: Candidate) -> Candidate:
        stored = Candidate(
            id=self._next_id,
            name=candidate.name,
            email=candidate.email,
            role_id=candidate.role_id,
            owner_id=candidate.owner_id,
            session_token=candidate.session_token,
            external_ref=candidate.external_ref,
            created_at=candidate.created_at,
        )
        self._candidates[stored.id] = stored
        self._next_id += 1
        return stored

    async def get(self, candidate_id: int) -> Candidate | None:
        return self._candidates.get(candidate_id)

    async def get_by_email(self, email: str) -> Candidate | None:
        return next((c for c in self._candidates.values() if c.email == email), None)

    async def get_by_session_token(self, session_token: str) -> Candidate | None:
        return next(
            (c for c in self._candidates.values() if c.session_token == session_token),
            None,
        )

    async def get_by_external_ref(self, external_ref: str) -> Candidate | None:
        return next(
            (c for c in self._candidates.values() if c.external_ref == external_ref),
            None,
        )

    async def list_by_role(self, role_id: int) -> list[Candidate]:
        return [c for c in self._candidates.values() if c.role_id == role_id]

    async def count_by_role(self, role_id: int) -> int:
        return sum(1 for c in self._candidates.values() if c.role_id == role_id)


class FakeAnswerRepository:
    def __init__(self, answers: list[Answer] | None = None) -> None:
        self._answers: dict[tuple[int, int], Answer] = {
            (answer.candidate_id, answer.question_id): answer for answer in answers or []
        }
        self._next_id = max((answer.id for answer in self._answers.values()), default=0) + 1
        self.block_next_upsert = False

    async def upsert(self, answer: Answer, *, max_submissions: int | None) -> tuple[Answer, bool]:
        key = (answer.candidate_id, answer.question_id)
        existing = self._answers.get(key)
        if self.block_next_upsert:
            self.block_next_upsert = False
            if existing is not None:
                return existing, False
        changed = existing is None or existing.content_hash != answer.content_hash
        if (
            existing is not None
            and changed
            and max_submissions is not None
            and existing.version >= max_submissions
        ):
            return existing, False
        if existing is None:
            stored = Answer(
                id=self._next_id,
                candidate_id=answer.candidate_id,
                question_id=answer.question_id,
                answer_type=answer.answer_type,
                text=answer.text,
                audio_key=answer.audio_key,
                content_hash=answer.content_hash,
                version=1,
                external_ref=answer.external_ref,
                submitted_at=answer.submitted_at,
            )
            self._next_id += 1
        elif changed:
            stored = Answer(
                id=existing.id,
                candidate_id=answer.candidate_id,
                question_id=answer.question_id,
                answer_type=answer.answer_type,
                text=answer.text,
                audio_key=answer.audio_key,
                content_hash=answer.content_hash,
                version=existing.version + 1,
                external_ref=answer.external_ref,
                submitted_at=answer.submitted_at,
            )
        else:
            stored = existing
        self._answers[key] = stored
        return stored, changed

    async def get(self, answer_id: int) -> Answer | None:
        return next((a for a in self._answers.values() if a.id == answer_id), None)

    async def get_active(self, candidate_id: int, question_id: int) -> Answer | None:
        return self._answers.get((candidate_id, question_id))

    async def list_for_candidate(self, candidate_id: int) -> list[Answer]:
        return [a for a in self._answers.values() if a.candidate_id == candidate_id]

    async def get_by_external_ref(self, external_ref: str) -> Answer | None:
        return next(
            (a for a in self._answers.values() if a.external_ref == external_ref),
            None,
        )


class FakeCandidatesUnitOfWork:
    def __init__(
        self,
        candidates: FakeCandidateRepository,
        answers: FakeAnswerRepository,
    ) -> None:
        self.candidates = candidates
        self.answers = answers

    async def __aenter__(self) -> FakeCandidatesUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        return None


class FakeScoringJobPort:
    def __init__(self) -> None:
        self.reset_calls: list[tuple[int, str]] = []

    async def reset_for_answer(self, answer_id: int, *, status: str) -> None:
        self.reset_calls.append((answer_id, status))


class FakeCatalogService:
    def __init__(self, question_ids: set[int]) -> None:
        self._question_ids = question_ids

    async def get_question(self, question_id: int) -> Question:
        if question_id not in self._question_ids:
            raise QuestionNotFoundError(question_id)
        return Question(
            id=question_id,
            code=f"Q{question_id}",
            sort_order=question_id,
            prompt=f"Prompt {question_id}",
            grading_guide={"1": "Bad", "4": "Great"},
        )


def _answers_service(
    tmp_path,
    *,
    question_ids: set[int] | None = None,
    answers: list[Answer] | None = None,
    max_submissions: int = 3,
) -> tuple[AnswersService, FakeAnswerRepository, FakeScoringJobPort, LocalFileStorage]:
    candidates = FakeCandidateRepository()
    answers_repo = FakeAnswerRepository(answers)
    questions = FakeCatalogService(question_ids or set())
    scoring_jobs = FakeScoringJobPort()
    file_storage = LocalFileStorage(tmp_path)
    service = AnswersService(
        lambda: FakeCandidatesUnitOfWork(candidates, answers_repo),
        questions,
        scoring_jobs,
        file_storage,
        max_submissions=max_submissions,
    )
    return service, answers_repo, scoring_jobs, file_storage


async def test_create_candidate_generates_token_and_conflicts_on_email() -> None:
    candidates = FakeCandidateRepository()
    service = CandidatesService(
        lambda: FakeCandidatesUnitOfWork(candidates, FakeAnswerRepository()),
        lambda: "token-1",
    )

    created = await service.create_candidate(
        name="Ada",
        email="ada@example.com",
        role_id=2,
        owner_id=1,
    )

    assert created.session_token == "token-1"
    assert created.external_ref is None

    with pytest.raises(CandidateAlreadyExistsError):
        await service.create_candidate(
            name="Ada",
            email="ada@example.com",
            role_id=2,
            owner_id=1,
        )


async def test_submit_text_unchanged_is_noop(tmp_path) -> None:
    service, _, scoring_jobs, _ = _answers_service(tmp_path, question_ids={7})

    first = await service.submit_text(candidate_id=1, question_id=7, text="hello")
    second = await service.submit_text(candidate_id=1, question_id=7, text="hello")

    assert first.unchanged is False
    assert second.unchanged is True
    assert scoring_jobs.reset_calls == [(first.answer.id, "queued")]


async def test_submit_text_changed_requeues(tmp_path) -> None:
    service, _, scoring_jobs, _ = _answers_service(tmp_path, question_ids={7})

    first = await service.submit_text(candidate_id=1, question_id=7, text="hello")
    second = await service.submit_text(candidate_id=1, question_id=7, text="goodbye")

    assert first.unchanged is False
    assert second.unchanged is False
    assert scoring_jobs.reset_calls == [
        (first.answer.id, "queued"),
        (second.answer.id, "queued"),
    ]


async def test_submit_audio_requires_person(tmp_path) -> None:
    service, _, scoring_jobs, file_storage = _answers_service(tmp_path, question_ids={7})

    result = await service.submit_audio(
        candidate_id=1,
        question_id=7,
        data=b"\x00audio",
        filename="clip.m4a",
    )

    assert result.answer.answer_type == "audio"
    content_hash = sha256(b"\x00audio").hexdigest()
    assert result.answer.audio_key == f"audio/1/7/{content_hash}.m4a"
    assert await file_storage.read(result.answer.audio_key) == b"\x00audio"
    assert scoring_jobs.reset_calls == [(result.answer.id, "needs_a_person")]


async def test_submit_unknown_question_raises(tmp_path) -> None:
    service, _, scoring_jobs, _ = _answers_service(tmp_path, question_ids=set())

    with pytest.raises(QuestionNotFoundError):
        await service.submit_text(candidate_id=1, question_id=99, text="nope")

    assert scoring_jobs.reset_calls == []


async def test_read_audio_returns_bytes_and_type(tmp_path) -> None:
    answer = Answer(
        id=10,
        candidate_id=1,
        question_id=7,
        answer_type="audio",
        text=None,
        audio_key="audio/1/7.m4a",
        content_hash="abc",
        version=1,
        external_ref=None,
        submitted_at=datetime.now(UTC),
    )
    service, _, _, file_storage = _answers_service(tmp_path, answers=[answer])
    await file_storage.save("audio/1/7.m4a", b"\x01\x02")

    data, media_type = await service.read_audio(answer.id)

    assert data == b"\x01\x02"
    assert media_type == "audio/mp4"


async def test_third_submit_is_accepted_and_fourth_changed_submit_is_rejected(tmp_path) -> None:
    service, _, _, _ = _answers_service(tmp_path, question_ids={7})

    first = await service.submit_text(candidate_id=1, question_id=7, text="a")
    second = await service.submit_text(candidate_id=1, question_id=7, text="b")
    third = await service.submit_text(candidate_id=1, question_id=7, text="c")

    assert [first.answer.version, second.answer.version, third.answer.version] == [1, 2, 3]
    with pytest.raises(AttemptsExhaustedError):
        await service.submit_text(candidate_id=1, question_id=7, text="d")


async def test_unchanged_resubmission_does_not_consume_attempt(tmp_path) -> None:
    service, _, _, _ = _answers_service(tmp_path, question_ids={7})

    first = await service.submit_text(candidate_id=1, question_id=7, text="a")
    again = await service.submit_text(candidate_id=1, question_id=7, text="a")

    assert again.unchanged is True
    assert service.attempts_remaining(again.answer) == 2
    assert service.attempts_remaining(first.answer) == 2


async def test_attempts_remaining_counts_changed_submissions(tmp_path) -> None:
    service, _, _, _ = _answers_service(tmp_path, question_ids={7})

    assert service.attempts_remaining(None) == 3
    result = await service.submit_text(candidate_id=1, question_id=7, text="a")
    assert service.attempts_remaining(result.answer) == 2


async def test_attempts_remaining_clamps_to_zero(tmp_path) -> None:
    answer = Answer(
        id=10,
        candidate_id=1,
        question_id=7,
        answer_type="text",
        text="old",
        audio_key=None,
        content_hash="old",
        version=5,
        external_ref=None,
        submitted_at=datetime.now(UTC),
    )
    service, _, _, _ = _answers_service(
        tmp_path, question_ids={7}, answers=[answer], max_submissions=2
    )

    assert service.attempts_remaining(answer) == 0


async def test_submit_audio_at_limit_does_not_overwrite_accepted_file(tmp_path) -> None:
    accepted = Answer(
        id=10,
        candidate_id=1,
        question_id=7,
        answer_type="audio",
        text=None,
        audio_key="audio/1/7.m4a",
        content_hash="accepted",
        version=3,
        external_ref=None,
        submitted_at=datetime.now(UTC),
    )
    service, _, _, file_storage = _answers_service(tmp_path, question_ids={7}, answers=[accepted])
    await file_storage.save("audio/1/7.m4a", b"accepted")

    with pytest.raises(AttemptsExhaustedError):
        await service.submit_audio(
            candidate_id=1,
            question_id=7,
            data=b"rejected",
            filename="clip.m4a",
        )

    assert await file_storage.read("audio/1/7.m4a") == b"accepted"


async def test_submit_audio_identical_at_limit_is_noop(tmp_path) -> None:
    data = b"accepted-audio"
    content_hash = sha256(data).hexdigest()
    accepted = Answer(
        id=10,
        candidate_id=1,
        question_id=7,
        answer_type="audio",
        text=None,
        audio_key=f"audio/1/7/{content_hash}.m4a",
        content_hash=content_hash,
        version=3,
        external_ref=None,
        submitted_at=datetime.now(UTC),
    )
    service, _, scoring_jobs, _ = _answers_service(tmp_path, question_ids={7}, answers=[accepted])

    result = await service.submit_audio(
        candidate_id=1,
        question_id=7,
        data=data,
        filename="clip.m4a",
    )

    assert result.unchanged is True
    assert result.answer.version == 3
    assert result.answer.content_hash == content_hash
    assert service.attempts_remaining(result.answer) == 0
    assert scoring_jobs.reset_calls == []


async def test_submit_audio_identical_returns_post_upsert_row(tmp_path) -> None:
    data = b"same-bytes"
    content_hash = sha256(data).hexdigest()
    active = Answer(
        id=10,
        candidate_id=1,
        question_id=7,
        answer_type="audio",
        text=None,
        audio_key=f"audio/1/7/{content_hash}.m4a",
        content_hash=content_hash,
        version=1,
        external_ref=None,
        submitted_at=datetime.now(UTC),
    )
    service, answers_repo, _, _ = _answers_service(tmp_path, question_ids={7}, answers=[active])
    concurrent = Answer(
        id=10,
        candidate_id=1,
        question_id=7,
        answer_type="audio",
        text=None,
        audio_key="audio/1/7/other.m4a",
        content_hash="other",
        version=2,
        external_ref=None,
        submitted_at=datetime.now(UTC),
    )
    original_get_active = answers_repo.get_active

    async def get_active_then_race(candidate_id: int, question_id: int) -> Answer | None:
        row = await original_get_active(candidate_id, question_id)
        answers_repo._answers[(candidate_id, question_id)] = concurrent
        return row

    answers_repo.get_active = get_active_then_race  # type: ignore[method-assign]

    result = await service.submit_audio(
        candidate_id=1,
        question_id=7,
        data=data,
        filename="clip.m4a",
    )

    assert result.unchanged is False
    assert result.answer.version == 3
    assert result.answer.content_hash == content_hash
    assert service.attempts_remaining(result.answer) == 0


async def test_rejected_audio_race_does_not_overwrite_accepted_file(tmp_path) -> None:
    accepted = Answer(
        id=10,
        candidate_id=1,
        question_id=7,
        answer_type="audio",
        text=None,
        audio_key="audio/1/7.m4a",
        content_hash="accepted",
        version=2,
        external_ref=None,
        submitted_at=datetime.now(UTC),
    )
    service, answers_repo, _, file_storage = _answers_service(
        tmp_path, question_ids={7}, answers=[accepted]
    )
    await file_storage.save("audio/1/7.m4a", b"accepted")
    answers_repo.block_next_upsert = True

    with pytest.raises(AttemptsExhaustedError):
        await service.submit_audio(
            candidate_id=1,
            question_id=7,
            data=b"rejected",
            filename="clip.m4a",
        )

    assert await file_storage.read("audio/1/7.m4a") == b"accepted"


async def test_import_answer_ignores_candidate_limit(tmp_path) -> None:
    existing = Answer(
        id=10,
        candidate_id=1,
        question_id=7,
        answer_type="text",
        text="old",
        audio_key=None,
        content_hash="old",
        version=3,
        external_ref=None,
        submitted_at=datetime.now(UTC),
    )
    service, _, _, _ = _answers_service(tmp_path, question_ids={7}, answers=[existing])

    stored, changed = await service.import_answer(
        candidate_id=1,
        question_id=7,
        answer_type="text",
        text="imported",
        audio_key=None,
        content_hash="imported",
        external_ref="A001",
        submitted_at=datetime.now(UTC),
    )

    assert changed is True
    assert stored.version == 4


async def test_lowered_limit_rejects_further_changed_submit(tmp_path) -> None:
    service, _, _, _ = _answers_service(tmp_path, question_ids={7}, max_submissions=1)

    await service.submit_text(candidate_id=1, question_id=7, text="a")

    with pytest.raises(AttemptsExhaustedError):
        await service.submit_text(candidate_id=1, question_id=7, text="b")
