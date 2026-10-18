import io
import json
import zipfile
from datetime import UTC, datetime
from hashlib import sha256

import pytest
from api.candidates.domain.entities import Answer, Candidate
from api.catalog.application.service import RoleWithCount
from api.catalog.domain.entities import Question, Role
from api.importing.application.service import ImportService
from api.importing.domain import InvalidImportError

OPEN_ROLES = (
    "Backend Engineer, Sales Executive, Customer Success Associate, "
    "Marketing Coordinator, Finance Analyst"
)

QUESTIONS_MD = f"""# Interview questions

Open roles: {OPEN_ROLES}.

## Q1. Tell us about a piece of work you are proud of.

- **1:** Cannot name a piece of work.
- **2:** Names a piece of work but vague.
- **3:** Clear personal contribution.
- **4:** Clear contribution and measured result.

## Q2. Describe a time you had to meet a tight deadline.

- **1:** No real example.
- **2:** An example but generic.
- **3:** Specific actions taken.
- **4:** Specific actions and a trade-off.

## Q3. Tell us about a disagreement with a colleague.

- **1:** Blames the colleague.
- **2:** Describes but not how it ended.
- **3:** Explains both views and resolution.
- **4:** Explains both views and relationship after.

## Q4. Tell us about a mistake you made at work.

- **1:** No real mistake.
- **2:** A real mistake but generic lesson.
- **3:** Owns the mistake and a specific lesson.
- **4:** Owns it and a concrete change.

## Q5. How do you decide what to work on first?

- **1:** No method.
- **2:** A general method.
- **3:** Clear ranking with a real example.
- **4:** Clear ranking by impact.

## Q6. What have you learned recently?

- **1:** Nothing specific.
- **2:** Names a topic only.
- **3:** A specific skill and where used.
- **4:** A specific skill and a measured effect.
"""

PIPELINE_CSV = """candidate_id,candidate_name,candidate_email,role
C2041,Nhi Van Tran,nhi.tran@example.com,Backend Engineer
"""

A001_TRANSCRIPT = "I built an idempotency key for the payments service."

A001_JSON = json.dumps(
    {
        "answer_id": "A001",
        "candidate_id": "C2041",
        "role": "Backend Engineer",
        "question_id": "Q1",
        "submitted_at": "2026-09-14T10:15:00",
        "transcript": A001_TRANSCRIPT,
    }
)

A034_AUDIO = b"\x00\x01fake-audio"

A034_JSON = json.dumps(
    {
        "answer_id": "A034",
        "candidate_id": "C2057",
        "role": "Sales Executive",
        "question_id": "Q1",
        "submitted_at": "2026-09-19T18:05:00",
        "audio_file": "A034.m4a",
        "transcript": None,
    }
)


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _pack(*, include_answers: bool = True) -> bytes:
    files: dict[str, bytes] = {
        "questions.md": QUESTIONS_MD.encode("utf-8"),
        "pipeline_log.csv": PIPELINE_CSV.encode("utf-8"),
    }
    if include_answers:
        files["answers/A001.json"] = A001_JSON.encode("utf-8")
        files["answers/A034.json"] = A034_JSON.encode("utf-8")
        files["answers/A034.m4a"] = A034_AUDIO
    return _zip_bytes(files)


class FakeCatalogService:
    def __init__(self) -> None:
        self.roles: dict[str, Role] = {}
        self.questions: dict[str, Question] = {}
        self._next_role_id = 1
        self._next_question_id = 1

    async def list_roles(self) -> list[RoleWithCount]:
        return [RoleWithCount(role=role, candidate_count=0) for role in self.roles.values()]

    async def list_questions(self) -> list[Question]:
        return sorted(self.questions.values(), key=lambda question: question.sort_order)

    async def ensure_role(self, name: str) -> Role:
        if name not in self.roles:
            self.roles[name] = Role(id=self._next_role_id, name=name)
            self._next_role_id += 1
        return self.roles[name]

    async def upsert_question(
        self,
        *,
        code: str,
        sort_order: int,
        prompt: str,
        grading_guide: dict[str, str],
    ) -> Question:
        existing = self.questions.get(code)
        question = Question(
            id=existing.id if existing is not None else self._next_question_id,
            code=code,
            sort_order=sort_order,
            prompt=prompt,
            grading_guide=grading_guide,
        )
        if existing is None:
            self._next_question_id += 1
        self.questions[code] = question
        return question


class FakeCandidatesService:
    def __init__(self) -> None:
        self.candidates: dict[str, Candidate] = {}
        self._next_id = 1

    async def get_by_external_ref(self, ref: str) -> Candidate | None:
        return self.candidates.get(ref)

    async def create_candidate(
        self,
        *,
        name: str,
        email: str,
        role_id: int,
        external_ref: str | None = None,
    ) -> Candidate:
        candidate = Candidate(
            id=self._next_id,
            name=name,
            email=email,
            role_id=role_id,
            session_token="generated-token",
            external_ref=external_ref,
            created_at=datetime.now(UTC),
        )
        self._next_id += 1
        self.candidates[external_ref] = candidate
        return candidate


class FakeAnswersService:
    def __init__(self) -> None:
        self.answers: dict[str, Answer] = {}
        self._next_id = 1

    async def get_by_external_ref(self, ref: str) -> Answer | None:
        return self.answers.get(ref)

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
    ) -> Answer:
        answer = Answer(
            id=self._next_id,
            candidate_id=candidate_id,
            question_id=question_id,
            answer_type=answer_type,
            text=text,
            audio_key=audio_key,
            content_hash=content_hash,
            version=1,
            external_ref=external_ref,
            submitted_at=submitted_at,
        )
        self._next_id += 1
        self.answers[external_ref] = answer
        return answer


class FakeFileStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    async def save(self, key: str, data: bytes) -> None:
        self.files[key] = data


def _service() -> tuple[
    ImportService, FakeCatalogService, FakeCandidatesService, FakeAnswersService, FakeFileStorage
]:
    catalog = FakeCatalogService()
    candidates = FakeCandidatesService()
    answers = FakeAnswersService()
    file_storage = FakeFileStorage()
    return (
        ImportService(catalog, candidates, answers, file_storage),
        catalog,
        candidates,
        answers,
        file_storage,
    )


async def test_import_parses_questions_and_roles() -> None:
    service, catalog, _, _, _ = _service()

    summary = await service.import_zip(_pack(include_answers=False))

    assert summary.questions_created == 6
    assert summary.roles_created == 5
    assert [q.code for q in await catalog.list_questions()] == [
        "Q1",
        "Q2",
        "Q3",
        "Q4",
        "Q5",
        "Q6",
    ]
    q1 = catalog.questions["Q1"]
    assert q1.prompt == "Tell us about a piece of work you are proud of."
    assert q1.grading_guide == {
        "1": "Cannot name a piece of work.",
        "2": "Names a piece of work but vague.",
        "3": "Clear personal contribution.",
        "4": "Clear contribution and measured result.",
    }
    assert sorted(listed.role.name for listed in await catalog.list_roles()) == [
        "Backend Engineer",
        "Customer Success Associate",
        "Finance Analyst",
        "Marketing Coordinator",
        "Sales Executive",
    ]


async def test_import_creates_text_candidates_and_answers() -> None:
    service, catalog, candidates, answers, _ = _service()

    summary = await service.import_zip(_pack(include_answers=True))

    assert summary.candidates_created == 2
    assert summary.answers_imported == 2
    assert summary.scoring_jobs_queued == 1

    created = candidates.candidates["C2041"]
    backend_role = catalog.roles["Backend Engineer"]
    assert created.name == "Nhi Van Tran"
    assert created.email == "nhi.tran@example.com"
    assert created.role_id == backend_role.id

    imported = answers.answers["A001"]
    assert imported.answer_type == "text"
    assert imported.text == A001_TRANSCRIPT
    assert imported.audio_key is None
    assert imported.content_hash == sha256(A001_TRANSCRIPT.encode("utf-8")).hexdigest()
    assert imported.candidate_id == created.id
    assert imported.question_id == catalog.questions["Q1"].id


async def test_import_audio_is_needs_a_person() -> None:
    service, catalog, candidates, answers, file_storage = _service()

    summary = await service.import_zip(_pack(include_answers=True))

    assert summary.audio_answers_needing_person == 1
    assert summary.scoring_jobs_queued == 1

    created = candidates.candidates["C2057"]
    sales_role = catalog.roles["Sales Executive"]
    assert created.name == "C2057"
    assert created.email == "c2057@import.local"
    assert created.role_id == sales_role.id

    imported = answers.answers["A034"]
    assert imported.answer_type == "audio"
    assert imported.text is None
    assert imported.audio_key == "audio/import/A034.m4a"
    assert imported.content_hash == sha256(A034_AUDIO).hexdigest()
    assert file_storage.files["audio/import/A034.m4a"] == A034_AUDIO


async def test_import_is_idempotent_on_external_ref() -> None:
    service, catalog, candidates, answers, _ = _service()

    first = await service.import_zip(_pack())
    second = await service.import_zip(_pack())

    assert first.roles_created == 5
    assert first.questions_created == 6
    assert first.candidates_created == 2
    assert first.answers_imported == 2

    assert second.roles_created == 0
    assert second.questions_created == 0
    assert second.candidates_created == 0
    assert second.answers_imported == 0
    assert second.scoring_jobs_queued == 0
    assert second.audio_answers_needing_person == 0

    assert len(catalog.questions) == 6
    assert len(catalog.roles) == 5
    assert len(candidates.candidates) == 2
    assert len(answers.answers) == 2


async def test_import_unreadable_zip_raises() -> None:
    service, _, _, _, _ = _service()

    with pytest.raises(InvalidImportError):
        await service.import_zip(b"this is not a zip archive")
