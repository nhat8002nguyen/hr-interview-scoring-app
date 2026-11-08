import asyncio
from datetime import UTC, datetime

import pytest

from api.scoring.application.ports import LlmError, LlmScore, TranscriptionError
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


def _scoring_input(
    *,
    answer_text: str | None = "4",
    answer_type: str = "text",
    audio_key: str | None = None,
) -> ScoringInput:
    return ScoringInput(
        answer_id=100,
        prompt="What is 2+2?",
        grading_guide={"1": "Bad", "4": "Great"},
        answer_text=answer_text,
        answer_type=answer_type,
        audio_key=audio_key,
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


class FakeTranscription:
    def __init__(self, text: str | None = None, error: Exception | None = None) -> None:
        self._text = text
        self._error = error
        self.calls: list[tuple[bytes, str, str]] = []

    async def transcribe(self, data: bytes, *, filename: str, language: str = "en") -> str:
        self.calls.append((data, filename, language))
        if self._error is not None:
            raise self._error
        assert self._text is not None
        return self._text


class FakeFileStorage:
    def __init__(
        self,
        blobs: dict[str, bytes] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._blobs = blobs or {}
        self._error = error
        self.read_calls: list[str] = []

    async def read(self, key: str) -> bytes:
        self.read_calls.append(key)
        if self._error is not None:
            raise self._error
        return self._blobs[key]


class FakeScoringJobRepository:
    def __init__(
        self,
        *,
        queued: list[ScoringJob],
        stop_event: asyncio.Event,
        scoring_input: ScoringInput | None = None,
    ) -> None:
        self._queue = list(queued)
        self._stop_event = stop_event
        self._input = scoring_input if scoring_input is not None else _scoring_input()
        self.mark_scored_calls: list[tuple] = []
        self.record_failure_calls: list[tuple] = []
        self.update_answer_text_calls: list[tuple[int, str]] = []

    async def claim_next_queued(self, now: datetime) -> ScoringJob | None:
        self._stop_event.set()
        if self._queue:
            return self._queue.pop(0)
        return None

    async def load_scoring_input(self, answer_id: int) -> ScoringInput | None:
        if answer_id == 100:
            return self._input
        return None

    async def update_answer_text(self, answer_id: int, text: str) -> None:
        self.update_answer_text_calls.append((answer_id, text))

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
        exhausted_status: str = "failed",
    ) -> ScoringJob:
        self.record_failure_calls.append((job_id, error, now, max_attempts, exhausted_status))
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
    transcription: FakeTranscription | None = None,
    file_storage: FakeFileStorage | None = None,
) -> ScoringWorker:
    return ScoringWorker(
        lambda: FakeScoringUnitOfWork(repo),
        llm,
        transcription=transcription or FakeTranscription(),
        file_storage=file_storage or FakeFileStorage(),
        max_attempts=max_attempts,
        poll_interval_seconds=0,
        stop_event=stop_event,
    )


async def test_worker_scores_queued_job() -> None:
    stop_event = asyncio.Event()
    repo = FakeScoringJobRepository(queued=[_job()], stop_event=stop_event)
    llm = FakeScoringLlm(result=LlmScore(3, "solid answer"))
    transcription = FakeTranscription()

    await _worker(repo, llm, stop_event, transcription=transcription).run()

    assert transcription.calls == []
    assert repo.update_answer_text_calls == []
    assert len(repo.mark_scored_calls) == 1
    job_id, score, reasoning, _ = repo.mark_scored_calls[0]
    assert job_id == 1
    assert score == 3
    assert reasoning == "solid answer"
    assert llm.score_calls == [("What is 2+2?", {"1": "Bad", "4": "Great"}, "4")]


async def test_worker_requeues_then_fails() -> None:
    stop_event = asyncio.Event()
    repo = FakeScoringJobRepository(queued=[_job()], stop_event=stop_event)
    llm = FakeScoringLlm(error=LlmError("boom"))

    await _worker(repo, llm, stop_event, max_attempts=3).run()

    assert len(repo.record_failure_calls) == 1
    job_id, error, _, max_attempts, exhausted_status = repo.record_failure_calls[0]
    assert job_id == 1
    assert error == "boom"
    assert max_attempts == 3
    assert exhausted_status == "failed"


async def test_worker_sleeps_when_empty() -> None:
    stop_event = asyncio.Event()
    repo = FakeScoringJobRepository(queued=[], stop_event=stop_event)
    llm = FakeScoringLlm(result=LlmScore(3, "unused"))

    await _worker(repo, llm, stop_event).run()

    assert repo.mark_scored_calls == []
    assert repo.record_failure_calls == []


@pytest.mark.parametrize("answer_text", [None, "", "   "])
async def test_worker_transcribes_blank_audio_then_scores(answer_text: str | None) -> None:
    stop_event = asyncio.Event()
    repo = FakeScoringJobRepository(
        queued=[_job()],
        stop_event=stop_event,
        scoring_input=_scoring_input(
            answer_text=answer_text,
            answer_type="audio",
            audio_key="clips/answer.m4a",
        ),
    )
    llm = FakeScoringLlm(result=LlmScore(3, "solid answer"))
    transcription = FakeTranscription(text="four")
    storage = FakeFileStorage({"clips/answer.m4a": b"audio-bytes"})

    await _worker(
        repo,
        llm,
        stop_event,
        transcription=transcription,
        file_storage=storage,
    ).run()

    assert transcription.calls == [(b"audio-bytes", "answer.m4a", "en")]
    assert repo.update_answer_text_calls == [(100, "four")]
    assert llm.score_calls == [("What is 2+2?", {"1": "Bad", "4": "Great"}, "four")]
    assert len(repo.mark_scored_calls) == 1
    job_id, score, reasoning, _ = repo.mark_scored_calls[0]
    assert job_id == 1
    assert score == 3
    assert reasoning == "solid answer"
    assert repo.record_failure_calls == []


async def test_worker_transcription_error_needs_a_person() -> None:
    stop_event = asyncio.Event()
    repo = FakeScoringJobRepository(
        queued=[_job()],
        stop_event=stop_event,
        scoring_input=_scoring_input(
            answer_text=None,
            answer_type="audio",
            audio_key="clips/answer.m4a",
        ),
    )
    llm = FakeScoringLlm(result=LlmScore(3, "unused"))
    transcription = FakeTranscription(error=TranscriptionError("empty transcript"))
    storage = FakeFileStorage({"clips/answer.m4a": b"audio-bytes"})

    await _worker(
        repo,
        llm,
        stop_event,
        transcription=transcription,
        file_storage=storage,
        max_attempts=1,
    ).run()

    assert llm.score_calls == []
    assert repo.update_answer_text_calls == []
    assert repo.mark_scored_calls == []
    assert len(repo.record_failure_calls) == 1
    job_id, error, _, max_attempts, exhausted_status = repo.record_failure_calls[0]
    assert job_id == 1
    assert error == "empty transcript"
    assert max_attempts == 1
    assert exhausted_status == "needs_a_person"


async def test_worker_storage_failure_needs_a_person() -> None:
    stop_event = asyncio.Event()
    repo = FakeScoringJobRepository(
        queued=[_job()],
        stop_event=stop_event,
        scoring_input=_scoring_input(
            answer_text=None,
            answer_type="audio",
            audio_key="clips/missing.m4a",
        ),
    )
    llm = FakeScoringLlm(result=LlmScore(3, "unused"))
    transcription = FakeTranscription(text="should not run")
    storage = FakeFileStorage(error=FileNotFoundError("clips/missing.m4a"))

    await _worker(
        repo,
        llm,
        stop_event,
        transcription=transcription,
        file_storage=storage,
        max_attempts=1,
    ).run()

    assert transcription.calls == []
    assert llm.score_calls == []
    assert repo.update_answer_text_calls == []
    assert repo.mark_scored_calls == []
    job_id, error, _, max_attempts, exhausted_status = repo.record_failure_calls[0]
    assert job_id == 1
    assert "clips/missing.m4a" in error
    assert max_attempts == 1
    assert exhausted_status == "needs_a_person"


async def test_worker_missing_audio_key_needs_a_person() -> None:
    stop_event = asyncio.Event()
    repo = FakeScoringJobRepository(
        queued=[_job()],
        stop_event=stop_event,
        scoring_input=_scoring_input(answer_text=None, answer_type="audio", audio_key=None),
    )
    llm = FakeScoringLlm(result=LlmScore(3, "unused"))
    transcription = FakeTranscription(text="should not run")
    storage = FakeFileStorage()

    await _worker(
        repo,
        llm,
        stop_event,
        transcription=transcription,
        file_storage=storage,
        max_attempts=1,
    ).run()

    assert storage.read_calls == []
    assert transcription.calls == []
    assert llm.score_calls == []
    assert repo.update_answer_text_calls == []
    _, error, _, _, exhausted_status = repo.record_failure_calls[0]
    assert "audio_key" in error
    assert exhausted_status == "needs_a_person"


async def test_worker_skips_transcription_when_audio_text_present() -> None:
    stop_event = asyncio.Event()
    repo = FakeScoringJobRepository(
        queued=[_job()],
        stop_event=stop_event,
        scoring_input=_scoring_input(
            answer_text="already transcribed",
            answer_type="audio",
            audio_key="clips/answer.m4a",
        ),
    )
    llm = FakeScoringLlm(result=LlmScore(2, "ok"))
    transcription = FakeTranscription(text="should not run")
    storage = FakeFileStorage({"clips/answer.m4a": b"audio-bytes"})

    await _worker(
        repo,
        llm,
        stop_event,
        transcription=transcription,
        file_storage=storage,
    ).run()

    assert storage.read_calls == []
    assert transcription.calls == []
    assert repo.update_answer_text_calls == []
    assert llm.score_calls == [("What is 2+2?", {"1": "Bad", "4": "Great"}, "already transcribed")]
    assert len(repo.mark_scored_calls) == 1


async def test_worker_scoring_failure_after_transcript_is_failed() -> None:
    stop_event = asyncio.Event()
    repo = FakeScoringJobRepository(
        queued=[_job()],
        stop_event=stop_event,
        scoring_input=_scoring_input(
            answer_text=None,
            answer_type="audio",
            audio_key="clips/answer.m4a",
        ),
    )
    llm = FakeScoringLlm(error=LlmError("score boom"))
    transcription = FakeTranscription(text="four")
    storage = FakeFileStorage({"clips/answer.m4a": b"audio-bytes"})

    await _worker(
        repo,
        llm,
        stop_event,
        transcription=transcription,
        file_storage=storage,
        max_attempts=1,
    ).run()

    assert repo.update_answer_text_calls == [(100, "four")]
    assert llm.score_calls == [("What is 2+2?", {"1": "Bad", "4": "Great"}, "four")]
    assert repo.mark_scored_calls == []
    job_id, error, _, max_attempts, exhausted_status = repo.record_failure_calls[0]
    assert job_id == 1
    assert error == "score boom"
    assert max_attempts == 1
    assert exhausted_status == "failed"
