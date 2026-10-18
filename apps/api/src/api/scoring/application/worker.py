"""Background worker that scores queued jobs through the LLM port."""

import asyncio
from datetime import UTC, datetime

from api.scoring.application.ports import LlmError, ScoringLlmPort, ScoringUnitOfWorkFactory
from api.scoring.domain.entities import ScoringJob


class ScoringWorker:
    def __init__(
        self,
        uow_factory: ScoringUnitOfWorkFactory,
        llm: ScoringLlmPort,
        *,
        max_attempts: int,
        poll_interval_seconds: float,
        stop_event: asyncio.Event,
    ) -> None:
        self._uow_factory = uow_factory
        self._llm = llm
        self._max_attempts = max_attempts
        self._poll_interval_seconds = poll_interval_seconds
        self._stop_event = stop_event

    async def run(self) -> None:
        while not self._stop_event.is_set():
            job = await self._claim_next()
            if job is None:
                await asyncio.sleep(self._poll_interval_seconds)
                continue
            try:
                await self._process(job)
            except Exception as exc:  # noqa: BLE001 - worker survives any job failure
                await self._record_failure(job, exc)
                await asyncio.sleep(self._poll_interval_seconds)

    async def _claim_next(self) -> ScoringJob | None:
        async with self._uow_factory() as uow:
            return await uow.scoring_jobs.claim_next_queued(datetime.now(UTC))

    async def _process(self, job: ScoringJob) -> None:
        async with self._uow_factory() as uow:
            scoring_input = await uow.scoring_jobs.load_scoring_input(job.answer_id)
        if scoring_input is None:
            raise LlmError("scoring input missing")
        result = await self._llm.score(
            scoring_input.prompt,
            scoring_input.grading_guide,
            scoring_input.answer_text,
        )
        async with self._uow_factory() as uow:
            await uow.scoring_jobs.mark_scored(
                job.id,
                suggested_score=result.score,
                suggested_reasoning=result.reasoning,
                now=datetime.now(UTC),
            )

    async def _record_failure(self, job: ScoringJob, exc: Exception) -> None:
        async with self._uow_factory() as uow:
            await uow.scoring_jobs.record_failure(
                job.id,
                error=str(exc),
                now=datetime.now(UTC),
                max_attempts=self._max_attempts,
            )
