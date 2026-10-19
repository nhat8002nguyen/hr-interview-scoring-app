import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

from api.candidates.application.ports import (
    CandidatesUnitOfWorkFactory,
    FileStorage,
    ScoringJobPort,
    TokenGenerator,
)
from api.candidates.domain.entities import Answer, Candidate
from api.candidates.domain.exceptions import (
    AnswerNotFoundError,
    AttemptsExhaustedError,
    CandidateAlreadyExistsError,
    CandidateNotFoundError,
)
from api.catalog.application.service import CatalogService


def _default_token_generator() -> str:
    return secrets.token_urlsafe(32)


_MEDIA_TYPES = {
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
}


def _media_type(audio_key: str) -> str:
    return _MEDIA_TYPES.get(Path(audio_key).suffix.lower(), "application/octet-stream")


@dataclass(frozen=True, slots=True)
class SubmitResult:
    status: Literal["received"]
    unchanged: bool
    answer: Answer


class CandidatesService:
    def __init__(
        self,
        uow_factory: CandidatesUnitOfWorkFactory,
        token_generator: TokenGenerator | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._token_generator = token_generator or _default_token_generator

    async def create_candidate(
        self,
        *,
        name: str,
        email: str,
        role_id: int,
        owner_id: int,
        external_ref: str | None = None,
    ) -> Candidate:
        async with self._uow_factory() as uow:
            existing = await uow.candidates.get_by_email(email)
            if existing is not None:
                raise CandidateAlreadyExistsError(email)
            candidate = Candidate(
                id=0,
                name=name,
                email=email,
                role_id=role_id,
                owner_id=owner_id,
                session_token=self._token_generator(),
                external_ref=external_ref,
                created_at=datetime.now(UTC),
            )
            return await uow.candidates.add(candidate)

    async def get_by_session_token(self, token: str) -> Candidate | None:
        async with self._uow_factory() as uow:
            return await uow.candidates.get_by_session_token(token)

    async def get_candidate(self, id: int) -> Candidate:
        async with self._uow_factory() as uow:
            candidate = await uow.candidates.get(id)
        if candidate is None:
            raise CandidateNotFoundError(id)
        return candidate

    async def get_by_external_ref(self, ref: str) -> Candidate | None:
        async with self._uow_factory() as uow:
            return await uow.candidates.get_by_external_ref(ref)

    async def list_candidates_for_role(self, role_id: int) -> list[Candidate]:
        async with self._uow_factory() as uow:
            return await uow.candidates.list_by_role(role_id)

    async def count_by_role(self, role_id: int) -> int:
        async with self._uow_factory() as uow:
            return await uow.candidates.count_by_role(role_id)


class AnswersService:
    def __init__(
        self,
        uow_factory: CandidatesUnitOfWorkFactory,
        questions: CatalogService,
        scoring_jobs: ScoringJobPort,
        file_storage: FileStorage,
        max_submissions: int = 3,
    ) -> None:
        self._uow_factory = uow_factory
        self._questions = questions
        self._scoring_jobs = scoring_jobs
        self._file_storage = file_storage
        self.max_submissions = max_submissions

    def attempts_remaining(self, answer: Answer | None) -> int:
        used = 0 if answer is None else answer.version
        return max(0, self.max_submissions - used)

    async def submit_text(
        self,
        candidate_id: int,
        question_id: int,
        text: str,
    ) -> SubmitResult:
        await self._questions.get_question(question_id)
        content_hash = sha256(text.encode("utf-8")).hexdigest()
        return await self._submit(
            Answer(
                id=0,
                candidate_id=candidate_id,
                question_id=question_id,
                answer_type="text",
                text=text,
                audio_key=None,
                content_hash=content_hash,
                version=1,
                external_ref=None,
                submitted_at=datetime.now(UTC),
            ),
            status="queued",
        )

    async def submit_audio(
        self,
        candidate_id: int,
        question_id: int,
        data: bytes,
        filename: str,
    ) -> SubmitResult:
        await self._questions.get_question(question_id)
        content_hash = sha256(data).hexdigest()
        async with self._uow_factory() as uow:
            active = await uow.answers.get_active(candidate_id, question_id)
        if (
            active is not None
            and active.version >= self.max_submissions
            and active.content_hash != content_hash
        ):
            raise AttemptsExhaustedError(question_id, self.max_submissions)
        ext = Path(filename).suffix or ".m4a"
        key = f"audio/{candidate_id}/{question_id}/{content_hash}{ext}"
        await self._file_storage.save(key, data)
        return await self._submit(
            Answer(
                id=0,
                candidate_id=candidate_id,
                question_id=question_id,
                answer_type="audio",
                text=None,
                audio_key=key,
                content_hash=content_hash,
                version=1,
                external_ref=None,
                submitted_at=datetime.now(UTC),
            ),
            status="needs_a_person",
        )

    async def _submit(self, answer: Answer, *, status: str) -> SubmitResult:
        async with self._uow_factory() as uow:
            stored, changed = await uow.answers.upsert(answer, max_submissions=self.max_submissions)
        if changed:
            await self._scoring_jobs.reset_for_answer(stored.id, status=status)
            return SubmitResult(status="received", unchanged=False, answer=stored)
        if stored.content_hash == answer.content_hash:
            return SubmitResult(status="received", unchanged=True, answer=stored)
        raise AttemptsExhaustedError(answer.question_id, self.max_submissions)

    async def list_for_candidate(self, candidate_id: int) -> list[Answer]:
        async with self._uow_factory() as uow:
            return await uow.answers.list_for_candidate(candidate_id)

    async def get_by_external_ref(self, ref: str) -> Answer | None:
        async with self._uow_factory() as uow:
            return await uow.answers.get_by_external_ref(ref)

    async def get_active(self, candidate_id: int, question_id: int) -> Answer | None:
        async with self._uow_factory() as uow:
            return await uow.answers.get_active(candidate_id, question_id)

    async def get(self, answer_id: int) -> Answer:
        async with self._uow_factory() as uow:
            answer = await uow.answers.get(answer_id)
        if answer is None:
            raise AnswerNotFoundError(answer_id)
        return answer

    async def read_audio(self, answer_id: int) -> tuple[bytes, str]:
        answer = await self.get(answer_id)
        if answer.answer_type != "audio" or answer.audio_key is None:
            raise AnswerNotFoundError(answer_id)
        data = await self._file_storage.read(answer.audio_key)
        return data, _media_type(answer.audio_key)

    async def import_answer(
        self,
        candidate_id: int,
        question_id: int,
        *,
        answer_type: str,
        text: str | None,
        audio_key: str | None,
        content_hash: str,
        external_ref: str | None,
        submitted_at: datetime,
    ) -> tuple[Answer, bool]:
        status = "queued" if answer_type == "text" else "needs_a_person"
        async with self._uow_factory() as uow:
            stored, changed = await uow.answers.upsert(
                Answer(
                    id=0,
                    candidate_id=candidate_id,
                    question_id=question_id,
                    answer_type=answer_type,
                    text=text,
                    audio_key=audio_key,
                    content_hash=content_hash,
                    version=1,
                    external_ref=external_ref,
                    submitted_at=submitted_at,
                ),
                max_submissions=None,
            )
        if changed:
            await self._scoring_jobs.reset_for_answer(stored.id, status=status)
        return stored, changed
