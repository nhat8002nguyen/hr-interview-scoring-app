from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import ANY

import pytest
from api.scoring.application.service import ScoringService
from api.scoring.domain.entities import ScoringJob
from api.scoring.domain.exceptions import (
    ScoringJobInvalidTransitionError,
    ScoringJobNotFoundError,
)


def _job(
    job_id: int,
    answer_id: int,
    status: str,
    *,
    attempt_count: int = 0,
    final_score: int | None = None,
    override_reason: str | None = None,
    overridden_by: int | None = None,
) -> ScoringJob:
    return ScoringJob(
        id=job_id,
        answer_id=answer_id,
        status=status,
        suggested_score=None,
        suggested_reasoning=None,
        final_score=final_score,
        override_reason=override_reason,
        overridden_by=overridden_by,
        attempt_count=attempt_count,
        last_error=None,
        claimed_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        scored_at=None,
    )


class FakeScoringJobRepository:
    def __init__(self, jobs: list[ScoringJob] | None = None) -> None:
        self._jobs: dict[int, ScoringJob] = {job.id: job for job in jobs or []}
        self._by_answer: dict[int, ScoringJob] = {
            job.answer_id: job for job in jobs or []
        }
        self._next_id = max(self._jobs, default=0) + 1
        self.upsert_calls: list[tuple[int, str]] = []
        self.set_override_calls: list[tuple] = []
        self.mark_retried_calls: list[tuple[int, datetime]] = []

    async def get(self, job_id: int) -> ScoringJob | None:
        return self._jobs.get(job_id)

    async def get_by_answer(self, answer_id: int) -> ScoringJob | None:
        return self._by_answer.get(answer_id)

    async def upsert_for_answer(self, answer_id: int, status: str) -> ScoringJob:
        self.upsert_calls.append((answer_id, status))
        existing = self._by_answer.get(answer_id)
        if existing is None:
            job = _job(self._next_id, answer_id, status)
            self._next_id += 1
        else:
            job = replace(existing, status=status)
        self._jobs[job.id] = job
        self._by_answer[answer_id] = job
        return job

    async def set_override(
        self,
        answer_id: int,
        *,
        final_score: int,
        override_reason: str,
        overridden_by: int,
        now: datetime,
    ) -> ScoringJob:
        self.set_override_calls.append(
            (answer_id, final_score, override_reason, overridden_by, now)
        )
        job = self._by_answer.get(answer_id)
        if job is None:
            raise ScoringJobNotFoundError(answer_id)
        updated = replace(
            job,
            final_score=final_score,
            override_reason=override_reason,
            overridden_by=overridden_by,
            updated_at=now,
        )
        self._jobs[updated.id] = updated
        self._by_answer[answer_id] = updated
        return updated

    async def mark_retried(self, job_id: int, *, now: datetime) -> ScoringJob:
        self.mark_retried_calls.append((job_id, now))
        job = self._jobs.get(job_id)
        if job is None:
            raise ScoringJobNotFoundError(job_id)
        updated = replace(
            job,
            status="queued",
            attempt_count=job.attempt_count + 1,
            last_error=None,
            claimed_at=None,
            updated_at=now,
        )
        self._jobs[job_id] = updated
        self._by_answer[updated.answer_id] = updated
        return updated

    async def list(self, status: str | None) -> list:
        return []

    async def claim_next_queued(self, now: datetime) -> ScoringJob | None:
        return None

    async def mark_scored(self, job_id: int, **kwargs) -> ScoringJob:
        raise NotImplementedError

    async def record_failure(self, job_id: int, **kwargs) -> ScoringJob:
        raise NotImplementedError

    async def reset_stale_claims(self, before: datetime) -> int:
        return 0

    async def load_scoring_input(self, answer_id: int):
        return None


class FakeScoringUnitOfWork:
    def __init__(self, repo: FakeScoringJobRepository) -> None:
        self.scoring_jobs = repo

    async def __aenter__(self) -> FakeScoringUnitOfWork:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


def _service(repo: FakeScoringJobRepository) -> ScoringService:
    return ScoringService(lambda: FakeScoringUnitOfWork(repo))


async def test_override_requires_reason() -> None:
    repo = FakeScoringJobRepository([_job(1, 100, "scored")])
    service = _service(repo)

    with pytest.raises(ScoringJobInvalidTransitionError) as exc_info:
        await service.override_score(100, final_score=4, override_reason="   ", overridden_by=7)

    assert exc_info.value.status == "override_reason required"


async def test_override_sets_final_score() -> None:
    repo = FakeScoringJobRepository([_job(1, 100, "scored")])
    service = _service(repo)

    result = await service.override_score(
        100, final_score=4, override_reason="reviewed", overridden_by=7
    )

    assert result.final_score == 4
    assert result.override_reason == "reviewed"
    assert result.overridden_by == 7
    assert repo.set_override_calls == [(100, 4, "reviewed", 7, ANY)]


async def test_override_rejects_wrong_status() -> None:
    for status in ("queued", "failed"):
        repo = FakeScoringJobRepository([_job(1, 100, status)])
        service = _service(repo)

        with pytest.raises(ScoringJobInvalidTransitionError):
            await service.override_score(
                100, final_score=4, override_reason="reviewed", overridden_by=7
            )


async def test_retry_only_failed() -> None:
    repo = FakeScoringJobRepository([_job(1, 100, "failed", attempt_count=1)])
    service = _service(repo)

    result = await service.retry(1)

    assert result.status == "queued"
    assert result.attempt_count == 2
    assert repo.mark_retried_calls == [(1, ANY)]

    scored_repo = FakeScoringJobRepository([_job(2, 101, "scored")])
    scored_service = _service(scored_repo)

    with pytest.raises(ScoringJobInvalidTransitionError):
        await scored_service.retry(2)


async def test_reset_for_answer_upserts() -> None:
    repo = FakeScoringJobRepository()
    service = _service(repo)

    await service.reset_for_answer(100, status="queued")
    await service.reset_for_answer(100, status="needs_a_person")

    assert repo.upsert_calls == [(100, "queued"), (100, "needs_a_person")]
