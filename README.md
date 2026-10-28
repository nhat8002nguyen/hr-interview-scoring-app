# Interview Scoring

A side project for scoring interview answers.
Candidates answer six questions through a personal link.
HR reviews each answer, sees an LLM-suggested score with reasoning, and can override it with a required reason.

## Live demo

- Candidate app: https://talot-candidate-web.vercel.app
- HR app: https://talot-hr-web.vercel.app
- API health: https://talot-api.nate-ng.com/health

Sign in to the HR app with the seeded demo account `hr@talotrace.ai` / `4uuXKGhi24zDU4MShW8dpJRK`, or create your own account from the sign-up page.
Candidate links are created from the HR app or returned by the data-pack import.

## Repository layout

```text
apps/
  backend/          FastAPI API, scoring workers, migrations, tests
  candidate-web/    Next.js candidate interview app, port 3001
  hr-web/           Next.js HR app, port 3002
docs/superpowers/specs/   Accepted design specs
deploy/             Production VPS compose and deploy scripts
scripts/            Local smoke checks
docker-compose.yml  Full local stack
```

Everything runs from the repository root except the backend-only workflow, which also has its own Compose file.

## Setup

Prerequisites:

- Docker with Docker Compose v2 for the full stack
- `uv` and Python 3.14 for backend development outside Docker
- Node.js 22+ and npm for the web apps outside Docker

Create the root env file and add a DeepSeek key for live scoring:

```bash
cp .env.example .env
# edit .env and set DEEPSEEK_API_KEY
```

Without a key the API still runs and all non-scoring flows work.
Text answers will fail scoring after their retries and appear as `failed`, which HR can retry once a key is configured.

## How to run

Start Postgres, migrations, the API, and both web apps from the repository root:

```bash
docker compose up --build
```

Or in the background:

```bash
docker compose up -d --build
```

The `migrate` service runs `alembic upgrade head`.
The API waits for migrations, and the web apps wait for the API health check.

Open:

- Candidate app: http://localhost:3001
- HR app: http://localhost:3002
- API docs: http://localhost:3000/docs
- API health: http://localhost:3000/health

On a clean database, either import a data pack from `/import` in the HR app or create a candidate from `/candidates/new`.
Then open the returned interview link in the candidate app.

### Backend only

The backend has a standalone Compose file and env example:

```bash
cd apps/backend
cp .env.example .env
docker compose up --build
```

This starts Postgres on `localhost:5432` and the API on `localhost:3000`, and runs migrations automatically.
See [`apps/backend/README.md`](./apps/backend/README.md) for the non-Docker workflow.

Stop the stack:

```bash
docker compose down
```

Remove the database and audio volumes too:

```bash
docker compose down -v
```

## How to test

### Backend

Run from `apps/backend`:

```bash
uv sync
uv run pytest -q
uv run ruff check .
uv run mypy libs src
```

The suite covers auth, candidate isolation, resubmission idempotency, the submission cap, score overrides, retry transitions, the scoring worker with a fake LLM, import idempotency, and an end-to-end import/score test.

### Web apps

Candidate app:

```bash
cd apps/candidate-web
npm ci
npm test
npm run lint
npm run typecheck
```

HR app:

```bash
cd apps/hr-web
npm ci
npm test
```

Playwright specs are included in both apps.
They need the full local stack and installed browsers:

```bash
npx playwright install chromium
npx playwright test
```

### Local smoke check

With the full stack running from the repository root:

```bash
./scripts/smoke-local.sh
```

This checks `db`, `api`, `candidate-web`, and `hr-web`, loads the HR sign-in page, signs in through the HR BFF, and verifies the candidate CORS preflight.

### API smoke test

`scripts/smoke_integration.py` exercises the deployed or local API end to end: sign in, import a pack, create a candidate, submit text and audio, wait for scoring, and verify audio becomes `needs_a_person`.
It requires a data-pack zip and an audio file:

```bash
(cd apps/backend && uv run python ../../scripts/smoke_integration.py \
  --pack /path/to/business-systems-pack.zip \
  --audio /path/to/answer.m4a)
```

## Postman

Import both files from [`apps/backend/postman`](./apps/backend/postman):

- Collection JSON in that folder
- Local environment JSON in that folder

Select the local environment, start the API, and run `Auth / Sign in (HR)` first.
The request stores the JWTs automatically.
On a clean database, run `HR - import / Import data pack` next so roles and questions exist.
`Create candidate` stores the candidate token, and `Get interview` stores question IDs.
The audio and import requests need a file selected in Postman.

For the deployed API, change `baseUrl` to `https://talot-api.nate-ng.com`.

The same configuration files are linked from [`apps/backend/README.md`](./apps/backend/README.md).

## Architecture note

### Shape

The system is three independently deployable apps: a FastAPI monolith, a candidate Next.js app, and an HR Next.js app.
The API owns all business rules and data.
PostgreSQL is both the system of record and the scoring queue.
Scoring runs as an in-process `asyncio` worker pool inside the API, using `SELECT ... FOR UPDATE SKIP LOCKED` to claim jobs.
Each app is self-contained under `apps/`, with its own dependencies and build files.

### Data model

| Table | Purpose and key rules |
|---|---|
| `roles` | One row per open role. Candidates reference a role. |
| `questions` | The six questions (`Q1`..`Q6`) with prompt and JSONB grading guide (scores 1-4). |
| `candidates` | Name, email, role, and an unguessable `session_token` used by the candidate link. `owner_id` scopes each candidate to its HR account; `email` and `external_ref` are unique per owner. `external_ref` maps imported candidates. |
| `answers` | Exactly one active row per `(candidate_id, question_id)`. Stores text or `audio_key`, a SHA-256 `content_hash`, `version`, and `external_ref`. |
| `scoring_jobs` | One job per answer. Stores status, suggested score/reasoning, final score, override reason, attempt count, lease, and last error. |
| `users` | HR accounts. One seeded account is created at startup; anyone can self-register more. |
| `refresh_tokens` | Single-use rotating refresh tokens for HR sessions. |

Statuses are `queued`, `scored`, `failed`, and `needs_a_person`.
A failed job never exposes a score.

### API endpoints

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/sign-in`, `POST /auth/sign-up`, `POST /auth/refresh-tokens`, `POST /auth/sign-out` |
| Candidate (`X-Candidate-Token`) | `GET /candidate/interview`, `POST /candidate/interview/answers/{question_id}`, `POST /candidate/interview/answers/{question_id}/audio` |
| HR catalog | `GET /hr/roles`, `GET /hr/roles/{role_id}/candidates` |
| HR candidates | `GET /hr/candidates/{candidate_id}`, `POST /hr/candidates` |
| HR answers | `GET /hr/answers/{answer_id}`, `GET /hr/answers/{answer_id}/audio`, `PATCH /hr/answers/{answer_id}/score` |
| HR scoring | `GET /hr/scoring-jobs?status=`, `POST /hr/scoring-jobs/{job_id}/retry` |
| HR import | `POST /hr/import` |
| Health | `GET /health` |

HR endpoints require a Bearer JWT with role `hr`.
Candidate endpoints accept only the session token and never return scores or grading guides.
Errors use RFC 7807 problem details.

### Accounts and data isolation

Anyone can create an HR account from the HR app's sign-up page (`POST /auth/sign-up`, email + password).
Each account owns its candidates and therefore its answers, scoring jobs, and interview links.
Every `/hr/*` read and write is scoped to the signed-in account, and cross-account access returns `404`.
The seeded demo account is an ordinary account.
`roles` and `questions` stay shared, read-only reference data.

Two limitations are accepted and documented:

- Sign-up does not verify the email address.
- There is no password reset. A forgotten password locks the account out.

### How an answer moves from submission to a score

1. The candidate submits text as JSON or audio as multipart form data.
2. The API computes a SHA-256 hash of the submitted bytes.
3. Identical content is an idempotent no-op and returns `200` with `unchanged: true`.
4. Changed content atomically upserts the single answer row, increments `version`, and resets the job to `queued`. Audio resets it to `needs_a_person`.
5. Changed submissions are capped at `MAX_ANSWER_SUBMISSIONS` (default 3). A submit beyond the cap returns `409`.
6. A worker claims the queued job with `FOR UPDATE SKIP LOCKED`.
7. The worker builds a prompt from the question prompt and grading guide, sends the candidate text as untrusted data, and calls the DeepSeek adapter.
8. The reply is strictly validated as `{score: 1-4, reasoning: string}`. Invalid output is rejected.
9. Success stores the suggested score and reasoning and sets `final_score` to the suggested score.
10. Failure increments the attempt count, retries up to `SCORING_MAX_ATTEMPTS` (default 3), then sets `failed` with `last_error`.
11. HR can retry a failed job or override any scored or `needs_a_person` answer with a score and a required reason.

Audio-only answers are stored and shown to HR but are not transcribed or LLM-scored in this version.

### What I chose not to build

These are deferred extras from the original design:

- A score-agreement report against `hr_reference_scores.csv`.
- Transcription and LLM scoring of the five audio-only answers.
- A dedicated "needs a person" list. The status appears in the scoring-job list, but there is no curated queue.
- Candidate ordering to help HR decide who to read first.
- A consent screen and microphone check in the candidate area.
- A richer candidate-facing error and retry flow beyond the invalid-link screen and basic inline errors.

The live demo was originally deferred, then built, so it is not in the list above.

## Design docs and deployment

- Accepted specs: [`docs/superpowers/specs`](./docs/superpowers/specs)
- Backend details and env vars: [`apps/backend/README.md`](./apps/backend/README.md)
- Production deployment and host bootstrap: [`deploy/README.md`](./deploy/README.md)
