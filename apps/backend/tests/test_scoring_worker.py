import asyncio
from datetime import UTC, datetime

from api.scoring.application.ports import LlmError, LlmScore
from api.scoring.application.worker import ScoringWorker
from api.scoring.domain.entities import ScoringInput, ScoringJob


def _job(job_id: int = 1, answer_id: int = 100) -> ScoringJob:
    return ScoringJob(
        id=job_id,
        answer_id=answer_id,
        status="queued",
        suggested_score=None,
        suggested_reasoning=None,
        final_score=None,
        override_reason=None,
        overridden_by=None,
        attempt_count=0,
        last_error=None,
        claimed_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        scored_at=None,
    )


class FakeScoringLlm:
    def __init__(self, result: LlmScore | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.score_calls: list[tuple] = []

    async def score(
        self,
        prompt: str,
        grading_guide: dict[str, str],
        answer_text: str,
    ) -> LlmScore:
        self.score_calls.append((prompt, grading_guide, answer_text))
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


class FakeScoringJobRepository:
    def __init__(self, *, queued: list[ScoringJob], stop_event: asyncio.Event) -> None:
        self._queue = list(queued)
        self._stop_event = stop_event
        self._input = ScoringInput(
            answer_id=100,
            prompt="What is 2+2?",
            grading_guide={"1": "Bad", "4": "Great"},
            answer_text="4",
        )
        self.mark_scored_calls: list[tuple] = []
        self.record_failure_calls: list[tuple] = []

    async def claim_next_queued(self, now: datetime) -> ScoringJob | None:
        self._stop_event.set()
        if self._queue:
            return self._queue.pop(0)
        return None

    async def load_scoring_input(self, answer_id: int) -> ScoringInput | None:
        if answer_id == 100:
            return self._input
        return None

    async def mark_scored(
        self,
        job_id: int,
        *,
        suggested_score: int,
        suggested_reasoning: str,
        now: datetime,
    ) -> ScoringJob:
        self.mark_scored_calls.append((job_id, suggested_score, suggested_reasoning, now))
        return _job(job_id)

    async def record_failure(
        self,
        job_id: int,
        *,
        error: str,
        now: datetime,
        max_attempts: int,
    ) -> ScoringJob:
        self.record_failure_calls.append((job_id, error, now, max_attempts))
        return _job(job_id)


class FakeScoringUnitOfWork:
    def __init__(self, repo: FakeScoringJobRepository) -> None:
        self.scoring_jobs = repo

    async def __aenter__(self) -> FakeScoringUnitOfWork:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


def _worker(
    repo: FakeScoringJobRepository,
    llm: FakeScoringLlm,
    stop_event: asyncio.Event,
    *,
    max_attempts: int = 3,
) -> ScoringWorker:
    return ScoringWorker(
        lambda: FakeScoringUnitOfWork(repo),
        llm,
        max_attempts=max_attempts,
        poll_interval_seconds=0,
        stop_event=stop_event,
    )


async def test_worker_scores_queued_job() -> None:
    stop_event = asyncio.Event()
    repo = FakeScoringJobRepository(queued=[_job()], stop_event=stop_event)
    llm = FakeScoringLlm(result=LlmScore(3, "solid answer"))

    await _worker(repo, llm, stop_event).run()

    assert len(repo.mark_scored_calls) == 1
    job_id, score, reasoning, _ = repo.mark_scored_calls[0]
    assert job_id == 1
    assert score == 3
    assert reasoning == "solid answer"


async def test_worker_requeues_then_fails() -> None:
    stop_event = asyncio.Event()
    repo = FakeScoringJobRepository(queued=[_job()], stop_event=stop_event)
    llm = FakeScoringLlm(error=LlmError("boom"))

    await _worker(repo, llm, stop_event, max_attempts=3).run()

    assert len(repo.record_failure_calls) == 1
    job_id, error, _, max_attempts = repo.record_failure_calls[0]
    assert job_id == 1
    assert error == "boom"
    assert max_attempts == 3


async def test_worker_sleeps_when_empty() -> None:
    stop_event = asyncio.Event()
    repo = FakeScoringJobRepository(queued=[], stop_event=stop_event)
    llm = FakeScoringLlm(result=LlmScore(3, "unused"))

    await _worker(repo, llm, stop_event).run()

    assert repo.mark_scored_calls == []
    assert repo.record_failure_calls == []
