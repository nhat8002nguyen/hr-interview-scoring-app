# Talotrace Interview Scoring - Backend Service Design

**Date:** 2026-10-18
**Status:** Accepted
**Source of truth:** `docs/superpowers/specs/2026-10-18-api-contract-design.md`
**Repo:** `talot-backend` (sibling git repo to `talot-candidate-web` and `talot-hr-web`)
**Runtime:** Python 3.14 + FastAPI
**Database:** PostgreSQL 18
**LLM:** DeepSeek (adapter-swappable)

## 1. Goal

Define the backend service that implements the API contract in `2026-10-18-api-contract-design.md`.
This spec covers structure, module boundaries, lifecycle, data model, and correctness details that the contract leaves open.
The contract remains the single source of truth for endpoints, request/response shapes, error codes, and business rules.
Where this spec and the contract disagree, the contract wins.

The backend is a single FastAPI monolith copied from the `virtual-facility` app in `initial-resources/fastapi-microservices`, keeping `libs/database` and `libs/iam` and dropping all messaging, outbox, inbox, NATS, RabbitMQ, and tracing parts.
Scoring runs as an in-process asyncio worker pool inside the API process, draining the `scoring_jobs` table via `SELECT ... FOR UPDATE SKIP LOCKED`.

## 2. Scope

In scope for this spec: the FastAPI application, its data model and migrations, HR authentication, candidate session-token isolation, answer submission and resubmission, the scoring worker and LLM adapter, audio storage, the data-pack importer, and the test plan.

Out of scope (phase 2, unchanged from the contract): audio transcription/scoring, score-agreement reporting, candidate ordering, consent/microphone checks, and the deployed demo.

## 3. Locked Architectural Decisions

| Topic | Decision |
|---|---|
| Template source | `initial-resources/fastapi-microservices/apps/virtual-facility` plus `libs/database` and `libs/iam` |
| Kept libraries | `database`, `iam` only |
| Dropped | `messaging`, `outbox`, `inbox`, `tracing`, NATS, RabbitMQ, `workflows-service`, `contracts` |
| Layout | `uv` workspace under `talot-backend/` with `libs/database`, `libs/iam`, and `apps/api` |
| App package | `api` (import path `api.main:app`, FastAPI title "talotrace-api") |
| API style | JSON over HTTP, resource-oriented REST, no version prefix in phase 1 |
| Error format | RFC 7807 Problem Details (`{"type","title","status","detail"}`) |
| HR auth | Bearer JWT via `libs/iam`, role `hr`, one seeded HR account |
| Candidate auth | Opaque `secrets.token_urlsafe(32)` token in `X-Candidate-Token` header |
| ID scheme | Integer primary keys; `session_token` is the only secret (not a primary key) |
| Module layering | Pragmatic Clean Architecture per feature module (`domain`, `application`, `infrastructure`, `presentation`) |
| Scoring queue | `scoring_jobs` table drained by an in-process `asyncio` pool with `FOR UPDATE SKIP LOCKED` |
| LLM integration | `ScoringLlmPort` protocol + `DeepSeekLlm` adapter |
| Audio storage | `FileStorage` protocol + local-filesystem adapter in phase 1 |
| Resubmission | One active `answers` row per (candidate, question), atomic upsert keyed on `content_hash` |

## 4. Package Layout

```text
talot-backend/
├── pyproject.toml          # uv workspace root; members: libs/database, libs/iam, apps/api
├── uv.lock
├── Dockerfile.dev
├── docker-compose.yml      # api-db (postgres:18) + api-migrate + api
├── README.md
├── libs/
│   ├── database/
│   │   ├── pyproject.toml
│   │   └── src/database/
│   │       ├── __init__.py   # Base, UnitOfWork, create_engine, create_session_factory
│   │       ├── base.py
│   │       ├── session.py
│   │       └── uow.py
│   └── iam/
│       ├── pyproject.toml
│       └── src/iam/
│           ├── __init__.py
│           ├── config.py
│           ├── domain/{entities,exceptions,ports}.py
│           ├── application/{jwt,hashing,api_key,policy}.py
│           └── presentation/{dependencies,errors}.py
└── apps/
    └── api/
        ├── pyproject.toml
        ├── alembic.ini
        ├── migrations/
        │   ├── env.py
        │   └── versions/
        ├── tests/
        └── src/api/
            ├── __init__.py
            ├── config.py
            ├── main.py
            ├── health/
            │   └── router.py
            ├── auth/
            ├── catalog/
            ├── candidates/
            ├── scoring/
            └── importing/
```

The workspace root `pyproject.toml` lists `libs/database`, `libs/iam`, and `apps/api` as members and drops the messaging, outbox, inbox, tracing, contracts, and workflows-service members.

## 5. Library Changes

### 5.1 `libs/database`

Copied verbatim from the template.
No changes.

### 5.2 `libs/iam`

Copied with one change: the `Role` enum gains `HR = "hr"`.

```python
class Role(StrEnum):
    ADMIN = "admin"
    REGULAR = "regular"
    HR = "hr"
```

Everything else is reused unchanged: `JwtService`, `BcryptHashingService`, `RefreshTokenStorageProtocol`, `require_auth(AuthType.JWT)`, `require_roles(Role.HR)`, `CurrentUserDep`, and `register_iam_exception_handlers`.
The `api_keys` parts of the template app are not copied; only the `users` and `refresh_tokens` tables are needed.
There is no `groups` table; `ActiveUserData.group_ids` is always empty.
HR sign-in responses use a lean `HrUserResponse {id, email, role}` with no `group_ids` field.

## 6. Module Decomposition

Five feature modules plus `health`, each following the template's four-layer structure.

| Module | Owns tables / entities | Endpoints | Depends on |
|---|---|---|---|
| `auth` | `users`, `refresh_tokens` | `POST /auth/sign-in`, `POST /auth/refresh-tokens`, `POST /auth/sign-out` | `iam` |
| `catalog` | `roles`, `questions` | `GET /hr/roles` | `candidates` (candidate counts) |
| `candidates` | `candidates`, `answers` | `GET /candidate/interview`; `POST /candidate/interview/answers/{id}` and `.../{id}/audio`; `GET /hr/roles/{id}/candidates`; `GET /hr/candidates/{id}`; `POST /hr/candidates`; `GET /hr/answers/{id}`; `GET /hr/answers/{id}/audio` | `catalog`, `scoring` (enqueue + read) |
| `scoring` | `scoring_jobs` | `PATCH /hr/answers/{id}/score`; `GET /hr/scoring-jobs`; `POST /hr/scoring-jobs/{id}/retry` | `catalog`, `candidates` (read), LLM |
| `importing` | (none) | `POST /hr/import` | `catalog`, `candidates`, `scoring` |
| `health` | - | `GET /health` | - |

### 6.1 Ownership rule

Each module owns the write path and repository for its own tables.
Cross-table read composition (for example the HR answer detail joining `answers`, `questions`, and `scoring_jobs`) is done with SQLAlchemy joins inside the module that serves the endpoint.
The only true cross-module operations are answer-submit enqueue (`candidates` calls `scoring.enqueue`) and the importer (`importing` composes `catalog`, `candidates`, and `scoring`).
These are wired as services on `app.state` to avoid module-level import cycles.

### 6.2 `auth`

- `domain/entities.py`: `User` (id, email, password_hash, role).
- `domain/repositories.py`: `UserRepository` protocol (add, get, get_by_email).
- `domain/exceptions.py`: `UserNotFoundError`.
- `infrastructure/models.py`: `UserModel` (`users`), `RefreshTokenModel` (`refresh_tokens`), copied from the template minus groups and api keys.
- `infrastructure/repository.py`: `SqlAlchemyUserRepository`, `TransactionalRefreshTokenStorage`.
- `application/service.py`: `AuthenticationService` with `sign_in`, `refresh`, `sign_out` only (no sign-up).
  Reuses `JwtService`, `BcryptHashingService`, and `RefreshTokenStorageProtocol`.
- `presentation/{router,schemas,dependencies}.py`: auth router under `/auth`, RFC 7807 error handlers.

The seeded HR account is created idempotently at startup: bcrypt-hash `seed_hr_password`, role `hr`, email `seed_hr_email`, skipping creation when that email already exists.

### 6.3 `catalog`

- `domain/entities.py`: `Role` (id, name), `Question` (id, code, sort_order, prompt, grading_guide).
- `domain/repositories.py`: `RoleRepository` (list, get, get_by_name), `QuestionRepository` (list_ordered, get, get_by_code).
- `domain/exceptions.py`: `RoleNotFoundError`, `QuestionNotFoundError`.
- `infrastructure/models.py`: `RoleModel` (`roles`), `QuestionModel` (`questions`).
- `infrastructure/repository.py`: SQLAlchemy implementations.
- `application/service.py`: `CatalogService` (list roles with candidate counts, resolve question by id or code, ensure-role-exists, upsert question).
- `presentation/router.py`: `GET /hr/roles`.

### 6.4 `candidates`

- `domain/entities.py`: `Candidate` (id, name, email, role_id, session_token, external_ref, created_at), `Answer` (id, candidate_id, question_id, answer_type, text, audio_key, content_hash, version, external_ref, submitted_at).
- `domain/repositories.py`: `CandidateRepository` (add, get, get_by_email, get_by_session_token, get_by_external_ref, list_by_role), `AnswerRepository` (upsert, get_active, get, list_for_candidate, get_by_external_ref).
- `domain/exceptions.py`: `CandidateNotFoundError`, `CandidateAlreadyExistsError`, `AnswerNotFoundError`.
- `infrastructure/models.py`: `CandidateModel` (`candidates`), `AnswerModel` (`answers`).
- `infrastructure/repository.py`: SQLAlchemy implementations, including the atomic answer upsert in section 9.
- `application/service.py`: `CandidatesService` (create candidate, resolve by session token, interview context) and `AnswersService` (submit text/audio, resubmission, read models).
- `presentation/`: `candidate_router` (session auth) and `hr_router` (JWT `hr`), each with its own schemas and the `require_candidate` dependency.

The `require_candidate` dependency reads the `X-Candidate-Token` header, resolves the candidate by `session_token`, and raises `401` for a missing or unknown token.
It never touches `libs/iam`.

### 6.5 `scoring`

- `domain/entities.py`: `ScoringJob` (id, answer_id, status, suggested_score, suggested_reasoning, final_score, override_reason, overridden_by, attempt_count, last_error, claimed_at, created_at, updated_at, scored_at).
- `domain/repositories.py`: `ScoringJobRepository` (claim_next_queued, complete, fail, retry, list_by_status, get, load_scoring_input).
- `domain/exceptions.py`: `ScoringJobNotFoundError`, `ScoringJobInvalidTransitionError`.
- `application/ports.py`: `ScoringLlmPort` protocol.
- `application/service.py`: `ScoringService` (override score, retry job, list jobs, enqueue) and `ScoringWorker`.
- `infrastructure/models.py`: `ScoringJobModel` (`scoring_jobs`).
- `infrastructure/repository.py`: SQLAlchemy implementation with `FOR UPDATE SKIP LOCKED` claim and a `load_scoring_input` join over `answers` and `questions`.
- `infrastructure/llm.py`: `DeepSeekLlm` adapter.
- `infrastructure/storage.py`: `FileStorage` protocol plus `LocalFileStorage`.
- `presentation/{router,schemas,dependencies}.py`: score-override, scoring-jobs list, and retry endpoints.

### 6.6 `importing`

- `application/service.py`: `ImportService` orchestrating catalog, candidates, and scoring services.
- `presentation/{router,schemas}.py`: `POST /hr/import` (multipart zip).
- No domain or infrastructure of its own; it composes the other modules.

### 6.7 `health`

`GET /health` executes `SELECT 1` on PostgreSQL and returns `{"status": "ok"}`, mirroring the template.

## 7. Data Model

### 7.1 Enums

- `answer_type`: `"text"` | `"audio"` (stored as a plain string column, validated in Pydantic).
- `scoring_status`: `"queued"` | `"scored"` | `"failed"` | `"needs_a_person"`.
- `iam_role`: `"hr"` (plus the template's `admin` and `regular`).

### 7.2 Tables

`users` (auth):

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| email | str unique indexed | |
| password_hash | str | bcrypt |
| role | str default "hr" | |
| created_at | timestamptz | |
| updated_at | timestamptz | |

`refresh_tokens` (auth):

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| token_id | str unique indexed | single-use rotation jti |
| user_id | int FK -> users.id CASCADE | |
| expires_at | timestamptz | |
| created_at | timestamptz | |

`roles` (catalog):

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| name | str unique | Backend Engineer, Sales Executive, Customer Success Associate, Marketing Coordinator, Finance Analyst |
| created_at | timestamptz | |

`questions` (catalog):

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| code | str unique | "Q1".."Q6" |
| sort_order | int unique | 1..6 |
| prompt | text | |
| grading_guide | jsonb | `{"1":..,"2":..,"3":..,"4":..}` |

`candidates` (candidates):

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| name | str nullable | |
| email | str unique | HR keys creation off it |
| role_id | int FK -> roles.id | |
| session_token | str unique indexed | unguessable secret |
| external_ref | str nullable indexed | data-pack `candidate_id` |
| created_at | timestamptz | |

`answers` (candidates):

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| candidate_id | int FK -> candidates.id | |
| question_id | int FK -> questions.id | |
| answer_type | str | text \| audio |
| text | text nullable | transcript for text answers |
| audio_key | str nullable | FileStorage key |
| content_hash | str | SHA-256 hex of submitted bytes |
| version | int default 1 | increments on changed resubmit |
| external_ref | str nullable indexed | data-pack `answer_id` |
| submitted_at | timestamptz | |

Unique constraint on `(candidate_id, question_id)`: exactly one active row per candidate x question.

`scoring_jobs` (scoring):

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| answer_id | int FK -> answers.id unique | 1:1 with answer |
| status | str | queued \| scored \| failed \| needs_a_person |
| suggested_score | int nullable | 1..4 (LLM) |
| suggested_reasoning | text nullable | |
| final_score | int nullable | 1..4 (HR decision) |
| override_reason | text nullable | required when HR sets final_score |
| overridden_by | int nullable FK -> users.id | |
| attempt_count | int default 0 | |
| last_error | text nullable | |
| claimed_at | timestamptz nullable | worker lease |
| created_at | timestamptz | |
| updated_at | timestamptz | |
| scored_at | timestamptz nullable | |

Relationships mirror the contract: `roles 1-N candidates 1-N answers 1-1 scoring_jobs`, `questions 1-N answers`, `users 1-N scoring_jobs (overridden_by)`.

## 8. Authentication and Authorization

### 8.1 HR (JWT, role `hr`)

`/hr/*` routers declare `dependencies=[Depends(require_auth(AuthType.JWT)), Depends(require_roles(Role.HR))]`.
`POST /auth/sign-in` returns `{user, access_token, refresh_token}` with a 1h access token and a single-use rotating refresh token, exactly as the contract specifies.
`POST /auth/refresh-tokens` validates and consumes the refresh token's jti.
`POST /auth/sign-out` revokes the refresh token and returns `204`.
Invalid credentials, refresh reuse, and non-`hr` roles map to `401`/`403` via the IAM exception handlers.

### 8.2 Candidate (session token)

Candidate routes use `require_candidate`, a custom dependency independent of `libs/iam`.
It reads `X-Candidate-Token`, resolves the candidate by `session_token`, and raises `401` on a missing or unknown token.
Every candidate endpoint scopes its reads to that candidate only; grades and grading guides are never serialized in the candidate area.

## 9. Resubmission Correctness

Submission always computes `content_hash = sha256(submitted bytes)`.
For text answers the bytes are the UTF-8 encoding of `text`; for audio the raw file bytes.

The answer upsert is a single atomic statement keyed on the unique `(candidate_id, question_id)`:

```sql
INSERT INTO answers (candidate_id, question_id, answer_type, text, audio_key, content_hash, version, external_ref, submitted_at)
VALUES (...)
ON CONFLICT (candidate_id, question_id) DO UPDATE
  SET text = EXCLUDED.text,
      audio_key = EXCLUDED.audio_key,
      content_hash = EXCLUDED.content_hash,
      version = answers.version + 1,
      submitted_at = NOW()
  WHERE answers.content_hash <> EXCLUDED.content_hash
```

The repository returns whether a row actually changed (a changed content hash) versus a byte-identical no-op.
The service resets the scoring job to `queued` only when content changed.
This makes a double-click or racing duplicate submit converge to one row and exactly one score, and keeps byte-identical resubmission from re-scoring.

Audio answers follow the same upsert path but the scoring job is created or reset to `needs_a_person` rather than `queued`.

## 10. Scoring Pipeline

### 10.1 Enqueue

On text answer submit or import of a text answer, the scoring job is created or reset with `status = queued`.
On audio submit or import, the job is created with `status = needs_a_person` and never enters the queue.

### 10.2 Worker

The lifespan starts `SCORING_WORKERS` asyncio tasks, each running the `ScoringWorker.run()` loop:

1. **Claim** - `SELECT ... FROM scoring_jobs WHERE status = 'queued' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1`, then set `claimed_at = now()` in the same transaction.
2. **Score** - load the question prompt and grading guide (system) and the candidate text (user, delimited as untrusted data), call `ScoringLlmPort`.
3. **Validate** - strictly validate the adapter reply to `{score: int 1..4, reasoning: str}`; anything else is rejected.
4. **Store** - on success set `suggested_score`, `suggested_reasoning`, `final_score = suggested_score`, `status = scored`, `scored_at = now()`, and clear `claimed_at`.
5. **Failure** - increment `attempt_count`; below `SCORING_MAX_ATTEMPTS` re-queue with backoff, otherwise set `status = failed` and `last_error`.
   A failed job has no `final_score` and is never shown as a score.

On shutdown the lifespan sets a stop event, cancels the worker tasks, and awaits them before disposing the engine.

### 10.3 Stale-lease recovery

At startup the worker resets any `status = 'queued'` row whose `claimed_at` is older than `SCORING_LEASE_TIMEOUT_SECONDS` by clearing `claimed_at`, so jobs abandoned by a crashed worker become claimable again.

### 10.4 LLM adapter

`ScoringLlmPort` is a protocol:

```python
class ScoringLlmPort(Protocol):
    async def score(self, prompt: str, grading_guide: dict[str, str], answer_text: str) -> LlmScore: ...
```

`LlmScore` is `{score: int, reasoning: str}` with `1 <= score <= 4`.
`DeepSeekLlm` calls the DeepSeek OpenAI-compatible chat-completions endpoint over `httpx.AsyncClient`, configured by `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, and `DEEPSEEK_BASE_URL`.
The system prompt instructs the model that the candidate text is untrusted data and never instructions.
The reply is schema-validated so only a `score` and `reasoning` can be stored, defeating prompt injection.

### 10.5 Audio storage

`FileStorage` is a protocol with `save(key, data)`, `open(key)`, and `delete(key)`.
`LocalFileStorage` writes under `AUDIO_STORAGE_DIR`.
`GET /hr/answers/{id}/audio` streams the stored bytes with the audio content type.

## 11. Data-Pack Import

`POST /hr/import` accepts the `business-systems-pack.zip` and orchestrates:

1. Parse `questions.md` and upsert the six questions (prompt + grading guide from the 1-4 bullets).
2. Ensure the five roles from the `Open roles` list exist.
3. Parse `pipeline_log.csv` into `candidate_id -> (name, email, role)`.
4. For each `answers/*.json`, resolve the role by name, find-or-create the candidate by `external_ref = candidate_id` (set `name`/`email` from the pipeline log, else a placeholder from `candidate_id`, and generate a `session_token`), then create the answer by `external_ref = answer_id`.
   Transcript answers enqueue a `queued` scoring job; audio-only answers store the `.m4a` and create a `needs_a_person` job.
5. Return the summary counts.

Import is idempotent on `external_ref`: re-importing the same pack does not duplicate questions, candidates, or answers.
Unreadable zip or unexpected layout returns `400`; oversized files return `413`.

## 12. Cross-Cutting Concerns

### 12.1 Config

`Settings(JwtSettings)` extends the IAM settings and adds:

| Env var | Default | Notes |
|---|---|---|
| `database_url` | `postgresql+asyncpg://postgres:postgres@api-db:5432/talotrace` | |
| `candidate_web_origin` | - | builds the interview link |
| `cors_origins` | `[]` | the two FE origins |
| `scoring_workers` | `2` | worker pool size |
| `scoring_max_attempts` | `3` | before `failed` |
| `scoring_lease_timeout_seconds` | `300` | stale-lease reset |
| `deepseek_api_key` | - | |
| `deepseek_model` | `deepseek-chat` | |
| `deepseek_base_url` | `https://api.deepseek.com` | |
| `audio_storage_dir` | `/tmp/talotrace-audio` | local volume in phase 1 |
| `seed_hr_email` | `hr@talotrace.ai` | |
| `seed_hr_password` | - | required to seed the HR account |

`jwt_secret`, `jwt_algorithm`, `jwt_access_token_ttl_seconds`, and `jwt_refresh_token_ttl_seconds` are inherited from `JwtSettings`.

### 12.2 Lifespan

The app factory mirrors the template's `create_app(settings)`.
The lifespan creates the engine and session factory, builds all module services on `app.state`, seeds the HR account idempotently, starts the scoring workers, and registers clean shutdown.

### 12.3 Middleware and error handling

The app adds FastAPI `CORSMiddleware` from `CORS_ORIGINS`.
It registers the IAM exception handlers plus per-module RFC 7807 handlers mapping `NotFound -> 404`, `AlreadyExists -> 409`, `InvalidTransition -> 409`, and `Unauthorized -> 401`.

## 13. Migrations and Seeding

Alembic migrations define the seven tables with the columns, indexes, and constraints in section 7, including the `(candidate_id, question_id)` unique key and the `external_ref` unique index on both `candidates` and `answers`.
Startup seeds only the HR account (bcrypt, idempotent on email).
Roles and questions are created by `POST /hr/import`.
The README documents the clean-machine flow: migrate, run, sign in, import the pack.

## 14. Testing and Verification

### 14.1 Service unit tests (in-memory fakes)

- Catalog: role/question resolution, ensure-role-exists, question upsert.
- Candidates: resubmission idempotency (byte-identical no-op vs changed-content re-queue), version increment, candidate isolation.
- Scoring: override reason required, retry state machine, enqueue transitions, stale-lease reset.
- Auth: sign-in, refresh rotation, sign-out revocation.

### 14.2 Worker tests (fake LLM)

With a `FakeScoringLlmPort`, cover a valid score, an out-of-range score, a missing field, an injected-instruction answer, and max-attempts -> `failed`.

### 14.3 HTTP route tests (`httpx.AsyncClient`)

- Auth: `401` on bad credentials, `403` on non-`hr` role.
- Candidate: unknown token `401`, no cross-candidate reads, no grades/grading guides in candidate responses.
- Score override: `422` on bad `final_score`, missing reason rejected, `409` on wrong status, `404` on unknown answer.
- Retry: `409` unless `failed`, `404` unknown job.

### 14.4 Postgres integration and end-to-end

`FOR UPDATE SKIP LOCKED` claim, the atomic answer upsert, and the worker are covered by docker-compose integration tests and an end-to-end run that imports the data pack, observes text answers reach `scored`, audio answers become `needs_a_person`, and a duplicate submission yields a single score.

## 15. Traceability

| Requirement | Design guarantee |
|---|---|
| Same answer twice does not create two scores | Unique `(candidate_id, question_id)`; atomic upsert keyed on `content_hash`; job reset only on changed content |
| HR sees which submission counts | One active answer per question; `version` + `submitted_at` |
| Candidate cannot see grades or HR data | `require_candidate` scopes by token; candidate routes never serialize scores or grading guides; `/hr/*` requires JWT `hr` |
| Failed job visible with retry, never shown as a score | `status = failed` + `last_error`; retry resets to `queued`; no `final_score` |
| Prompt injection cannot change the score | Untrusted-text delimiters + strict output schema validation |
| Typed data-pack answers load and score | `POST /hr/import` enqueues text answers |
| Audio stored and visible to HR | `answer_type = audio` + `audio_key`; `GET /hr/answers/{id}/audio` streams it |
| Runs from README on a clean machine | `docker-compose.yml` boots Postgres + API; README documents migrate/run/import |
