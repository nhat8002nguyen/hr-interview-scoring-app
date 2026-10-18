# Talotrace Interview Scoring Backend

FastAPI backend for the Talotrace interview-scoring product.
The backend is a self-contained `uv` workspace in `apps/backend` with the API package (`src/api`), `libs/database`, and `libs/iam`.
Its lockfile, Python version, Dockerfiles, migrations, and tests all live inside the same folder.

The API listens on port `3000`.
Audio files are stored under the directory given by `AUDIO_STORAGE_DIR`.
`CORS_ORIGINS` is a comma-separated allow-list.

## Prerequisites

- Docker (with Docker Compose v2) for the full stack
- `uv` (any recent release that understands `--all-packages`)
- Python 3.14 (required by `requires-python = ">=3.14"`)

## Local development

Run these commands from `apps/backend`:

```bash
cd apps/backend
uv sync
```

Run the test suite:

```bash
uv run pytest -q
```

Run lint, type checks, and tests:

```bash
uv run ruff check .
uv run mypy libs src
uv run pytest -q
```

Run the API locally (against an existing Postgres):

```bash
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/talot
uv run uvicorn api.main:app --port 3000
```

Health check:

```bash
curl -fsS localhost:3000/health
# {"status":"ok"}
```

## Docker

Build the production image from this directory:

```bash
docker build -t talot-backend .
```

Build the development image:

```bash
docker build -f Dockerfile.dev -t talot-backend:dev .
```

The repository-level `docker-compose.yml` builds this app with build context `./apps/backend` and runs it together with the web apps.

The `migrate` service runs `alembic upgrade head` and the `api` service waits for it to finish before starting.

## Migrate, sign in, import flow

The data-pack importer is the HR onboarding path.
On a clean machine:

1. Start the stack from the repository root (`docker compose up --build`).
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

## Layout

```text
apps/backend/
├── alembic.ini
├── Dockerfile
├── Dockerfile.dev
├── libs/
│   ├── database/
│   └── iam/
├── migrations/
├── pyproject.toml
├── src/api/
├── tests/
└── uv.lock
```
