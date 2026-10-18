# Talotrace Interview Scoring - API Contract Design

**Date:** 2026-10-18
**Status:** Accepted
**Repo:** private monorepo (to be initialized)
**Frontend:** Next.js 16 (App Router), two independently deployed apps
**Backend:** Python 3.14 + FastAPI, single monolith modeled on `apps/virtual-facility`
**Database:** PostgreSQL 18
**LLM:** DeepSeek (adapter-swappable)

## 1. Goal

Define the JSON API contract shared by two frontend apps (candidate area, HR area) and one FastAPI backend.
This contract is the single source of truth for the three implementation specs that follow:

1. Frontend - candidate area
2. Frontend - HR area
3. Backend service

The product: an internal interview-scoring app where candidates answer six questions via an unguessable personal link, an LLM suggests a 1-4 score against each question's grading guide, and HR - the decision-maker - reviews, sees the reasoning, and can override with a reason.

## 2. Scope

### 2.1 Phase 1 (in scope)

- Candidate area: open interview from a personal link, answer six questions one at a time (text or audio upload), receive immediate "answer arrived" confirmation, reload and resume at the same question.
- HR area: JWT sign-in, view candidates for a role with each answer and its suggested score and reasoning, override a score with a required reason, view scoring-job status, retry failed jobs, import the data pack.
- Backend: JSON API that owns data, business rules, and permissions; background scoring worker pool using a real LLM; PostgreSQL as both system of record and scoring queue.
- Audio answers are accepted, stored, and visible to HR. Transcription/scoring of audio is deferred to phase 2.

### 2.2 Phase 2 (out of scope, optional extras)

- Score-agreement report vs `hr_reference_scores.csv`.
- Transcribe and score the five audio-only answers.
- A dedicated "needs a person" list with reasons.
- Candidate list ordered to help HR decide who to read first.
- Consent screen and microphone check in the candidate area.
- Candidate-facing error messages and retry.
- Deployed demo.

## 3. System Context

```text
                       +----------------------+
  candidate link  ---> | apps/candidate-web   |--\
  (unauthenticated)    | Next.js 16           |   \  X-Candidate-Token
                       +----------------------+    \      |
                                                   +-----v-----------+
  HR sign-in (JWT) --> +----------------------+    | apps/api        |
                       | apps/hr-web          |--->| FastAPI monolith|
                       | Next.js 16           |    | Python 3.14     |
                       +----------------------+    | PostgreSQL 18   |
                                                   | scoring workers |
                                                   +-----|-----------+
                                                         |  FOR UPDATE SKIP LOCKED
                                                   scoring_jobs table (queue)
```

- Both frontends are deployed independently and consume the same API.
- The API is a single FastAPI app. It keeps `libs/database` and `libs/iam` from the template and drops `messaging`, `outbox`, `inbox`, NATS, RabbitMQ, and `workflows-service`.
- Scoring runs as an in-process background worker pool inside the API process. PostgreSQL acts as the queue via `SELECT ... FOR UPDATE SKIP LOCKED` polling of the `scoring_jobs` table.

### 3.1 Monorepo layout

```text
talotrace-assessment/
├── apps/
│   ├── candidate-web/        # Next.js 16 app router - candidate area
│   ├── hr-web/               # Next.js 16 app router - HR area
│   └── api/                  # FastAPI monolith (virtual-facility shaped)
├── libs/
│   ├── database/             # from template
│   ├── iam/                  # from template
│   └── contracts/            # shared Pydantic/TS contract types (optional)
├── docs/
│   └── superpowers/
│       └── specs/            # this spec + the 3 downstream specs
└── docker-compose.yml        # postgres + api (+ dev servers)
```

## 4. Locked Architectural Decisions

| Topic | Decision |
|---|---|
| API style | JSON over HTTP, resource-oriented REST. No version prefix in phase 1 (`/auth`, `/hr`, `/candidate`). |
| Error format | RFC 7807 Problem Details (`{"type","title","status","detail"}`), matching the template. |
| HR auth | Bearer JWT via template `libs/iam`, role `hr`. One seeded HR account. |
| Candidate auth | No credentials. Opaque unguessable token (`secrets.token_urlsafe(32)`) passed as `X-Candidate-Token` header, scoping every response to that candidate. |
| ID scheme | Integer primary keys for all entities; `session_token` is the only secret (not a primary key). |
| Scoring queue | `scoring_jobs` table in PostgreSQL, drained by an in-process `asyncio` worker pool with `FOR UPDATE SKIP LOCKED`. |
| LLM integration | `ScoringLlmPort` protocol + `DeepSeekLlm` adapter; config via env. Output strictly validated to `{score: int 1-4, reasoning: str}`. |
| Audio storage | `FileStorage` abstraction, local filesystem volume in phase 1; object-storage adapter later. |
| Resubmission | One active `Answer` row per (candidate, question), with a `content_hash`. Byte-identical resubmission is an idempotent no-op; changed content increments `version` and resets the `ScoringJob` to `queued`. Exactly one score ever exists per candidate x question. |
| Candidate isolation | Candidate endpoints have no cross-candidate lookups; grades and grading guides are never serialized to the candidate area. |

## 5. Authentication & Authorization

### 5.1 HR (JWT, role `hr`)

Reuses the template IAM (`require_auth(AuthType.JWT)`, `require_roles(Role.HR)`).

- Seeded HR account (email + bcrypt password) is created at startup/migration.
- `POST /auth/sign-in` returns an access token (`role=hr`, TTL 1h) and a refresh token (single-use rotation, as in the template).
- All `/hr/*` endpoints require a valid JWT with `role=hr`. Any other role (or no token) returns `401`/`403`.

IAM role enum is extended with `hr`. There is no login "candidate" role - candidates authenticate via session token, not the IAM.

### 5.2 Candidate (session token)

- HR creates a candidate; the backend generates `session_token = secrets.token_urlsafe(32)` (unguessable, unique, indexed).
- The interview link is `{CANDIDATE_WEB_ORIGIN}/interview/{session_token}`. `CANDIDATE_WEB_ORIGIN` is an env var so the API can build the link without hardcoding the FE origin.
- The candidate FE extracts the token from its route and sends it on every request as `X-Candidate-Token`.
- The API resolves the token to a `Candidate`, rejects unknown/expired tokens with `401`, and scopes every candidate endpoint to that candidate only.

The token is kept in the URL for the candidate (so the link is shareable/pasteable) but travels to the API in a header, keeping it out of API server access logs.

## 6. Data Model

Enums:

- `answer_type`: `"text"` | `"audio"`
- `scoring_status`: `"queued"` | `"scored"` | `"failed"` | `"needs_a_person"`
- `iam_role`: `"hr"` (plus template's `"admin"`/`"regular"`)

### 6.1 `roles`

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| name | str unique | one of: Backend Engineer, Sales Executive, Customer Success Associate, Marketing Coordinator, Finance Analyst |
| created_at | timestamptz | |

### 6.2 `questions`

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| code | str unique | `"Q1"` .. `"Q6"` |
| sort_order | int unique | 1..6 |
| prompt | text | the question text |
| grading_guide | jsonb | map `{"1": ..., "2": ..., "3": ..., "4": ...}` |

### 6.3 `candidates`

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| name | str nullable | |
| email | str unique | required; HR keys candidate creation off it |
| role_id | int FK -> roles.id | |
| session_token | str unique indexed | unguessable secret |
| external_ref | str nullable indexed | data-pack `candidate_id` (e.g. `"C2041"`) for phase-2 matching |
| created_at | timestamptz | |

### 6.4 `answers`

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| candidate_id | int FK -> candidates.id | |
| question_id | int FK -> questions.id | |
| answer_type | str | `text` \| `audio` |
| text | text nullable | transcript for text answers |
| audio_key | str nullable | `FileStorage` key for audio answers |
| content_hash | str | SHA-256 hex of submitted content (UTF-8 text bytes, or audio file bytes) |
| version | int | starts 1; increments on resubmit |
| external_ref | str nullable indexed | data-pack `answer_id` (e.g. `"A001"`) |
| submitted_at | timestamptz | |

- Unique constraint on `(candidate_id, question_id)`. There is exactly one active row per candidate x question.

**Resubmission semantics.** Each submit computes `content_hash = sha256(submitted bytes)`. If the active answer for that question already has the same `content_hash`, the submit is an idempotent no-op: no new version, no scoring-job reset, no re-score. Otherwise the answer is upserted (new row, or `version` incremented when content changes), `content_hash` is stored, and the `scoring_job` is reset to `queued`. This makes a double-click or byte-identical resubmission produce exactly one score, and the `(candidate_id, question_id)` unique key makes racing duplicate submits converge to one row.

### 6.5 `scoring_jobs`

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| answer_id | int FK -> answers.id, unique | 1:1 with answer |
| status | str | `queued` \| `scored` \| `failed` \| `needs_a_person` |
| suggested_score | int nullable | 1..4 (LLM) |
| suggested_reasoning | text nullable | LLM reasoning |
| final_score | int nullable | 1..4 (HR decision) |
| override_reason | text nullable | required when HR sets final_score |
| overridden_by | int nullable | FK -> users.id |
| attempt_count | int | default 0 |
| last_error | text nullable | for `failed` |
| claimed_at | timestamptz nullable | worker lease |
| created_at | timestamptz | |
| updated_at | timestamptz | |
| scored_at | timestamptz nullable | |

`final_score` resolution: when `status=scored` and no override, `final_score = suggested_score`; HR can set `final_score` + `override_reason` (override), or set `final_score` + reason for `needs_a_person` answers (manual scoring). `queued`/`failed` have no final score.

### 6.6 `users` (HR accounts)

Reuses the template `users` table: `id`, `email` (unique), `password_hash`, `role` (`"hr"`). `refresh_tokens` reuses the template table for JWT rotation.

### Relationships

```text
roles 1 ---- N candidates 1 ---- N answers 1 ---- 1 scoring_jobs
questions 1 ---- N answers
users 1 ---- N scoring_jobs (overridden_by)
```

## 7. API Endpoints

Conventions:

- Requests/responses are JSON unless noted.
- Errors are RFC 7807 problem details (see section 9).
- Auth columns: `-` = public, `session` = `X-Candidate-Token` header, `jwt(hr)` = Bearer JWT with role `hr`.

### 7.1 Auth (HR)

| Method + path | Auth | Purpose |
|---|---|---|
| `POST /auth/sign-in` | - | HR login |
| `POST /auth/refresh-tokens` | - | rotate refresh token |
| `POST /auth/sign-out` | - | revoke refresh token |

`POST /auth/sign-in`

Request:
```json
{ "email": "hr@talotrace.ai", "password": "..." }
```

Response `200`:
```json
{
  "user": { "id": 1, "email": "hr@talotrace.ai", "role": "hr" },
  "access_token": "<jwt>",
  "refresh_token": "<jwt>"
}
```

`401` on invalid credentials. `POST /auth/refresh-tokens` takes `{ "refresh_token": "..." }` and returns the same shape. `POST /auth/sign-out` takes `{ "refresh_token": "..." }` and returns `204`.

### 7.2 Candidate (session token)

| Method + path | Auth | Purpose |
|---|---|---|
| `GET /candidate/interview` | session | interview context, questions, own progress |
| `POST /candidate/interview/answers/{question_id}` | session | submit a text answer |
| `POST /candidate/interview/answers/{question_id}/audio` | session | upload an audio answer |

`GET /candidate/interview` - Response `200`:

```json
{
  "candidate": { "id": 1, "name": "Nhi Tran", "role": "Backend Engineer" },
  "questions": [
    {
      "id": 1,
      "code": "Q1",
      "sort_order": 1,
      "prompt": "Tell us about a piece of work you are proud of...",
      "answer": {
        "answer_type": "text",
        "text": "...",
        "version": 1,
        "submitted_at": "2026-09-14T10:15:00Z"
      }
    }
  ],
  "progress": { "answered": 1, "total": 6 }
}
```

- `answer` is `null` when the question is unanswered.
- The grading guide and any score are never included. The candidate cannot see grades, other candidates, or HR data.

`POST /candidate/interview/answers/{question_id}` - Request:

```json
{ "answer_type": "text", "text": "..." }
```

Response `201` (or `200` when unchanged):

```json
{
  "status": "received",
  "unchanged": false,
  "answer": { "answer_type": "text", "version": 2, "submitted_at": "..." }
}
```

- `201` + `unchanged: false` when the answer is new or its content changed (a new `version` was written and the job re-queued).
- `200` + `unchanged: true` when the submitted content hash matches the existing answer (idempotent no-op; the existing score/job is left untouched).

`422` if `text` is empty/whitespace or `answer_type` is not `text`. `404` if `question_id` is not one of the six.

`POST /candidate/interview/answers/{question_id}/audio` - Request: `multipart/form-data` with field `file` (audio). Response `201`/`200` (same shape, `answer_type: "audio"`, hash over the file bytes). `422` on missing/invalid file, `404` unknown question.

Resubmission semantics: submitting again for the same question upserts the single active answer. Identical content (same `content_hash`) is a no-op; changed content increments `version`, replaces content, and resets the scoring job to `queued`. The response reports `unchanged` and the current `version`.

### 7.3 HR (JWT `hr`)

| Method + path | Auth | Purpose |
|---|---|---|
| `GET /hr/roles` | jwt(hr) | list roles |
| `GET /hr/roles/{role_id}/candidates` | jwt(hr) | candidates for a role with answers |
| `GET /hr/candidates/{candidate_id}` | jwt(hr) | candidate detail + interview link |
| `POST /hr/candidates` | jwt(hr) | create candidate, generate link |
| `GET /hr/answers/{answer_id}` | jwt(hr) | answer + scoring detail |
| `GET /hr/answers/{answer_id}/audio` | jwt(hr) | stream audio answer |
| `PATCH /hr/answers/{answer_id}/score` | jwt(hr) | override/ set final score |
| `GET /hr/scoring-jobs` | jwt(hr) | list jobs, filter by status |
| `POST /hr/scoring-jobs/{job_id}/retry` | jwt(hr) | retry a failed job |
| `POST /hr/import` | jwt(hr) | import data-pack zip |

`GET /hr/roles` - Response `200`:

```json
[
  { "id": 1, "name": "Backend Engineer", "candidate_count": 4 },
  { "id": 2, "name": "Sales Executive", "candidate_count": 3 }
]
```

`GET /hr/roles/{role_id}/candidates` - Response `200`:

```json
[
  {
    "id": 12,
    "name": "Nhi Tran",
    "email": "nhi.tran.van26@example.com",
    "answer_progress": { "answered": 2, "total": 6 },
    "answers": [
      {
        "id": 31,
        "question_id": 1,
        "question_code": "Q1",
        "answer_type": "text",
        "version": 1,
        "scoring": {
          "status": "scored",
          "suggested_score": 3,
          "final_score": 3,
          "override_reason": null
        }
      }
    ]
  }
]
```

`GET /hr/candidates/{candidate_id}` - Response `200` adds `role_id`, `session_token`, `interview_link`, and full scoring detail per answer (`suggested_reasoning`, `override_reason`, `overridden_by`, `last_error`, `attempt_count`, `scored_at`).

`POST /hr/candidates` - Request:

```json
{ "name": "Nhi Tran", "email": "nhi.tran.van26@example.com", "role_id": 1 }
```

Response `201`:

```json
{
  "id": 12,
  "name": "Nhi Tran",
  "email": "nhi.tran.van26@example.com",
  "role_id": 1,
  "session_token": "<token>",
  "interview_link": "https://candidate.example.com/interview/<token>"
}
```

`409` if `email` already exists.

`GET /hr/answers/{answer_id}` - Response `200`:

```json
{
  "id": 31,
  "candidate_id": 12,
  "question_id": 1,
  "question_code": "Q1",
  "question_prompt": "...",
  "grading_guide": { "1": "...", "2": "...", "3": "...", "4": "..." },
  "answer_type": "text",
  "text": "...",
  "version": 1,
  "submitted_at": "...",
  "scoring": {
    "status": "scored",
    "suggested_score": 3,
    "suggested_reasoning": "...",
    "final_score": 3,
    "override_reason": null,
    "overridden_by": null,
    "attempt_count": 1,
    "last_error": null,
    "scored_at": "..."
  }
}
```

`GET /hr/answers/{answer_id}/audio` - Response `200` with audio content type (e.g. `audio/mp4`). `404` if the answer is not audio or the file is missing.

`PATCH /hr/answers/{answer_id}/score` - Request:

```json
{ "final_score": 4, "override_reason": "Candidate clearly measured impact and reflected on what they would change." }
```

Response `200` (updated answer shape). `override_reason` is required (non-empty). `final_score` must be an integer 1..4 (`422` otherwise). Allowed when the job status is `scored` or `needs_a_person` (`409` otherwise). `404` unknown answer.

`GET /hr/scoring-jobs` - Query `status` (optional, one of the four statuses). Response `200`:

```json
[
  {
    "id": 51,
    "answer_id": 31,
    "candidate_id": 12,
    "candidate_name": "Nhi Tran",
    "question_code": "Q1",
    "status": "failed",
    "attempt_count": 3,
    "last_error": "LLM returned invalid output",
    "created_at": "..."
  }
]
```

`POST /hr/scoring-jobs/{job_id}/retry` - Resets a `failed` job to `queued` (increments `attempt_count`, clears `last_error`). Response `200` (job shape). `409` if status is not `failed`. `404` unknown job.

`POST /hr/import` - Request: `multipart/form-data` field `file` (the data-pack zip). See section 8. Response `200`:

```json
{
  "roles_created": 5,
  "questions_created": 6,
  "candidates_created": 18,
  "answers_imported": 35,
  "scoring_jobs_queued": 30,
  "audio_answers_needing_person": 5
}
```

`400` on unreadable zip or unexpected layout; `413` on oversized file.

### 7.4 Health

`GET /health` - Response `200`: `{ "status": "ok" }`.

## 8. Data Pack Import

`POST /hr/import` accepts the `business-systems-pack.zip`. Behavior:

1. Parse `questions.md` -> upsert the six `questions` (prompt + grading guide from the 1-4 bullets).
2. Ensure the five `roles` from the `Open roles` list exist.
3. Parse `pipeline_log.csv` -> build `candidate_id -> (name, email, role)` for enrichment.
4. For each `answers/*.json`:
   - Resolve role by name.
   - Find-or-create the `candidate` by `external_ref = candidate_id`; set `name`/`email` from `pipeline_log.csv` when present, otherwise fall back to a placeholder derived from `candidate_id`. Generate a `session_token`.
   - Create the `answer` (`external_ref = answer_id`). If `transcript` is present: `answer_type=text`, enqueue `scoring_job(status=queued)`. If `audio_file` is present and `transcript` is null: `answer_type=audio`, store the `.m4a` via `FileStorage`, set `scoring_job(status=needs_a_person)`.
5. Return the summary above.

Import is idempotent on `external_ref`: re-importing the same pack does not duplicate questions, candidates, or answers.

## 9. Errors

All error responses use RFC 7807 problem details, matching the template:

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "answer not found"
}
```

| Code | Meaning |
|---|---|
| 400 | malformed request / unreadable import |
| 401 | missing or invalid credentials (HR JWT or candidate token) |
| 403 | authenticated but not allowed (non-HR role on `/hr/*`) |
| 404 | resource not found |
| 409 | conflict (duplicate email, invalid state transition) |
| 413 | upload too large |
| 422 | validation error |

## 10. Scoring Pipeline

1. **Enqueue**: on answer submit (or import of a text answer), the `scoring_job` is created/reset with `status=queued`.
2. **Claim**: a worker in the pool runs `SELECT ... FROM scoring_jobs WHERE status='queued' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1`, sets `claimed_at`, and marks it in-flight.
3. **Score**: the worker builds a prompt from the question `prompt` + `grading_guide` (system) and the candidate `text` (user, delimited as untrusted data), calls the `ScoringLlmPort` (DeepSeek adapter).
4. **Validate**: the adapter returns JSON that is strictly validated to `{score: int, reasoning: str}` with `1 <= score <= 4`. Anything else is rejected.
5. **Store**: on success, set `suggested_score`, `suggested_reasoning`, `final_score=suggested_score`, `status=scored`, `scored_at=now`.
6. **Failure**: on LLM/validation error, increment `attempt_count`. Below the max attempts, re-queue (backoff); at the max, set `status=failed` and `last_error`. A failed job is never shown as a score.
7. **Audio (phase 1)**: audio-only answers are set to `needs_a_person` at import/submit time and are not sent to the LLM.

Status transitions: `queued -> scored` or `queued -> failed`; `failed -> queued` (retry). Audio-only answers (phase 1) are created directly with `status=needs_a_person` and never enter the queue. `scored`/`needs_a_person` answers can receive an HR override that sets `final_score` + `override_reason` without changing `status`.

Prompt-injection safety: the system prompt instructs the model that the candidate text is untrusted data and must never be treated as instructions; the output is schema-validated so only a `score` and `reasoning` can be stored. An answer that instructs the scorer cannot change its own score.

## 11. Cross-Cutting Concerns

- **CORS**: allow-list via `CORS_ORIGINS` env (the two FE origins).
- **Config (env)**: `DATABASE_URL`, `JWT_SECRET`, `JWT_ALGORITHM`, `CANDIDATE_WEB_ORIGIN`, `CORS_ORIGINS`, `SCORING_WORKERS` (pool size), `SCORING_MAX_ATTEMPTS`, `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `AUDIO_STORAGE_DIR`.
- **LLM adapter**: `ScoringLlmPort` protocol with `DeepSeekLlm` implementation; alternate providers swap in without changing the worker. The test suite may substitute a fake.
- **Audio storage**: `FileStorage` protocol with a local-filesystem adapter in phase 1.
- **Background worker**: `asyncio` pool of `SCORING_WORKERS` tasks started in the FastAPI lifespan, stopped cleanly on shutdown (mirrors the template's `OutboxProcessor` lifecycle).

## 12. "What Must Be True" Traceability

| Requirement | Design guarantee |
|---|---|
| Same answer twice does not create two scores | Unique `(candidate_id, question_id)` on `answers`; resubmit upserts the single row and resets the single `scoring_job`; byte-identical content (`content_hash`) is an idempotent no-op. |
| HR sees which submission counts | One active answer per question; `version` + `submitted_at` expose resubmission history. |
| Candidate cannot see grades/other candidates/HR pages via API | Candidate endpoints scope by token and never serialize scores or grading guides; `/hr/*` requires JWT `hr`; no cross-candidate lookups exist. |
| Failed job visible with retry, never shown as low score | `status=failed` + `last_error`; `POST /hr/scoring-jobs/{id}/retry`; failed jobs have no `final_score`. |
| Prompt-injection cannot change the score | Untrusted-text delimiters + strict output schema validation. |
| Typed data-pack answers can be loaded and scored | `POST /hr/import` enqueues text answers for scoring. |
| Audio answer stored and visible to HR | `answer_type=audio` + `audio_key`; `GET /hr/answers/{id}/audio` streams it. |
| App runs from README on a clean machine | `docker-compose.yml` boots Postgres + API; README documents setup/run/test (own spec section, delivered in repo). |

## 13. Testing & Verification

- Backend: HTTP tests per endpoint covering auth (401/403), candidate isolation, resubmission idempotency (changed content re-queues; byte-identical content is a no-op), score-override reason requirement, failed-job retry, and import idempotency. Scoring worker tested with a fake `ScoringLlmPort` and with schema-validation cases (invalid score, missing field, injected instructions).
- Frontend: candidate flow (open link, answer, resume, resubmit, confirmation) and HR flow (sign-in, role -> candidate -> override, retry) against the real API.
- End-to-end: import the data pack, observe text answers reach `scored`, audio answers are `needs_a_person`, and a duplicate submission yields a single score.
