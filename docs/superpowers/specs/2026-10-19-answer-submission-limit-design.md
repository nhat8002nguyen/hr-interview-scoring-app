# Talotrace Interview Scoring - Answer Submission Limit Design

**Date:** 2026-10-19
**Status:** Accepted
**Repo:** private monorepo
**Related:** `2026-10-18-api-contract-design.md` (single source of truth this feature amends)

## 1. Goal

Prevent a candidate from spamming a question with repeated resubmissions.

Each candidate may submit at most `MAX_ANSWER_SUBMISSIONS` distinct answers per question (default `3`).

The candidate area shows how many attempts remain and allows resubmission until that count reaches zero.

## 2. Scope

In scope:

- A global per-question submission limit, default `3`, configurable via environment.
- Backend enforcement: a submission whose content changed is rejected with `409` once the limit is reached.
- Candidate-area API surfaces `attempts_remaining` (per question) and `max_submissions` (whole interview).
- Candidate frontend displays remaining attempts and disables the submit control at zero.

Out of scope:

- Per-question or per-role limits (a single global value for now).
- Any HR-area UI for viewing submission counts.
- Counting byte-identical resubmissions against the limit (see 4.2).

## 3. Locked Decisions

| Topic | Decision |
|---|---|
| Limit location | Single global setting `MAX_ANSWER_SUBMISSIONS`, default `3`. |
| What counts as an attempt | Only a *changed* answer consumes an attempt. Byte-identical resubmission remains an idempotent no-op. |
| Counter storage | Reuse the existing `answers.version` column. No new table, no new column, no migration. |
| Exhaustion response | `409 Conflict` RFC 7807 problem detail. |
| Exposed fields | `attempts_remaining` on each interview question and on the submit response; `max_submissions` once at the interview-response top level. |

## 4. Design

### 4.1 Why `version`, not a new field or model

The candidate considered a new `candidate_questions` join model or a new column.

`answers` already carries a unique `(candidate_id, question_id)` constraint and a `version` column that:

- starts at `1` on the first submission,
- increments by exactly one on every *changed* resubmission,
- is left untouched by byte-identical resubmissions (the existing idempotent no-op).

Because "changed content only" counts as an attempt, `version` is exactly the number of submissions used.
Reusing it avoids a redundant table or column and removes any risk of two counters drifting apart.

### 4.2 Attempt semantics

`submissions_used = version` (0 while unanswered).
`attempts_remaining = max(0, max_submissions - submissions_used)`.

Consequences:

- A candidate who submits one answer then resubmits twice more has used 3 attempts and may not submit again.
- A candidate who accidentally double-submits the same text does not lose an attempt, because the resubmission is a no-op.
- If the configured limit is later lowered below an existing answer's `version`, `attempts_remaining` clamps to `0` and further submissions are rejected.

### 4.3 Config

Add to `api/config.py`:

```python
max_answer_submissions: int = 3
```

`AnswersService` receives it as a constructor argument `max_submissions`, wired in `main.py` from `configured.max_answer_submissions`.
It is exposed as a public `max_submissions` attribute for the presentation layer.

### 4.4 Enforcement

**Repository.** `build_upsert_statement(answer, max_submissions)` adds a second condition to the `ON CONFLICT ... DO UPDATE` `WHERE`:

```python
and_(
    AnswerModel.content_hash != statement.excluded.content_hash,
    AnswerModel.version < max_submissions,
)
```

This makes the limit atomic: under concurrent submits, `version` can never exceed the maximum even when two requests race at the boundary.

**Service.** `AnswersService._submit` runs the upsert, then reads the resulting active row and disambiguates three outcomes:

- `content_hash` unchanged -> return `unchanged=True` (no scoring-job reset).
- content changed and written -> return `unchanged=False`, reset the scoring job.
- content changed but not written -> raise `AttemptsExhaustedError` (the write was blocked because `version` hit the maximum).

`submit_audio` computes the hash and checks the limit *before* saving the file, so a rejected upload cannot overwrite the already-accepted recording.

A new `AttemptsExhaustedError(question_id, max_submissions)` is added to `candidates/domain/exceptions.py` and mapped to `409` in `candidates/presentation/errors.py`.

### 4.5 API contract (candidate area)

`GET /candidate/interview` - response adds `max_submissions` at the top level and `attempts_remaining` to each question:

```json
{
  "candidate": { "id": 1, "name": "Nhi Tran", "role": "Backend Engineer" },
  "questions": [
    {
      "id": 1,
      "code": "Q1",
      "sort_order": 1,
      "prompt": "Tell us about a piece of work you are proud of...",
      "answer": { "answer_type": "text", "text": "...", "version": 1, "submitted_at": "..." },
      "attempts_remaining": 2
    }
  ],
  "progress": { "answered": 1, "total": 6 },
  "max_submissions": 3
}
```

`POST /candidate/interview/answers/{question_id}` (text and audio) - response adds `attempts_remaining`:

```json
{
  "status": "received",
  "unchanged": false,
  "answer": { "answer_type": "text", "version": 2, "submitted_at": "..." },
  "attempts_remaining": 1
}
```

At the limit, a changed submission returns `409`:

```json
{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "Maximum submissions (3) reached for question 1"
}
```

The grading guide and any score remain absent from the candidate area.

### 4.6 Frontend (candidate-web)

- `lib/types.ts`: add `attempts_remaining` to `Question`, `max_submissions` to `InterviewResponse`, and `attempts_remaining` to `SubmitResponse`.
- `question-card.tsx` / `answer-input.tsx`: show "N attempts remaining" and disable the submit button when the count reaches `0`, with a "No attempts remaining" message.
- `interview-flow.tsx` already refetches the interview on "Continue", so the latest remaining count is present when a candidate revisits a question.

## 5. Testing

Backend:

- Service: three changed submissions succeed; the fourth changed submission raises `AttemptsExhaustedError`.
- Service: byte-identical resubmission never consumes an attempt.
- Service: `attempts_remaining` math, including the clamp at zero.
- Router: interview response includes `attempts_remaining` per question and `max_submissions` at the top level.
- Router: submit response includes `attempts_remaining`.
- Router: a changed submission at the limit returns `409`.

Frontend:

- Component tests for the remaining-attempts display and the disabled-at-zero state.

## 6. Traceability

| Requirement | Design guarantee |
|---|---|
| Candidate cannot spam a question | `version` is capped at `max_submissions` by the atomic upsert `WHERE version < max_submissions`. |
| Candidate sees attempts remaining | `attempts_remaining` on each interview question and on the submit response. |
| Candidate can resubmit until exhausted | Submissions are accepted while `version < max_submissions`. |
| Accidental identical resubmit does not penalize | Byte-identical content is still an idempotent no-op and does not consume an attempt. |
| No HR data leaks to candidates | No score or grading-guide fields are added to the candidate area. |
