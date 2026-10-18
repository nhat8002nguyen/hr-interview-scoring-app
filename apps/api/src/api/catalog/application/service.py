from dataclasses import dataclass

from api.catalog.application.ports import CatalogUnitOfWorkFactory, RoleCandidateCounter
from api.catalog.domain.entities import Question, Role
from api.catalog.domain.exceptions import QuestionNotFoundError, RoleNotFoundError


@dataclass(frozen=True, slots=True)
class RoleWithCount:
    role: Role
    candidate_count: int


class CatalogService:
    def __init__(
        self,
        uow_factory: CatalogUnitOfWorkFactory,
        counter: RoleCandidateCounter,
    ) -> None:
        self._uow_factory = uow_factory
        self._counter = counter

    async def list_roles(self) -> list[RoleWithCount]:
        async with self._uow_factory() as uow:
            roles = await uow.roles.list()
        return [
            RoleWithCount(
                role=role,
                candidate_count=await self._counter.count_by_role(role.id),
            )
            for role in roles
        ]

    async def list_questions(self) -> list[Question]:
        async with self._uow_factory() as uow:
            return await uow.questions.list_ordered()

    async def get_question(self, question_id: int) -> Question:
        async with self._uow_factory() as uow:
            question = await uow.questions.get(question_id)
        if question is None:
            raise QuestionNotFoundError(question_id)
        return question

    async def get_role(self, role_id: int) -> Role:
        async with self._uow_factory() as uow:
            role = await uow.roles.get(role_id)
        if role is None:
            raise RoleNotFoundError(role_id)
        return role

    async def ensure_role(self, name: str) -> Role:
        async with self._uow_factory() as uow:
            existing = await uow.roles.get_by_name(name)
            if existing is not None:
                return existing
            return await uow.roles.add(Role(id=0, name=name))

    async def upsert_question(
        self,
        *,
        code: str,
        sort_order: int,
        prompt: str,
        grading_guide: dict[str, str],
    ) -> Question:
        async with self._uow_factory() as uow:
            return await uow.questions.upsert(
                Question(
                    id=0,
                    code=code,
                    sort_order=sort_order,
                    prompt=prompt,
                    grading_guide=grading_guide,
                )
            )
