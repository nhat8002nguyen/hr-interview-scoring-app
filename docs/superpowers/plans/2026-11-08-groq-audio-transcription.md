# Groq Audio Transcription Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transcribe audio answers with Groq Whisper inside the existing scoring worker, persist the transcript on `answers.text`, then score with DeepSeek so new audio reaches `scored` automatically.

**Architecture:** Extend `ScoringInput` so audio rows load without text. Add `TranscriptionPort` + Groq multipart adapter. In one worker claim, transcribe when needed, save text, then call `ScoringLlmPort`. Transcription exhaustion terminates as `needs_a_person`; scoring exhaustion stays `failed`. Live submit and import enqueue audio as `queued`.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2 async, httpx, Groq OpenAI-compatible `/audio/transcriptions`, existing DeepSeek scoring path, pytest.

**Spec:** `docs/superpowers/specs/2026-11-08-groq-audio-transcription-design.md`

## Global Constraints

- No new tables or status enum values.
- English only: always pass `language=en` to Groq.
- Default model `whisper-large-v3`; base URL `https://api.groq.com/openai/v1`.
- Shared `attempt_count` for transcribe + score on one job.
- Do not migrate existing `needs_a_person` rows.
- Retry endpoint stays `failed`-only.
- CI must not call real Groq; use fakes / httpx MockTransport.
- No em dashes in docs/strings; commit messages must not carry an agent co-author trailer.
- Run backend tests with `uv run pytest` from `apps/backend/`.

---

## File Structure

```text
apps/backend/src/api/
  config.py                                          # groq_* settings; lease bump
  main.py                                            # wire Groq + FileStorage into worker
  scoring/
    domain/entities.py                               # ScoringInput gains answer_type, audio_key; nullable text
    domain/repositories.py                           # update_answer_text; record_failure exhausted_status
    application/ports.py                             # TranscriptionPort, TranscriptionError
    application/worker.py                            # transcribe-then-score branch
    infrastructure/repository.py                     # load/update/failure SQL
    infrastructure/groq_transcription.py             # NEW Groq adapter
  candidates/application/service.py                  # audio enqueue queued
  importing/application/service.py                   # audio increments scoring_jobs_queued
apps/backend/tests/
  test_scoring_job_repository_sql.py
  test_groq_transcription.py                         # NEW
  test_scoring_worker.py
  test_candidates_service.py
  test_import_service.py
  test_import_router.py
  test_e2e_import_and_score.py
apps/backend/{README.md,.env.example,docker-compose.yml}
deploy/{.env.example,docker-compose.yml,README.md}   # as needed
scripts/smoke_integration.py
.env.example
```

---

### Task 1: ScoringInput + repository transcription support

**Files:**
- Modify: `apps/backend/src/api/scoring/domain/entities.py`
- Modify: `apps/backend/src/api/scoring/domain/repositories.py`
- Modify: `apps/backend/src/api/scoring/infrastructure/repository.py`
- Modify: `apps/backend/tests/test_scoring_job_repository_sql.py`

**Interfaces:**
- Consumes: existing `ScoringJobModel`, `AnswerModel`, `QuestionModel`
- Produces:
  - `ScoringInput(answer_id, prompt, grading_guide, answer_text: str | None, answer_type: str, audio_key: str | None)`
  - `ScoringJobRepository.update_answer_text(answer_id: int, text: str) -> None`
  - `ScoringJobRepository.record_failure(..., exhausted_status: str = "failed")`
  - `build_record_failure_statement(..., exhausted_status: str = "failed")`
  - `build_load_scoring_input_statement` selects `text`, `answer_type`, `audio_key`, `prompt`, `grading_guide`
  - `load_scoring_input` returns a row even when `text` is null (still `None` only if the answer row is missing)

- [ ] **Step 1: Write the failing SQL/shape tests**

Extend `apps/backend/tests/test_scoring_job_repository_sql.py`:

```python
def test_record_failure_can_exhaust_to_needs_a_person() -> None:
    stmt = build_record_failure_statement(
        1, "boom", datetime.now(UTC), 3, exhausted_status="needs_a_person"
    )
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "needs_a_person" in sql
    assert "failed" not in sql.replace("needs_a_person", "")


def test_load_scoring_input_includes_audio_fields() -> None:
    sql = str(build_load_scoring_input_statement(1).compile(dialect=postgresql.dialect()))
    assert "answers.answer_type" in sql
    assert "answers.audio_key" in sql
```

Keep existing `test_record_failure_transitions` asserting default exhausted status still uses `failed`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/backend && uv run pytest tests/test_scoring_job_repository_sql.py -q`
Expected: FAIL (missing `exhausted_status` / columns).

- [ ] **Step 3: Implement entity + repository changes**

Update `ScoringInput`:

```python
@dataclass(frozen=True, slots=True)
class ScoringInput:
    answer_id: int
    prompt: str
    grading_guide: dict[str, str]
    answer_text: str | None
    answer_type: str
    audio_key: str | None
```

Update `build_load_scoring_input_statement` to select `AnswerModel.text`, `AnswerModel.answer_type`, `AnswerModel.audio_key`, `QuestionModel.prompt`, `QuestionModel.grading_guide`.

Change `load_scoring_input` so a missing join row returns `None`, but a present answer with `text is None` still returns `ScoringInput`.

Add:

```python
async def update_answer_text(self, answer_id: int, text: str) -> None:
    await self._session.execute(
        update(AnswerModel).where(AnswerModel.id == answer_id).values(text=text)
    )
```

Change `build_record_failure_statement` / `record_failure` to accept `exhausted_status: str = "failed"` and use that literal in the CASE arm instead of hard-coded `'failed'`.

Update the protocol in `domain/repositories.py` to match.

Fix any in-repo callers/fakes that construct `ScoringInput` (worker tests, etc.) so the suite still type-checks after this task; worker behavior changes come in Task 3.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/backend && uv run pytest tests/test_scoring_job_repository_sql.py -q`
Expected: PASS

Also run a quick compile check on worker tests if they break on `ScoringInput` construction; fix constructors only.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/src/api/scoring/domain/entities.py \
  apps/backend/src/api/scoring/domain/repositories.py \
  apps/backend/src/api/scoring/infrastructure/repository.py \
  apps/backend/tests/test_scoring_job_repository_sql.py \
  apps/backend/tests/test_scoring_worker.py
git commit -m "feat(scoring): load audio fields and terminal needs_a_person failures"
```

---

### Task 2: TranscriptionPort + Groq adapter

**Files:**
- Modify: `apps/backend/src/api/scoring/application/ports.py`
- Create: `apps/backend/src/api/scoring/infrastructure/groq_transcription.py`
- Create: `apps/backend/tests/test_groq_transcription.py`

**Interfaces:**
- Consumes: httpx
- Produces:
  - `class TranscriptionError(Exception)`
  - `class TranscriptionPort(Protocol): async def transcribe(self, data: bytes, *, filename: str, language: str = "en") -> str`
  - `class GroqTranscription` implementing the port; `aclose()` like DeepSeek

- [ ] **Step 1: Write the failing adapter tests**

Create `apps/backend/tests/test_groq_transcription.py` modeled on `test_scoring_llm.py`:

```python
import httpx
import pytest

from api.scoring.application.ports import TranscriptionError
from api.scoring.infrastructure.groq_transcription import GroqTranscription


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_transcribe_posts_multipart_and_returns_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/audio/transcriptions")
        assert request.headers["Authorization"] == "Bearer test-key"
        assert b"whisper-large-v3" in request.content
        assert b'name="language"' in request.content and b"en" in request.content
        return httpx.Response(200, json={"text": " hello world "})

    groq = GroqTranscription(
        "test-key",
        "whisper-large-v3",
        "https://api.groq.com/openai/v1",
        client=_client(handler),
    )
    text = await groq.transcribe(b"fake-audio", filename="answer.m4a", language="en")
    assert text == "hello world"
    await groq.aclose()


@pytest.mark.asyncio
async def test_transcribe_http_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="nope")

    groq = GroqTranscription(
        "test-key",
        "whisper-large-v3",
        "https://api.groq.com/openai/v1",
        client=_client(handler),
    )
    with pytest.raises(TranscriptionError):
        await groq.transcribe(b"x", filename="a.m4a")
    await groq.aclose()


@pytest.mark.asyncio
async def test_transcribe_empty_text_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"text": "   "})

    groq = GroqTranscription(
        "test-key",
        "whisper-large-v3",
        "https://api.groq.com/openai/v1",
        client=_client(handler),
    )
    with pytest.raises(TranscriptionError):
        await groq.transcribe(b"x", filename="a.m4a")
    await groq.aclose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/backend && uv run pytest tests/test_groq_transcription.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement port + adapter**

In `ports.py` add `TranscriptionError` and `TranscriptionPort`.

Create `groq_transcription.py`:

```python
class GroqTranscription:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        client: httpx.AsyncClient | None = None,
    ) -> None: ...

    async def transcribe(
        self,
        data: bytes,
        *,
        filename: str,
        language: str = "en",
    ) -> str:
        # multipart: file=(filename, data), model, language, response_format=json
        # POST {base_url}/audio/transcriptions
        # raise TranscriptionError on HTTPError / non-object / blank strip()
        # return stripped text
```

Mirror DeepSeek's owned-client / `aclose` pattern.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/backend && uv run pytest tests/test_groq_transcription.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/backend/src/api/scoring/application/ports.py \
  apps/backend/src/api/scoring/infrastructure/groq_transcription.py \
  apps/backend/tests/test_groq_transcription.py
git commit -m "feat(scoring): add Groq transcription adapter"
```

---

### Task 3: ScoringWorker transcribe-then-score

**Files:**
- Modify: `apps/backend/src/api/scoring/application/worker.py`
- Modify: `apps/backend/tests/test_scoring_worker.py`

**Interfaces:**
- Consumes: `TranscriptionPort`, `FileStorage` (from `api.candidates.application.ports`), Task 1 repository methods, `ScoringLlmPort`
- Produces: worker behavior per spec section 4.2 / 4.3

- [ ] **Step 1: Write the failing worker tests**

Extend fakes and add tests in `test_scoring_worker.py`:

```python
class FakeTranscription:
    def __init__(self, text: str | None = None, error: Exception | None = None) -> None:
        self._text = text
        self._error = error
        self.calls: list[tuple[bytes, str]] = []

    async def transcribe(self, data: bytes, *, filename: str, language: str = "en") -> str:
        self.calls.append((data, filename))
        if self._error is not None:
            raise self._error
        assert self._text is not None
        return self._text


class FakeFileStorage:
    def __init__(self, blobs: dict[str, bytes]) -> None:
        self._blobs = blobs

    async def read(self, key: str) -> bytes:
        return self._blobs[key]
```

Update `FakeScoringJobRepository` for new `ScoringInput` fields, `update_answer_text`, and `record_failure(..., exhausted_status=...)`.

Update `_worker` to accept `transcription` and `file_storage` (use no-op fakes for text-only tests).

Add cases:
1. Audio without text: transcription called, `update_answer_text` called, LLM scored with transcript, `mark_scored`.
2. Empty/TranscriptionError with `max_attempts=1`: `record_failure` called with `exhausted_status="needs_a_person"`.
3. Audio that already has text: transcription not called; LLM scores existing text.
4. Text answer path: transcription not called (existing score test still passes).
5. After successful transcript save, LLM `LlmError` with `max_attempts=1`: `record_failure` with default/`failed` exhausted status; text retained via prior `update_answer_text`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/backend && uv run pytest tests/test_scoring_worker.py -q`
Expected: FAIL (worker signature / behavior missing).

- [ ] **Step 3: Implement worker**

```python
class ScoringWorker:
    def __init__(
        self,
        uow_factory: ScoringUnitOfWorkFactory,
        llm: ScoringLlmPort,
        *,
        transcription: TranscriptionPort,
        file_storage: FileStorage,
        max_attempts: int,
        poll_interval_seconds: float,
        stop_event: asyncio.Event,
    ) -> None: ...

    async def _process(self, job: ScoringJob) -> None:
        async with self._uow_factory() as uow:
            scoring_input = await uow.scoring_jobs.load_scoring_input(job.answer_id)
        if scoring_input is None:
            raise LlmError("scoring input missing")

        answer_text = (scoring_input.answer_text or "").strip()
        if scoring_input.answer_type == "audio" and not answer_text:
            if not scoring_input.audio_key:
                raise TranscriptionError("audio answer missing audio_key")
            data = await self._file_storage.read(scoring_input.audio_key)
            filename = Path(scoring_input.audio_key).name or "audio.m4a"
            answer_text = await self._transcription.transcribe(
                data, filename=filename, language="en"
            )
            async with self._uow_factory() as uow:
                await uow.scoring_jobs.update_answer_text(job.answer_id, answer_text)

        result = await self._llm.score(
            scoring_input.prompt,
            scoring_input.grading_guide,
            answer_text,
        )
        async with self._uow_factory() as uow:
            await uow.scoring_jobs.mark_scored(...)

    async def _record_failure(self, job: ScoringJob, exc: Exception) -> None:
        exhausted_status = (
            "needs_a_person" if isinstance(exc, TranscriptionError) else "failed"
        )
        async with self._uow_factory() as uow:
            await uow.scoring_jobs.record_failure(
                job.id,
                error=str(exc),
                now=datetime.now(UTC),
                max_attempts=self._max_attempts,
                exhausted_status=exhausted_status,
            )
```

Catch storage read failures and wrap as `TranscriptionError` so missing blobs terminate as `needs_a_person`.

Update `main.py` call sites only enough that imports still work if required by other tests in this task; full wiring is Task 5. Prefer updating the constructor and fixing e2e construction in Task 4/5 if that keeps this commit focused - but do not leave `main.py` broken. Minimal wire with a no-op or real Groq in Task 5 is fine if Task 3 would otherwise break app startup tests; if there are no startup tests failing, update `main.py` in Task 5 and temporarily keep tests constructing the new args.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/backend && uv run pytest tests/test_scoring_worker.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/backend/src/api/scoring/application/worker.py \
  apps/backend/tests/test_scoring_worker.py
git commit -m "feat(scoring): transcribe audio before LLM scoring in worker"
```

---

### Task 4: Enqueue audio as queued + import summary

**Files:**
- Modify: `apps/backend/src/api/candidates/application/service.py`
- Modify: `apps/backend/src/api/importing/application/service.py`
- Modify: `apps/backend/tests/test_candidates_service.py`
- Modify: `apps/backend/tests/test_import_service.py`
- Modify: `apps/backend/tests/test_import_router.py`
- Modify: `apps/backend/tests/test_e2e_import_and_score.py`

**Interfaces:**
- Consumes: existing `reset_for_answer` / `import_answer`
- Produces: audio submit + import use `status="queued"`; import increments `scoring_jobs_queued` for audio (not `audio_answers_needing_person`)

- [ ] **Step 1: Update failing expectations first**

In `test_candidates_service.py` (`test_submit_audio_requires_person`):
- Rename to `test_submit_audio_enqueues_queued`
- Assert `reset_calls == [(result.answer.id, "queued")]`

In `test_import_service.py` (`test_import_audio_is_needs_a_person`):
- Rename to `test_import_audio_enqueues_queued`
- Assert `summary.scoring_jobs_queued` includes the audio row and `audio_answers_needing_person == 0`

In `test_import_router.py`: set fake summary `audio_answers_needing_person=0` and `scoring_jobs_queued` accordingly; assert JSON matches.

In `test_e2e_import_and_score.py`:
- Fresh import: `scoring_jobs_queued == 35` (30 text + 5 audio), `audio_answers_needing_person == 0`
- Worker construction must pass fake transcription + file storage that can read imported keys
- After drain: audio jobs are `scored` (not `needs_a_person`), with scores set like text

- [ ] **Step 2: Run targeted tests to verify they fail**

Run: `cd apps/backend && uv run pytest tests/test_candidates_service.py::test_submit_audio_enqueues_queued tests/test_import_service.py::test_import_audio_enqueues_queued -q`
Expected: FAIL on old status / counts.

- [ ] **Step 3: Implement enqueue + import counting**

In `AnswersService.submit_audio`, pass `status="queued"`.
In `AnswersService.import_answer`, use `status = "queued"` for both text and audio (or always `"queued"`).

In `ImportService`, when an audio answer changes, do `scoring_jobs_queued += 1` instead of `audio_answers_needing_person += 1`. Keep the summary field on the dataclass (it will be `0` for fresh imports).

Update e2e worker to use a `FakeTranscription` that returns a fixed string and a `LocalFileStorage` already used in that test so audio files are readable.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/backend && uv run pytest tests/test_candidates_service.py tests/test_import_service.py tests/test_import_router.py tests/test_e2e_import_and_score.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/backend/src/api/candidates/application/service.py \
  apps/backend/src/api/importing/application/service.py \
  apps/backend/tests/test_candidates_service.py \
  apps/backend/tests/test_import_service.py \
  apps/backend/tests/test_import_router.py \
  apps/backend/tests/test_e2e_import_and_score.py
git commit -m "feat: enqueue audio answers for automatic transcription scoring"
```

---

### Task 5: Config, wiring, docs, smoke

**Files:**
- Modify: `apps/backend/src/api/config.py`
- Modify: `apps/backend/src/api/main.py`
- Modify: `apps/backend/.env.example`
- Modify: `apps/backend/docker-compose.yml`
- Modify: `apps/backend/README.md`
- Modify: `.env.example`
- Modify: `deploy/.env.example`
- Modify: `deploy/docker-compose.yml` (if env block lists DeepSeek vars)
- Modify: `deploy/README.md` (brief Groq note)
- Modify: `scripts/smoke_integration.py`
- Modify: root `README.md` only if it still claims audio stays `needs_a_person` on the happy path

**Interfaces:**
- Consumes: Task 2 `GroqTranscription`, Task 3 worker constructor
- Produces: app boots with Groq + storage wired; docs list `GROQ_*`

- [ ] **Step 1: Add settings**

```python
groq_api_key: str = ""
groq_model: str = "whisper-large-v3"
groq_base_url: str = "https://api.groq.com/openai/v1"
scoring_lease_timeout_seconds: int = 600  # was 300; covers Groq + DeepSeek
```

- [ ] **Step 2: Wire main.py**

```python
transcription = GroqTranscription(
    configured.groq_api_key,
    configured.groq_model,
    configured.groq_base_url,
)
# ScoringWorker(..., transcription=transcription, file_storage=file_storage, ...)
# on shutdown: await transcription.aclose() alongside llm.aclose()
```

- [ ] **Step 3: Update env examples, compose, READMEs**

Document `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_BASE_URL`.
Pass them through docker-compose like DeepSeek.
Note that new audio is transcribed then scored; `needs_a_person` is the transcription-failure fallback.

- [ ] **Step 4: Update smoke script**

In `scripts/smoke_integration.py`, wait for the audio answer to reach `scored` (same polling style as text), or accept `needs_a_person` only if you are intentionally testing without Groq.
Default happy path: expect `scored` when Groq key is configured; if the script currently asserts immediate `needs_a_person` after upload, change it to poll until `scored` / terminal state with a clear failure message.

Also update import assertions: `audio_answers_needing_person` expected `0` and queued count includes audio if the script checks those numbers.

- [ ] **Step 5: Run full backend suite**

Run: `cd apps/backend && uv run pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add apps/backend/src/api/config.py apps/backend/src/api/main.py \
  apps/backend/.env.example apps/backend/docker-compose.yml apps/backend/README.md \
  .env.example deploy/.env.example deploy/docker-compose.yml deploy/README.md \
  scripts/smoke_integration.py README.md
git commit -m "feat: wire Groq transcription config into API and deploy docs"
```

---

## Spec coverage check

| Spec requirement | Task |
|---|---|
| Single worker claim: transcribe then score | 3 |
| Groq Whisper adapter, `language=en`, default model | 2, 5 |
| Persist transcript on `answers.text` | 1, 3 |
| Audio enqueue `queued` (live + import) | 4 |
| Transcription exhaustion -> `needs_a_person` | 1, 3 |
| Scoring exhaustion -> `failed`, text retained | 3 |
| Skip Groq when text already present | 3 |
| No migration of old `needs_a_person` | 4 (no migration code) |
| Retry stays failed-only | unchanged |
| Config / docs / smoke | 5 |
| Tests with fakes, no real Groq in CI | 2, 3, 4 |
| Lease timeout bump | 5 (`600`) |
