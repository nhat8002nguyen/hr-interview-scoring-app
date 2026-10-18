# Talotrace Interview Scoring Backend

FastAPI backend for the Talotrace interview-scoring product.
It is a `uv` workspace with three packages: `apps/api` (the API), `libs/database`, and `libs/iam`.

The API listens on port `3000`.
Audio files are stored under the directory given by `AUDIO_STORAGE_DIR`.
`CORS_ORIGINS` is a comma-separated allow-list.

## Prerequisites

- Docker (with Docker Compose v2)
- `uv` (any recent release that understands `--all-packages`)
- Python 3.14 (required by the workspace `requires-python = ">=3.14"`)

## Local development

Sync the workspace, including dev dependencies:

```bash
uv sync
```

Run the test suite:

```bash
uv run pytest -q
```

Run the API locally (against an existing Postgres):

```bash
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/talot
uv run --directory apps/api uvicorn api.main:app --port 3000
```

Health check:

```bash
curl -fsS localhost:3000/health
# {"status":"ok"}
```

## Docker Compose

The build context for both `Dockerfile.dev` and `Dockerfile` is the workspace root (`.`), not `apps/api`, because `apps/api` depends on the `libs/` workspace packages.

Start everything (Postgres, migrations, API):

```bash
docker compose up --build
```

Or detached:

```bash
docker compose up -d --build
```

The `migrate` service runs `alembic upgrade head` and the `api` service waits for it to finish before starting.
After the API is up:

```bash
curl -fsS localhost:3000/health
# {"status":"ok"}
```

Tear down and remove volumes:

```bash
docker compose down -v
```

## Migrate, sign in, import flow

The data-pack importer is the HR onboarding path.
On a clean machine:

1. Start the stack (`docker compose up --build`).
   The `migrate` service applies the Alembic migrations automatically.
2. Sign in as the seeded HR account:

   ```bash
   TOKEN=$(curl -fsS -X POST localhost:3000/auth/sign-in \
     -H 'Content-Type: application/json' \
     -d '{"email":"hr@talotrace.ai","password":"change-me"}' \
     | python -c 'import sys, json; print(json.load(sys.stdin)["access_token"])')
   ```

3. Import the HR data pack (`business-systems-pack.zip`):

   ```bash
   curl -fsS -X POST localhost:3000/hr/import \
     -H "Authorization: Bearer $TOKEN" \
     -F "file=@path/to/business-systems-pack.zip"
   ```

The import is idempotent on the data pack's external refs, so re-importing does not duplicate questions, candidates, or answers.

## Environment variables

| Variable | Meaning | Default | Compose example |
|---|---|---|---|
| `DATABASE_URL` | asyncpg DSN | `postgresql+asyncpg://postgres:postgres@db:5432/talot` | same |
| `JWT_SECRET` | HS256 signing secret | `dev-secret-change-me-in-production-32bytes` | `dev-secret-change-me-in-production` |
| `CORS_ORIGINS` | comma-separated allowed origins | empty | `http://localhost:3001,http://localhost:3002` |
| `CANDIDATE_WEB_ORIGIN` | origin used to build interview links | `http://localhost:3001` | same |
| `DEEPSEEK_API_KEY` | LLM provider key | empty | `${DEEPSEEK_API_KEY:-}` |
| `DEEPSEEK_MODEL` | LLM model id | `deepseek-chat` | same |
| `AUDIO_STORAGE_DIR` | audio file directory | `/tmp/talotrace-audio` | `/data/audio` |
| `SCORING_WORKERS` | worker pool size | `2` | `2` |
| `SCORING_MAX_ATTEMPTS` | retry ceiling before `failed` | `3` | `3` |
| `SEED_HR_EMAIL` | seeded HR account email | `hr@talotrace.ai` | same |
| `SEED_HR_PASSWORD` | seeded HR account password | `change-me` | same |

## Related repositories

The two web apps, `apps/candidate-web` and `apps/hr-web`, live in separate repositories and are not part of this Compose file.
Point their `NEXT_PUBLIC_API_URL` at `http://localhost:3000` to run them against this API locally.
