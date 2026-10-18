"""Application services for scoring jobs."""

from datetime import UTC, datetime

from api.scoring.application.ports import ScoringUnitOfWorkFactory
from api.scoring.domain.entities import ScoringJob, ScoringJobSummary
from api.scoring.domain.exceptions import (
    ScoringJobInvalidTransitionError,
    ScoringJobNotFoundError,
)

_OVERRIDABLE_STATUSES = ("scored", "needs_a_person")


class ScoringService:
    def __init__(self, uow_factory: ScoringUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def reset_for_answer(self, answer_id: int, *, status: str) -> None:
        async with self._uow_factory() as uow:
            await uow.scoring_jobs.upsert_for_answer(answer_id, status)

    async def get_job(self, job_id: int) -> ScoringJob:
        async with self._uow_factory() as uow:
            job = await uow.scoring_jobs.get(job_id)
        if job is None:
            raise ScoringJobNotFoundError(job_id)
        return job

    async def get_job_by_answer(self, answer_id: int) -> ScoringJob:
        async with self._uow_factory() as uow:
            job = await uow.scoring_jobs.get_by_answer(answer_id)
        if job is None:
            raise ScoringJobNotFoundError(answer_id)
        return job

    async def list_jobs(self, status: str | None) -> list[ScoringJobSummary]:
        async with self._uow_factory() as uow:
            return await uow.scoring_jobs.list(status)

    async def override_score(
        self,
        answer_id: int,
        *,
        final_score: int,
        override_reason: str,
        overridden_by: int,
    ) -> ScoringJob:
        async with self._uow_factory() as uow:
            job = await uow.scoring_jobs.get_by_answer(answer_id)
            if job is None:
                raise ScoringJobNotFoundError(answer_id)
            if job.status not in _OVERRIDABLE_STATUSES:
                raise ScoringJobInvalidTransitionError(job.id, job.status)
            if not override_reason.strip():
                raise ScoringJobInvalidTransitionError(job.id, "override_reason required")
            if not 1 <= final_score <= 4:
                raise ScoringJobInvalidTransitionError(
                    job.id, f"final_score {final_score} out of range"
                )
            return await uow.scoring_jobs.set_override(
                answer_id,
                final_score=final_score,
                override_reason=override_reason,
                overridden_by=overridden_by,
                now=datetime.now(UTC),
            )

    async def retry(self, job_id: int) -> ScoringJob:
        async with self._uow_factory() as uow:
            job = await uow.scoring_jobs.get(job_id)
            if job is None:
                raise ScoringJobNotFoundError(job_id)
            if job.status != "failed":
                raise ScoringJobInvalidTransitionError(job_id, job.status)
            return await uow.scoring_jobs.mark_retried(job_id, now=datetime.now(UTC))

    async def reset_stale_claims(self, before: datetime) -> int:
        async with self._uow_factory() as uow:
            return await uow.scoring_jobs.reset_stale_claims(before)
