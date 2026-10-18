from typing import Any, cast

from sqlalchemy import Insert, func, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from api.candidates.domain.entities import Answer, Candidate
from api.candidates.infrastructure.models import AnswerModel, CandidateModel


def build_upsert_statement(answer: Answer) -> Insert:
    statement = insert(AnswerModel).values(
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
    return statement.on_conflict_do_update(
        index_elements=["candidate_id", "question_id"],
        set_={
            "answer_type": answer.answer_type,
            "text": answer.text,
            "audio_key": answer.audio_key,
            "content_hash": answer.content_hash,
            "version": literal_column("answers.version + 1"),
            "submitted_at": answer.submitted_at,
        },
        where=AnswerModel.content_hash != statement.excluded.content_hash,
    )


class SqlAlchemyCandidateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, candidate: Candidate) -> Candidate:
        row = CandidateModel(
            name=candidate.name,
            email=candidate.email,
            role_id=candidate.role_id,
            session_token=candidate.session_token,
            external_ref=candidate.external_ref,
            created_at=candidate.created_at,
        )
        self._session.add(row)
        await self._session.flush()
        return self._to_candidate(row)

    async def get(self, candidate_id: int) -> Candidate | None:
        row = await self._session.get(CandidateModel, candidate_id)
        return None if row is None else self._to_candidate(row)

    async def get_by_email(self, email: str) -> Candidate | None:
        row = await self._session.scalar(
            select(CandidateModel).where(CandidateModel.email == email)
        )
        return None if row is None else self._to_candidate(row)

    async def get_by_session_token(self, session_token: str) -> Candidate | None:
        row = await self._session.scalar(
            select(CandidateModel).where(CandidateModel.session_token == session_token)
        )
        return None if row is None else self._to_candidate(row)

    async def get_by_external_ref(self, external_ref: str) -> Candidate | None:
        row = await self._session.scalar(
            select(CandidateModel).where(CandidateModel.external_ref == external_ref)
        )
        return None if row is None else self._to_candidate(row)

    async def list_by_role(self, role_id: int) -> list[Candidate]:
        rows = (
            (
                await self._session.execute(
                    select(CandidateModel)
                    .where(CandidateModel.role_id == role_id)
                    .order_by(CandidateModel.id)
                )
            )
            .scalars()
            .all()
        )
        return [self._to_candidate(row) for row in rows]

    async def count_by_role(self, role_id: int) -> int:
        count = await self._session.scalar(
            select(func.count())
            .select_from(CandidateModel)
            .where(CandidateModel.role_id == role_id)
        )
        return count or 0

    def _to_candidate(self, row: CandidateModel) -> Candidate:
        return Candidate(
            id=row.id,
            name=row.name,
            email=row.email,
            role_id=row.role_id,
            session_token=row.session_token,
            external_ref=row.external_ref,
            created_at=row.created_at,
        )


class SqlAlchemyAnswerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, answer: Answer) -> tuple[Answer, bool]:
        result = await self._session.execute(build_upsert_statement(answer))
        changed = cast(CursorResult[Any], result).rowcount > 0
        row = await self._get_active_row(answer.candidate_id, answer.question_id)
        assert row is not None, "upsert must always produce an active answer row"
        return self._to_answer(row), changed

    async def get(self, answer_id: int) -> Answer | None:
        row = await self._session.get(AnswerModel, answer_id)
        return None if row is None else self._to_answer(row)

    async def get_active(self, candidate_id: int, question_id: int) -> Answer | None:
        row = await self._get_active_row(candidate_id, question_id)
        return None if row is None else self._to_answer(row)

    async def list_for_candidate(self, candidate_id: int) -> list[Answer]:
        rows = (
            (
                await self._session.execute(
                    select(AnswerModel)
                    .where(AnswerModel.candidate_id == candidate_id)
                    .order_by(AnswerModel.question_id)
                )
            )
            .scalars()
            .all()
        )
        return [self._to_answer(row) for row in rows]

    async def get_by_external_ref(self, external_ref: str) -> Answer | None:
        row = await self._session.scalar(
            select(AnswerModel).where(AnswerModel.external_ref == external_ref)
        )
        return None if row is None else self._to_answer(row)

    async def _get_active_row(self, candidate_id: int, question_id: int) -> AnswerModel | None:
        return await self._session.scalar(
            select(AnswerModel)
            .where(
                AnswerModel.candidate_id == candidate_id,
                AnswerModel.question_id == question_id,
            )
            .execution_options(populate_existing=True)
        )

    def _to_answer(self, row: AnswerModel) -> Answer:
        return Answer(
            id=row.id,
            candidate_id=row.candidate_id,
            question_id=row.question_id,
            answer_type=row.answer_type,
            text=row.text,
            audio_key=row.audio_key,
            content_hash=row.content_hash,
            version=row.version,
            external_ref=row.external_ref,
            submitted_at=row.submitted_at,
        )
