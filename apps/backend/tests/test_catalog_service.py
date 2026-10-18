import pytest

from api.catalog.application.service import CatalogService, RoleWithCount
from api.catalog.domain.entities import Question, Role
from api.catalog.domain.exceptions import QuestionNotFoundError


class FakeRoleRepository:
    def __init__(self, roles: list[Role] | None = None) -> None:
        self._roles = {role.id: role for role in roles or []}
        self._next_id = max(self._roles, default=0) + 1

    async def list(self) -> list[Role]:
        return sorted(self._roles.values(), key=lambda role: role.id)

    async def get(self, role_id: int) -> Role | None:
        return self._roles.get(role_id)

    async def get_by_name(self, name: str) -> Role | None:
        return next((role for role in self._roles.values() if role.name == name), None)

    async def add(self, role: Role) -> Role:
        stored = Role(id=self._next_id, name=role.name)
        self._roles[stored.id] = stored
        self._next_id += 1
        return stored


class FakeQuestionRepository:
    def __init__(self, questions: list[Question] | None = None) -> None:
        self._questions = {question.id: question for question in questions or []}
        self._next_id = max(self._questions, default=0) + 1

    async def list_ordered(self) -> list[Question]:
        return sorted(self._questions.values(), key=lambda question: question.sort_order)

    async def get(self, question_id: int) -> Question | None:
        return self._questions.get(question_id)

    async def get_by_code(self, code: str) -> Question | None:
        return next(
            (question for question in self._questions.values() if question.code == code),
            None,
        )

    async def upsert(self, question: Question) -> Question:
        existing = await self.get_by_code(question.code)
        question_id = self._next_id if existing is None else existing.id
        stored = Question(
            id=question_id,
            code=question.code,
            sort_order=question.sort_order,
            prompt=question.prompt,
            grading_guide=question.grading_guide,
        )
        self._questions[stored.id] = stored
        if existing is None:
            self._next_id += 1
        return stored


class FakeCatalogUnitOfWork:
    def __init__(
        self,
        roles: FakeRoleRepository,
        questions: FakeQuestionRepository,
    ) -> None:
        self.roles = roles
        self.questions = questions

    async def __aenter__(self) -> FakeCatalogUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        return None


class FakeRoleCandidateCounter:
    def __init__(self, counts: dict[int, int] | None = None) -> None:
        self._counts = counts or {}

    async def count_by_role(self, role_id: int) -> int:
        return self._counts.get(role_id, 0)


def _service(
    *,
    roles: list[Role] | None = None,
    questions: list[Question] | None = None,
    counts: dict[int, int] | None = None,
) -> tuple[CatalogService, FakeRoleRepository, FakeQuestionRepository]:
    role_repository = FakeRoleRepository(roles)
    question_repository = FakeQuestionRepository(questions)
    service = CatalogService(
        lambda: FakeCatalogUnitOfWork(role_repository, question_repository),
        FakeRoleCandidateCounter(counts),
    )
    return service, role_repository, question_repository


def _question(question_id: int, code: str, sort_order: int) -> Question:
    return Question(
        id=question_id,
        code=code,
        sort_order=sort_order,
        prompt=f"Prompt {code}",
        grading_guide={"1": "Bad", "4": "Great"},
    )


async def test_list_questions_ordered() -> None:
    service, _, _ = _service(
        questions=[_question(2, "Q2", 2), _question(1, "Q1", 1)],
    )

    questions = await service.list_questions()

    assert [question.code for question in questions] == ["Q1", "Q2"]


async def test_get_question_missing_raises() -> None:
    service, _, _ = _service()

    with pytest.raises(QuestionNotFoundError, match="Question #99 not found"):
        await service.get_question(99)


async def test_ensure_role_creates_when_missing() -> None:
    service, role_repository, _ = _service()

    role = await service.ensure_role("Backend Engineer")
    duplicate = await service.ensure_role("Backend Engineer")

    assert role.name == "Backend Engineer"
    assert duplicate == role
    assert await role_repository.list() == [role]


async def test_upsert_question_updates_by_code() -> None:
    service, _, question_repository = _service(questions=[_question(10, "Q1", 1)])

    updated = await service.upsert_question(
        code="Q1",
        sort_order=1,
        prompt="Updated prompt",
        grading_guide={"1": "Poor", "4": "Excellent"},
    )

    assert updated.id == 10
    assert updated.prompt == "Updated prompt"
    assert updated.grading_guide == {"1": "Poor", "4": "Excellent"}
    assert await question_repository.list_ordered() == [updated]


async def test_list_roles_includes_counts() -> None:
    roles = [Role(id=1, name="Backend Engineer"), Role(id=2, name="Sales Executive")]
    service, _, _ = _service(roles=roles, counts={1: 3, 2: 0})

    result = await service.list_roles()

    assert result == [
        RoleWithCount(role=roles[0], candidate_count=3),
        RoleWithCount(role=roles[1], candidate_count=0),
    ]
