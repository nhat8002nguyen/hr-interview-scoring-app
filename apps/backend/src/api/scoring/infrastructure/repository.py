from dataclasses import replace
from datetime import datetime
from typing import Any, cast

from sqlalchemy import Insert, Select, Update, case, func, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from api.candidates.infrastructure.models import AnswerModel, CandidateModel
from api.catalog.infrastructure.models import QuestionModel
from api.scoring.domain.entities import ScoringInput, ScoringJob, ScoringJobSummary
from api.scoring.domain.exceptions import ScoringJobNotFoundError
from api.scoring.infrastructure.models import ScoringJobModel


def build_claim_statement() -> Select[ScoringJobModel]:
    return (
        select(ScoringJobModel)
        .where(
            ScoringJobModel.status == literal_column("'queued'"),
            ScoringJobModel.claimed_at.is_(None),
        )
        .order_by(ScoringJobModel.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )


def build_upsert_for_answer_statement(answer_id: int, status: str) -> Insert:
    statement = insert(ScoringJobModel).values(
        answer_id=answer_id,
        status=status,
    )
    return statement.on_conflict_do_update(
        index_elements=["answer_id"],
        set_={
            "status": statement.excluded.status,
            "suggested_score": None,
            "suggested_reasoning": None,
            "final_score": None,
            "override_reason": None,
            "overridden_by": None,
            "scored_at": None,
            "last_error": None,
            "claimed_at": None,
            "attempt_count": 0,
            "updated_at": func.now(),
        },
    )


def build_record_failure_statement(
    job_id: int,
    error: str,
    now: datetime,
    max_attempts: int,
) -> Update:
    return (
        update(ScoringJobModel)
        .where(ScoringJobModel.id == job_id)
        .values(
            attempt_count=ScoringJobModel.attempt_count + 1,
            last_error=error,
            claimed_at=None,
            updated_at=now,
            status=case(
                (ScoringJobModel.attempt_count + 1 >= max_attempts, literal_column("'failed'")),
                else_=literal_column("'queued'"),
            ),
        )
    )


def build_load_scoring_input_statement(
    answer_id: int,
) -> Select[str | None, str, dict[str, str]]:
    return (
        select(
            AnswerModel.text,
            QuestionModel.prompt,
            QuestionModel.grading_guide,
        )
        .select_from(AnswerModel)
        .join(QuestionModel, AnswerModel.question_id == QuestionModel.id)
        .where(AnswerModel.id == answer_id)
    )


def build_list_statement(
    status: str | None,
    owner_id: int,
) -> Select[int, int, int, str | None, str, str, int, str | None, datetime]:
    statement = (
        select(
            ScoringJobModel.id.label("id"),
            ScoringJobModel.answer_id.label("answer_id"),
            AnswerModel.candidate_id.label("candidate_id"),
            CandidateModel.name.label("candidate_name"),
            QuestionModel.code.label("question_code"),
            ScoringJobModel.status.label("status"),
            ScoringJobModel.attempt_count.label("attempt_count"),
            ScoringJobModel.last_error.label("last_error"),
            ScoringJobModel.created_at.label("created_at"),
        )
        .select_from(ScoringJobModel)
        .join(AnswerModel, ScoringJobModel.answer_id == AnswerModel.id)
        .join(CandidateModel, AnswerModel.candidate_id == CandidateModel.id)
        .join(QuestionModel, AnswerModel.question_id == QuestionModel.id)
        .where(CandidateModel.owner_id == owner_id)
    )
    if status is not None:
        statement = statement.where(ScoringJobModel.status == status)
    return statement


class SqlAlchemyScoringJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, job_id: int) -> ScoringJob | None:
        row = await self._session.get(ScoringJobModel, job_id)
        return None if row is None else self._to_job(row)

    async def get_owned(self, job_id: int, owner_id: int) -> ScoringJob | None:
        row = await self._session.scalar(
            select(ScoringJobModel)
            .join(AnswerModel, ScoringJobModel.answer_id == AnswerModel.id)
            .join(CandidateModel, AnswerModel.candidate_id == CandidateModel.id)
            .where(ScoringJobModel.id == job_id, CandidateModel.owner_id == owner_id)
        )
        return None if row is None else self._to_job(row)

    async def get_by_answer(self, answer_id: int) -> ScoringJob | None:
        row = await self._session.scalar(
            select(ScoringJobModel).where(ScoringJobModel.answer_id == answer_id)
        )
        return None if row is None else self._to_job(row)

    async def upsert_for_answer(self, answer_id: int, status: str) -> ScoringJob:
        await self._session.execute(build_upsert_for_answer_statement(answer_id, status))
        row = await self._session.scalar(
            select(ScoringJobModel)
            .where(ScoringJobModel.answer_id == answer_id)
            .execution_options(populate_existing=True)
        )
        assert row is not None, "upsert must always produce a scoring job row"
        return self._to_job(row)

    async def claim_next_queued(self, now: datetime) -> ScoringJob | None:
        row = await self._session.scalar(build_claim_statement())
        if row is None:
            return None
        await self._session.execute(
            update(ScoringJobModel)
            .where(ScoringJobModel.id == row.id)
            .values(claimed_at=now)
        )
        return replace(self._to_job(row), claimed_at=now)

    async def mark_scored(
        self,
        job_id: int,
        *,
        suggested_score: int,
        suggested_reasoning: str,
        now: datetime,
    ) -> ScoringJob:
        await self._session.execute(
            update(ScoringJobModel)
            .where(ScoringJobModel.id == job_id)
            .values(
                suggested_score=suggested_score,
                suggested_reasoning=suggested_reasoning,
                final_score=suggested_score,
                status="scored",
                scored_at=now,
                claimed_at=None,
                last_error=None,
                updated_at=now,
            )
        )
        row = await self._load(job_id)
        if row is None:
            raise ScoringJobNotFoundError(job_id)
        return self._to_job(row)

    async def record_failure(
        self,
        job_id: int,
        *,
        error: str,
        now: datetime,
        max_attempts: int,
    ) -> ScoringJob:
        await self._session.execute(
            build_record_failure_statement(job_id, error, now, max_attempts)
        )
        row = await self._load(job_id)
        if row is None:
            raise ScoringJobNotFoundError(job_id)
        return self._to_job(row)

    async def set_override(
        self,
        answer_id: int,
        *,
        final_score: int,
        override_reason: str,
        overridden_by: int,
        now: datetime,
    ) -> ScoringJob:
        row = await self._session.scalar(
            select(ScoringJobModel).where(ScoringJobModel.answer_id == answer_id)
        )
        if row is None:
            raise ScoringJobNotFoundError(answer_id)
        await self._session.execute(
            update(ScoringJobModel)
            .where(ScoringJobModel.id == row.id)
            .values(
                final_score=final_score,
                override_reason=override_reason,
                overridden_by=overridden_by,
                updated_at=now,
            )
        )
        reloaded = await self._load(row.id)
        if reloaded is None:
            raise ScoringJobNotFoundError(row.id)
        return self._to_job(reloaded)

    async def mark_retried(self, job_id: int, *, now: datetime) -> ScoringJob:
        await self._session.execute(
            update(ScoringJobModel)
            .where(ScoringJobModel.id == job_id)
            .values(
                status="queued",
                attempt_count=ScoringJobModel.attempt_count + 1,
                last_error=None,
                claimed_at=None,
                updated_at=now,
            )
        )
        row = await self._load(job_id)
        if row is None:
            raise ScoringJobNotFoundError(job_id)
        return self._to_job(row)

    async def list(self, status: str | None, owner_id: int) -> list[ScoringJobSummary]:
        rows = (await self._session.execute(build_list_statement(status, owner_id))).all()
        return [
            ScoringJobSummary(
                id=row.id,
                answer_id=row.answer_id,
                candidate_id=row.candidate_id,
                candidate_name=row.candidate_name,
                question_code=row.question_code,
                status=row.status,
                attempt_count=row.attempt_count,
                last_error=row.last_error,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def reset_stale_claims(self, before: datetime) -> int:
        result = await self._session.execute(
            update(ScoringJobModel)
            .where(
                ScoringJobModel.status == "queued",
                ScoringJobModel.claimed_at.is_not(None),
                ScoringJobModel.claimed_at < before,
            )
            .values(claimed_at=None)
        )
        return cast(CursorResult[Any], result).rowcount

    async def load_scoring_input(self, answer_id: int) -> ScoringInput | None:
        row = (
            await self._session.execute(build_load_scoring_input_statement(answer_id))
        ).one_or_none()
        if row is None:
            return None
        text, prompt, grading_guide = row
        if text is None:
            return None
        return ScoringInput(
            answer_id=answer_id,
            prompt=prompt,
            grading_guide=grading_guide,
            answer_text=text,
        )

    async def _load(self, job_id: int) -> ScoringJobModel | None:
        return await self._session.scalar(
            select(ScoringJobModel)
            .where(ScoringJobModel.id == job_id)
            .execution_options(populate_existing=True)
        )

    def _to_job(self, row: ScoringJobModel) -> ScoringJob:
        return ScoringJob(
            id=row.id,
            answer_id=row.answer_id,
            status=row.status,
            suggested_score=row.suggested_score,
            suggested_reasoning=row.suggested_reasoning,
            final_score=row.final_score,
            override_reason=row.override_reason,
            overridden_by=row.overridden_by,
            attempt_count=row.attempt_count,
            last_error=row.last_error,
            claimed_at=row.claimed_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
            scored_at=row.scored_at,
        )
