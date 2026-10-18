from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.catalog.domain.entities import Question, Role
from api.catalog.infrastructure.models import QuestionModel, RoleModel


class SqlAlchemyRoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[Role]:
        rows = (
            (await self._session.execute(select(RoleModel).order_by(RoleModel.id))).scalars().all()
        )
        return [self._to_role(row) for row in rows]

    async def get(self, role_id: int) -> Role | None:
        row = await self._session.get(RoleModel, role_id)
        return None if row is None else self._to_role(row)

    async def get_by_name(self, name: str) -> Role | None:
        row = await self._session.scalar(select(RoleModel).where(RoleModel.name == name))
        return None if row is None else self._to_role(row)

    async def add(self, role: Role) -> Role:
        row = RoleModel(name=role.name)
        self._session.add(row)
        await self._session.flush()
        return self._to_role(row)

    def _to_role(self, row: RoleModel) -> Role:
        return Role(id=row.id, name=row.name)


class SqlAlchemyQuestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_ordered(self) -> list[Question]:
        rows = (
            (await self._session.execute(select(QuestionModel).order_by(QuestionModel.sort_order)))
            .scalars()
            .all()
        )
        return [self._to_question(row) for row in rows]

    async def get(self, question_id: int) -> Question | None:
        row = await self._session.get(QuestionModel, question_id)
        return None if row is None else self._to_question(row)

    async def get_by_code(self, code: str) -> Question | None:
        row = await self._session.scalar(select(QuestionModel).where(QuestionModel.code == code))
        return None if row is None else self._to_question(row)

    async def upsert(self, question: Question) -> Question:
        statement = (
            insert(QuestionModel)
            .values(
                code=question.code,
                sort_order=question.sort_order,
                prompt=question.prompt,
                grading_guide=question.grading_guide,
            )
            .on_conflict_do_update(
                index_elements=[QuestionModel.code],
                set_={
                    "sort_order": question.sort_order,
                    "prompt": question.prompt,
                    "grading_guide": question.grading_guide,
                },
            )
            .returning(QuestionModel)
        )
        row = (await self._session.execute(statement)).scalar_one()
        return self._to_question(row)

    def _to_question(self, row: QuestionModel) -> Question:
        return Question(
            id=row.id,
            code=row.code,
            sort_order=row.sort_order,
            prompt=row.prompt,
            grading_guide=row.grading_guide,
        )
