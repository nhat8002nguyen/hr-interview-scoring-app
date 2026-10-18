# Talotrace Assessment

Monorepo for the Talotrace interview-scoring product.
Each application is self-contained inside its own folder under `apps/`.

## Apps

- [`apps/backend`](./apps/backend) - FastAPI backend on port `3000`.
  It has its own `uv` workspace, `uv.lock`, Dockerfiles, migrations, and tests.
- [`apps/candidate-web`](./apps/candidate-web) - candidate Next.js app on port `3001`.
- [`apps/hr-web`](./apps/hr-web) - HR Next.js app on port `3002`.

## Local full stack

Start Postgres, migrations, the backend, and both web apps from the repository root:

```bash
docker compose up --build
```

Or detached:

```bash
docker compose up -d --build
```

The `migrate` service runs `alembic upgrade head` and the `api` service waits for it to finish before starting.
The web apps start after the API is healthy.

After the stack is up:

- Candidate app: http://localhost:3001
- HR app: http://localhost:3002
- API health: http://localhost:3000/health

Run the local smoke check:

```bash
./scripts/smoke-local.sh
```

Tear down and remove volumes:

```bash
docker compose down -v
```

The local Compose file builds the candidate app with `NEXT_PUBLIC_API_URL=http://localhost:3000` because the browser calls the API directly.
It builds the HR app with `NEXT_PUBLIC_API_URL=http://api:3000` because every HR API call is server-side inside the container.

## Backend development

See [`apps/backend/README.md`](./apps/backend/README.md) for local backend setup, tests, migrations, and environment variables.
