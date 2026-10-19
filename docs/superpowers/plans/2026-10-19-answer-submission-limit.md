# Answer Submission Limit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cap each candidate at a configurable number of distinct answer submissions per question (default 3), surface remaining attempts to the candidate, and reject further changed submissions with `409`.

**Architecture:** Reuse the existing `answers.version` column as the submission counter (it increments only on changed content). Enforce the cap atomically inside the upsert's `ON CONFLICT ... DO UPDATE ... WHERE version < max_submissions`, so concurrent submits cannot exceed it. The service disambiguates unchanged vs. exhausted after the upsert. The candidate API exposes `max_submissions` and per-question `attempts_remaining`; the candidate web app renders them and disables submit at zero.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy async, PostgreSQL, pytest; Next.js 16, React 19, TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-19-answer-submission-limit-design.md`

## Global Constraints

- `MAX_ANSWER_SUBMISSIONS` defaults to `3`; it is a single global value, not per-question.
- Only a *changed* answer consumes an attempt; byte-identical resubmission stays an idempotent no-op.
- `attempts_remaining = max(0, max_submissions - version)`, with `version = 0` while unanswered.
- Exhaustion returns `409 Conflict` as RFC 7807 problem details.
- The candidate area must never expose `grading_guide` or any score.
- No database migration: `answers.version` already provides the counter.

## Review Focus

These edge classes are implied by the spec and pinned by tests in the owning task below:

1. Two changed submits racing at the version boundary must not exceed the cap - atomic SQL guard, `test_upsert_guards_against_exceeding_max_submissions` (Task 1).
2. The configured limit lowered below an existing answer's `version` must clamp to `0` and reject further submits - `test_attempts_remaining_clamps_to_zero` (Task 1).
3. An audio resubmit rejected at the limit must not overwrite the accepted recording - `test_submit_audio_at_limit_does_not_overwrite_accepted_file` (Task 1).
4. An unanswered question must report the full limit - `test_interview_reports_attempts_remaining` (Task 2).
5. A byte-identical resubmission must not consume an attempt - `test_unchanged_resubmission_does_not_consume_attempt` (Task 1).

---

### Task 1: Backend limit enforcement

**Files:**
- Modify: `apps/backend/src/api/config.py`
- Modify: `apps/backend/src/api/candidates/domain/exceptions.py`
- Modify: `apps/backend/src/api/candidates/domain/repositories.py`
- Modify: `apps/backend/src/api/candidates/infrastructure/repository.py`
- Modify: `apps/backend/src/api/candidates/application/service.py`
- Modify: `apps/backend/src/api/main.py`
- Test: `apps/backend/tests/test_answer_upsert_sql.py`
- Test: `apps/backend/tests/test_candidates_service.py`

**Interfaces:**
- Consumes: existing `Answer`, `AnswersService`, `SqlAlchemyAnswerRepository`, `build_upsert_statement`.
- Produces:
  - `Settings.max_answer_submissions: int = 3`
  - `AttemptsExhaustedError(question_id: int, max_submissions: int)` in `api.candidates.domain.exceptions`
  - `build_upsert_statement(answer: Answer, max_submissions: int) -> Insert`
  - `SqlAlchemyAnswerRepository.upsert(answer: Answer, *, max_submissions: int) -> tuple[Answer, bool]` (and the matching `AnswerRepository` protocol)
  - `AnswersService(..., max_submissions: int = 3)`, public attribute `max_submissions: int`, method `attempts_remaining(answer: Answer | None) -> int`

- [ ] **Step 1: Update the SQL test to the new signature and add the atomic-guard test**

In `apps/backend/tests/test_answer_upsert_sql.py`, change both existing calls to `build_upsert_statement(sample_answer(), max_submissions=3)` and append:

```python
def test_upsert_guards_against_exceeding_max_submissions() -> None:
    stmt = build_upsert_statement(sample_answer(), max_submissions=3)
    sql = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "answers.version < 3" in sql
```

- [ ] **Step 2: Run the SQL tests to verify they fail**

Run: `cd apps/backend && uv run pytest tests/test_answer_upsert_sql.py -q`
Expected: FAIL - `build_upsert_statement()` takes 1 positional argument but 2 were given.

- [ ] **Step 3: Implement config, exception, and the atomic upsert guard**

In `apps/backend/src/api/config.py` add alongside the scoring settings:

```python
max_answer_submissions: int = 3
```

In `apps/backend/src/api/candidates/domain/exceptions.py` add:

```python
class AttemptsExhaustedError(Exception):
    def __init__(self, question_id: int, max_submissions: int) -> None:
        super().__init__(
            f"Maximum submissions ({max_submissions}) reached for question {question_id}"
        )
        self.question_id = question_id
        self.max_submissions = max_submissions
```

In `apps/backend/src/api/candidates/domain/repositories.py` change the `AnswerRepository.upsert` signature to:

```python
async def upsert(self, answer: Answer, *, max_submissions: int) -> tuple[Answer, bool]: ...
```

In `apps/backend/src/api/candidates/infrastructure/repository.py` import `and_` from `sqlalchemy`, take `max_submissions: int` in `build_upsert_statement`, and replace the `where=` argument with:

```python
where=and_(
    AnswerModel.content_hash != statement.excluded.content_hash,
    AnswerModel.version < max_submissions,
),
```

Change `SqlAlchemyAnswerRepository.upsert` to `async def upsert(self, answer: Answer, *, max_submissions: int)` and pass `max_submissions` through to `build_upsert_statement`.

- [ ] **Step 4: Run the SQL tests to verify they pass**

Run: `cd apps/backend && uv run pytest tests/test_answer_upsert_sql.py -q`
Expected: PASS.

- [ ] **Step 5: Update the service test fake and add the service tests**

In `apps/backend/tests/test_candidates_service.py`:
- Import `AttemptsExhaustedError` from `api.candidates.domain.exceptions`.
- Change `FakeAnswerRepository.upsert` to `async def upsert(self, answer: Answer, *, max_submissions: int)`. In the changed-content branch, raise `AttemptsExhaustedError(answer.question_id, max_submissions)` when `existing.version >= max_submissions`; otherwise behave as today.
- Add `max_submissions: int = 3` to `_answers_service` and pass it to `AnswersService(..., max_submissions=max_submissions)`.

Append these tests:

```python
async def test_third_submit_is_accepted_and_fourth_changed_submit_is_rejected(tmp_path) -> None:
    service, _, _, _ = _answers_service(tmp_path, question_ids={7})

    first = await service.submit_text(candidate_id=1, question_id=7, text="a")
    second = await service.submit_text(candidate_id=1, question_id=7, text="b")
    third = await service.submit_text(candidate_id=1, question_id=7, text="c")

    assert [first.answer.version, second.answer.version, third.answer.version] == [1, 2, 3]
    with pytest.raises(AttemptsExhaustedError):
        await service.submit_text(candidate_id=1, question_id=7, text="d")


async def test_unchanged_resubmission_does_not_consume_attempt(tmp_path) -> None:
    service, _, _, _ = _answers_service(tmp_path, question_ids={7})

    first = await service.submit_text(candidate_id=1, question_id=7, text="a")
    again = await service.submit_text(candidate_id=1, question_id=7, text="a")

    assert again.unchanged is True
    assert service.attempts_remaining(again.answer) == 2
    assert service.attempts_remaining(first.answer) == 2


async def test_attempts_remaining_counts_changed_submissions(tmp_path) -> None:
    service, _, _, _ = _answers_service(tmp_path, question_ids={7})

    assert service.attempts_remaining(None) == 3
    result = await service.submit_text(candidate_id=1, question_id=7, text="a")
    assert service.attempts_remaining(result.answer) == 2


async def test_attempts_remaining_clamps_to_zero(tmp_path) -> None:
    answer = Answer(
        id=10,
        candidate_id=1,
        question_id=7,
        answer_type="text",
        text="old",
        audio_key=None,
        content_hash="old",
        version=5,
        external_ref=None,
        submitted_at=datetime.now(UTC),
    )
    service, _, _, _ = _answers_service(
        tmp_path, question_ids={7}, answers=[answer], max_submissions=2
    )

    assert service.attempts_remaining(answer) == 0


async def test_submit_audio_at_limit_does_not_overwrite_accepted_file(tmp_path) -> None:
    accepted = Answer(
        id=10,
        candidate_id=1,
        question_id=7,
        answer_type="audio",
        text=None,
        audio_key="audio/1/7.m4a",
        content_hash="accepted",
        version=3,
        external_ref=None,
        submitted_at=datetime.now(UTC),
    )
    service, _, _, file_storage = _answers_service(
        tmp_path, question_ids={7}, answers=[accepted]
    )
    await file_storage.save("audio/1/7.m4a", b"accepted")

    with pytest.raises(AttemptsExhaustedError):
        await service.submit_audio(
            candidate_id=1,
            question_id=7,
            data=b"rejected",
            filename="clip.m4a",
        )

    assert await file_storage.read("audio/1/7.m4a") == b"accepted"
```

- [ ] **Step 6: Run the service tests to verify they fail**

Run: `cd apps/backend && uv run pytest tests/test_candidates_service.py -q`
Expected: FAIL - the fake now requires the `max_submissions` keyword, `AnswersService.attempts_remaining` does not exist, and no `AttemptsExhaustedError` is raised.

- [ ] **Step 7: Implement the service enforcement and wiring**

In `apps/backend/src/api/candidates/application/service.py`:
- Import `AttemptsExhaustedError`.
- Add `max_submissions: int = 3` as the last `AnswersService.__init__` parameter and set `self.max_submissions = max_submissions`.
- Add:

```python
def attempts_remaining(self, answer: Answer | None) -> int:
    used = 0 if answer is None else answer.version
    return max(0, self.max_submissions - used)
```

- Replace `_submit` with:

```python
async def _submit(self, answer: Answer, *, status: str) -> SubmitResult:
    async with self._uow_factory() as uow:
        stored, changed = await uow.answers.upsert(
            answer, max_submissions=self.max_submissions
        )
    if changed:
        await self._scoring_jobs.reset_for_answer(stored.id, status=status)
        return SubmitResult(status="received", unchanged=False, answer=stored)
    if stored.content_hash == answer.content_hash:
        return SubmitResult(status="received", unchanged=True, answer=stored)
    raise AttemptsExhaustedError(answer.question_id, self.max_submissions)
```

- In `submit_audio`, after computing `content_hash` and before `self._file_storage.save`, read the active answer and short-circuit:

```python
async with self._uow_factory() as uow:
    active = await uow.answers.get_active(candidate_id, question_id)
if active is not None and active.content_hash == content_hash:
    return SubmitResult(status="received", unchanged=True, answer=active)
if active is not None and active.version >= self.max_submissions:
    raise AttemptsExhaustedError(question_id, self.max_submissions)
```

- In `import_answer`, pass `max_submissions=self.max_submissions` to `uow.answers.upsert`.

In `apps/backend/src/api/main.py`, pass `max_submissions=configured.max_answer_submissions` to the `AnswersService(...)` construction.

- [ ] **Step 8: Run the service tests to verify they pass**

Run: `cd apps/backend && uv run pytest tests/test_candidates_service.py tests/test_answer_upsert_sql.py -q`
Expected: PASS.

- [ ] **Step 9: Run the full backend suite and static checks**

Run: `cd apps/backend && uv run pytest -q && uv run ruff check . && uv run mypy libs src`
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add apps/backend/src/api/config.py \
  apps/backend/src/api/candidates/domain/exceptions.py \
  apps/backend/src/api/candidates/domain/repositories.py \
  apps/backend/src/api/candidates/infrastructure/repository.py \
  apps/backend/src/api/candidates/application/service.py \
  apps/backend/src/api/main.py \
  apps/backend/tests/test_answer_upsert_sql.py \
  apps/backend/tests/test_candidates_service.py
git commit -m "feat(backend): enforce per-question answer submission limit"
```

---

### Task 2: Backend API surface and contract doc

**Files:**
- Modify: `apps/backend/src/api/candidates/presentation/schemas.py`
- Modify: `apps/backend/src/api/candidates/presentation/candidate_router.py`
- Modify: `apps/backend/src/api/candidates/presentation/errors.py`
- Modify: `docs/superpowers/specs/2026-10-18-api-contract-design.md`
- Test: `apps/backend/tests/test_candidate_router.py`

**Interfaces:**
- Consumes: `AnswersService.attempts_remaining`, `AnswersService.max_submissions`, `AttemptsExhaustedError`.
- Produces:
  - `InterviewQuestion.attempts_remaining: int`
  - `InterviewResponse.max_submissions: int`
  - `SubmitResponse.attempts_remaining: int`
  - `409` handler for `AttemptsExhaustedError`

- [ ] **Step 1: Update the router-test fake and expected bodies**

In `apps/backend/tests/test_candidate_router.py`:
- Import `AttemptsExhaustedError`.
- Give `FakeAnswersService` a `max_submissions: int = 3` attribute and an `attempts_remaining(self, answer: Answer | None) -> int` method using the same clamp formula.
- In `FakeAnswersService._submit`, after the unchanged check, raise `AttemptsExhaustedError(question_id, self.max_submissions)` when `existing is not None and existing.version >= self.max_submissions`.

Update the expected JSON in existing tests:
- `test_interview_returns_questions_without_grades`: add `"attempts_remaining": 2` to Q1, `"attempts_remaining": 3` to Q2, and `"max_submissions": 3` at the top level.
- `test_submit_text_201_and_received`, `test_submit_unchanged_200`, `test_submit_audio_201`: add `"attempts_remaining": 2` to each expected body.

Add:

```python
async def test_submit_at_limit_returns_409() -> None:
    candidate = _candidate(1, "Nhi Tran", "token-a")
    full = Answer(
        id=10,
        candidate_id=1,
        question_id=1,
        answer_type="text",
        text="old",
        audio_key=None,
        content_hash="old",
        version=3,
        external_ref=None,
        submitted_at=SUBMITTED_AT,
    )
    app = _app(
        FakeCandidatesService([candidate]),
        FakeAnswersService({1, 2}, answers=[full]),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
    )

    async with AsyncClient(transport=_transport(app), base_url="http://test") as client:
        response = await client.post(
            "/candidate/interview/answers/1",
            headers={"X-Candidate-Token": "token-a"},
            json={"answer_type": "text", "text": "new"},
        )

    assert response.status_code == 409
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Conflict"
    assert body["status"] == 409


async def test_interview_reports_attempts_remaining_and_max() -> None:
    candidate = _candidate(1, "Nhi Tran", "token-a")
    answer = _answer(10, 1, 1)
    app = _app(
        FakeCandidatesService([candidate]),
        FakeAnswersService({1, 2}, answers=[answer]),
        FakeCatalogService([QUESTION_1, QUESTION_2]),
    )

    async with AsyncClient(transport=_transport(app), base_url="http://test") as client:
        response = await client.get(
            "/candidate/interview",
            headers={"X-Candidate-Token": "token-a"},
        )

    body = response.json()
    assert body["max_submissions"] == 3
    assert [q["attempts_remaining"] for q in body["questions"]] == [2, 3]
```

- [ ] **Step 2: Run the router tests to verify they fail**

Run: `cd apps/backend && uv run pytest tests/test_candidate_router.py -q`
Expected: FAIL - responses are missing `attempts_remaining`/`max_submissions`, and the exhausted submit returns `500` instead of `409`.

- [ ] **Step 3: Implement the schemas, router fields, and error handler**

In `apps/backend/src/api/candidates/presentation/schemas.py`:
- Add `attempts_remaining: int` to `InterviewQuestion`.
- Add `max_submissions: int` to `InterviewResponse`.
- Add `attempts_remaining: int` to `SubmitResponse`.

In `apps/backend/src/api/candidates/presentation/errors.py`, import `AttemptsExhaustedError` and register:

```python
@app.exception_handler(AttemptsExhaustedError)
async def attempts_exhausted(_: Request, exc: AttemptsExhaustedError) -> JSONResponse:
    return _problem(409, "Conflict", str(exc))
```

In `apps/backend/src/api/candidates/presentation/candidate_router.py`:
- Add a helper:

```python
def _interview_question(question, answer, answers) -> InterviewQuestion:
    return InterviewQuestion(
        id=question.id,
        code=question.code,
        sort_order=question.sort_order,
        prompt=question.prompt,
        answer=_interview_answer(answer),
        attempts_remaining=answers.attempts_remaining(answer),
    )
```

- Build `questions` with that helper and add `max_submissions=answers.max_submissions` to `InterviewResponse`.
- Change `_submit_response` to take `answers` and pass `attempts_remaining=answers.attempts_remaining(result.answer)`; thread it through `_submit_or_unchanged` and the two submit handlers.

- [ ] **Step 4: Run the router tests to verify they pass**

Run: `cd apps/backend && uv run pytest tests/test_candidate_router.py -q`
Expected: PASS.

- [ ] **Step 5: Update the API contract spec**

In `docs/superpowers/specs/2026-10-18-api-contract-design.md`:
- Section 4 (locked decisions), resubmission row: add that changed resubmissions are capped by `MAX_ANSWER_SUBMISSIONS` (default 3) and excess changed submits return `409`.
- Section 6.4 (`answers`): note `version` doubles as the submission counter.
- Section 7.2: add `attempts_remaining` and `max_submissions` to the example bodies and add the `409` case.
- Section 11 (config): add `MAX_ANSWER_SUBMISSIONS` to the env list.
- Section 12 (traceability): add a row mapping the submission cap to `version` plus the atomic upsert guard.

- [ ] **Step 6: Run the full backend suite and static checks**

Run: `cd apps/backend && uv run pytest -q && uv run ruff check . && uv run mypy libs src`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add apps/backend/src/api/candidates/presentation/schemas.py \
  apps/backend/src/api/candidates/presentation/candidate_router.py \
  apps/backend/src/api/candidates/presentation/errors.py \
  apps/backend/tests/test_candidate_router.py \
  docs/superpowers/specs/2026-10-18-api-contract-design.md
git commit -m "feat(api): expose answer attempts remaining and 409 on exhaustion"
```

---

### Task 3: Candidate web attempts display

**Files:**
- Modify: `apps/candidate-web/lib/types.ts`
- Modify: `apps/candidate-web/components/interview/question-card.tsx`
- Modify: `apps/candidate-web/components/interview/answer-input.tsx`
- Test: `apps/candidate-web/tests/components/answer-input.test.tsx`
- Test: `apps/candidate-web/tests/components/interview-flow.test.tsx`
- Modify: `apps/candidate-web/e2e/interview.mocked.spec.ts`

**Interfaces:**
- Consumes: `Question.attempts_remaining`, `InterviewResponse.max_submissions`.
- Produces: `AnswerInput` prop `attemptsRemaining: number`.

- [ ] **Step 1: Update the shared types and existing test fixtures**

In `apps/candidate-web/lib/types.ts`:
- Add `attempts_remaining: number` to `Question`.
- Add `max_submissions: number` to `InterviewResponse`.
- Add `attempts_remaining: number` to `SubmitResponse`.

In `apps/candidate-web/tests/components/answer-input.test.tsx`, add `attemptsRemaining={3}` to every existing `render(<AnswerInput ... />)` call.

In `apps/candidate-web/tests/components/interview-flow.test.tsx`:
- Add `attempts_remaining: 3` to each question in `buildQuestions`.
- Add `max_submissions: 3` to `interview`.
- Add `attempts_remaining: 2` to the `received` fixture.

In `apps/candidate-web/e2e/interview.mocked.spec.ts`, add `attempts_remaining: 3` to each question in `interview()` and `max_submissions: 3` to the returned object; add `attempts_remaining: 2` to the submit `json` body.

- [ ] **Step 2: Add the failing component tests**

Append to `apps/candidate-web/tests/components/answer-input.test.tsx`:

```tsx
it("shows the number of attempts remaining", () => {
  render(
    <AnswerInput
      questionId={1}
      initialAnswer={null}
      attemptsRemaining={2}
      submitting={false}
      onSubmitText={vi.fn()}
      onSubmitAudio={vi.fn()}
    />,
  );
  expect(screen.getByText("2 attempts remaining")).toBeInTheDocument();
});

it("uses singular wording for one remaining attempt", () => {
  render(
    <AnswerInput
      questionId={1}
      initialAnswer={null}
      attemptsRemaining={1}
      submitting={false}
      onSubmitText={vi.fn()}
      onSubmitAudio={vi.fn()}
    />,
  );
  expect(screen.getByText("1 attempt remaining")).toBeInTheDocument();
});

it("disables submit when no attempts remain", async () => {
  const user = userEvent.setup();
  render(
    <AnswerInput
      questionId={1}
      initialAnswer={null}
      attemptsRemaining={0}
      submitting={false}
      onSubmitText={vi.fn()}
      onSubmitAudio={vi.fn()}
    />,
  );
  await user.type(screen.getByLabelText("Your answer"), "my answer");
  expect(screen.getByText("No attempts remaining")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Submit answer" })).toBeDisabled();
});
```

- [ ] **Step 3: Run the frontend tests to verify they fail**

Run: `cd apps/candidate-web && npm test -- answer-input`
Expected: FAIL - `AnswerInput` does not accept `attemptsRemaining` and the text is absent.

- [ ] **Step 4: Implement the display and disabled state**

In `apps/candidate-web/components/interview/answer-input.tsx`:
- Add `attemptsRemaining: number` to `AnswerInputProps` and destructure it.
- Change `canSubmit` to require `attemptsRemaining > 0`.
- Render, above the `Button`:

```tsx
<p className="text-xs text-zinc-500">
  {attemptsRemaining === 0
    ? "No attempts remaining"
    : `${attemptsRemaining} attempt${attemptsRemaining === 1 ? "" : "s"} remaining`}
</p>
```

In `apps/candidate-web/components/interview/question-card.tsx`, pass `attemptsRemaining={question.attempts_remaining}` to `AnswerInput`.

- [ ] **Step 5: Run the frontend tests, typecheck, and lint**

Run: `cd apps/candidate-web && npm test && npm run typecheck && npm run lint`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add apps/candidate-web/lib/types.ts \
  apps/candidate-web/components/interview/question-card.tsx \
  apps/candidate-web/components/interview/answer-input.tsx \
  apps/candidate-web/tests/components/answer-input.test.tsx \
  apps/candidate-web/tests/components/interview-flow.test.tsx \
  apps/candidate-web/e2e/interview.mocked.spec.ts
git commit -m "feat(candidate-web): show remaining answer attempts"
```

---

### Task 4: Whole-branch verification

**Files:** none (verification only; fix any failures inline).

- [ ] **Step 1: Run the backend suite and static checks**

Run: `cd apps/backend && uv run pytest -q && uv run ruff check . && uv run mypy libs src`
Expected: all pass.

- [ ] **Step 2: Run the candidate web suite and static checks**

Run: `cd apps/candidate-web && npm test && npm run typecheck && npm run lint`
Expected: all pass.

- [ ] **Step 3: Confirm candidate isolation still holds**

Run: `cd apps/backend && uv run pytest tests/test_candidate_router.py -q`
Expected: PASS, including `test_interview_returns_questions_without_grades`, which asserts no `grading_guide`/score keys leak.

- [ ] **Step 4: Commit any verification fixes**

```bash
git add -A
git commit -m "chore: finalize answer submission limit"
```

Only commit if a verification step required a fix; otherwise skip this step.
