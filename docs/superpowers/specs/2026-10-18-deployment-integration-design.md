# Talotrace Interview Scoring - Deployment & Integration Design

**Date:** 2026-10-18
**Status:** Accepted
**Repo:** `nhat8002nguyen/talot-assessment` (private, monorepo)
**Depends on:** `2026-10-18-api-contract-design.md` (the API contract this plan wires together)

## 1. Goal

Define how the three components - `apps/api` (FastAPI monolith), `apps/candidate-web`, and `apps/hr-web` (Next.js 16) - run together locally via Docker Compose, then deploy to production: the two web apps on Vercel and the backend on a single VPS.

This document is the deployment contract the three implementation specs must honor (port, env var names, CORS allow-list). It is written before the implementations so the later integration step is wiring, not rework.

## 2. Scope

In scope:

- Local full-stack harness via `docker compose` (api + db + both web apps).
- Production VPS deploy for the backend (nginx TLS termination, certbot, GHCR image, Alembic migrations).
- Production Vercel deploy for the two web apps.
- CI/CD: GitHub Actions builds/pushes the api image and SSH-redeploys the VPS; Vercel auto-deploys the web apps from Git.
- CORS and env var contract.

Out of scope (phase 2 / later):

- Custom domains for the web apps (use Vercel `*.vercel.app` defaults).
- Object storage for audio (local persistent volume for now).
- Horizontal scaling, load balancing, monitoring/alerting beyond a health check.
- CI for the web apps beyond Vercel's Git integration.

## 3. Topology

### 3.1 Local

```text
browser → http://localhost:3001  → candidate-web (Next build)
browser → http://localhost:3002  → hr-web        (Next build)
                                      ↓  http://localhost:3000
                                     api  (uvicorn :3000)
                                      ↓
                                     db   (postgres:18)
```

### 3.2 Production

```text
https://<candidate>.vercel.app ─┐
https://<hr>.vercel.app ────────┼─→ https://talot-api.nate-ng.com
                                │        (nginx :443, TLS)
                                │          ↓
                                │        api (uvicorn :3000)
                                │          ↓
                                │        db (postgres:18)
                                └── VPS: nginx + api + db + certbot
```

- The API domain `talot-api.nate-ng.com` is a placeholder; the actual subdomain is filled at deploy time. Everything is env-driven.
- Vercel terminates TLS for the web apps; nginx + certbot terminate TLS for the API.

## 4. Port & URL Conventions

| Thing | Value |
|---|---|
| API listen port | `3000` (internal and local host port) |
| candidate-web local port | `3001` |
| hr-web local port | `3002` |
| db port | `5432` (internal; optionally exposed for local debugging) |
| API prod origin | `https://talot-api.nate-ng.com` (placeholder) |
| candidate-web prod origin | `https://<candidate>.vercel.app` |
| hr-web prod origin | `https://<hr>.vercel.app` |

The API keeps port `3000` to stay consistent with the `virtual-facility` template (uvicorn `--port 3000`) and the deploy template's nginx `upstream ... server api:3000;`.

## 5. Environment Variable Contract

These are the canonical names. Implementations must read exactly these.

### 5.1 Backend (`apps/api`)

| Var | Meaning | Local example | Prod example |
|---|---|---|---|
| `DATABASE_URL` | asyncpg DSN | `postgresql+asyncpg://postgres:postgres@db:5432/talot` | `postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@api-db:5432/talot` |
| `JWT_SECRET` | HS256 signing secret | dev secret | random 32-byte hex |
| `CORS_ORIGINS` | comma-separated allowed origins | `http://localhost:3001,http://localhost:3002` | `https://<candidate>.vercel.app,https://<hr>.vercel.app` |
| `CANDIDATE_WEB_ORIGIN` | origin used to build interview links | `http://localhost:3001` | `https://<candidate>.vercel.app` |
| `DEEPSEEK_API_KEY` | LLM provider key | - | real key |
| `DEEPSEEK_MODEL` | LLM model id | - | provider default |
| `AUDIO_STORAGE_DIR` | audio file directory | `/data/audio` | `/data/audio` |
| `SCORING_WORKERS` | worker pool size | `2` | `2` |
| `SCORING_MAX_ATTEMPTS` | retry ceiling before `failed` | `3` | `3` |

### 5.2 Web apps (`apps/candidate-web`, `apps/hr-web`)

| Var | Meaning | Local | Prod |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | API origin the browser calls | `http://localhost:3000` | `https://talot-api.nate-ng.com` |

`NEXT_PUBLIC_*` is inlined at Next.js build time, so it is a build argument in the web-app Dockerfiles (local) and a project environment variable on Vercel (prod).

## 6. CORS

The backend reads `CORS_ORIGINS` and reflects the origin in `Access-Control-Allow-Origin` when it is in the allow-list (with credentials if needed). Requests from non-listed origins receive no CORS headers.

- Local: `http://localhost:3001`, `http://localhost:3002`.
- Prod: the two Vercel origins.

Candidate session tokens travel in the `X-Candidate-Token` header (not credentials cookies), so `Access-Control-Allow-Headers` must include `X-Candidate-Token` and `Authorization` alongside `Content-Type`.

## 7. Local Docker Compose

Root `docker-compose.yml` at the monorepo root, used for local integration. Services:

| Service | Image / build | Notes |
|---|---|---|
| `db` | `postgres:18-alpine` | named volume for data; healthcheck |
| `migrate` | build `apps/api` | one-shot `alembic upgrade head`; `depends_on: db (healthy)` |
| `api` | build `apps/api` | `:3000`; `depends_on: migrate (completed)`; audio named volume |
| `candidate-web` | build `apps/candidate-web` | `:3001`; build arg `NEXT_PUBLIC_API_URL=http://localhost:3000` |
| `hr-web` | build `apps/hr-web` | `:3002`; build arg `NEXT_PUBLIC_API_URL=http://localhost:3000` |

Volumes: `db-data`, `audio-data` (mounted at `/data/audio`).

### 7.1 Web-app Dockerfile contract

Each web app ships a production `Dockerfile` that accepts the API origin as a build arg:

```dockerfile
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
# ... install, then:
RUN npm run build
# start via `next start`
```

### 7.2 Backend Dockerfile

`apps/api` ships a multi-stage production `Dockerfile` (uv sync for deps, then run `uvicorn` on `:3000`) and bakes the Alembic config + migrations into the image so `alembic upgrade head` is runnable.

## 8. VPS Deploy (adapting the template)

A committed `deploy/` folder mirrors the reference template but is simplified to our stack. It contains:

```text
deploy/
├── docker-compose.yml          # api + api-db + migrate + nginx + certbot
├── .env.example                # secrets + IMAGE_TAG + GHCR_OWNER + CERTBOT_EMAIL + DOMAIN
├── nginx/
│   ├── nginx.conf              # client_max_body_size 25m
│   └── conf.d/
│       ├── talot-api.conf            # TLS site (active)
│       └── talot-api.tls.conf.example
└── scripts/
    ├── deploy.sh
    ├── init-letsencrypt.sh
    ├── certbot-loop.sh
    └── ghcr-login.sh
```

### 8.1 Services (production compose)

| Service | Image | Notes |
|---|---|---|
| `api` | `ghcr.io/${GHCR_OWNER}/talot-api:${IMAGE_TAG}` | `:3000` internal (no host port - only nginx is exposed) |
| `migrate` | same image | one-shot `alembic upgrade head` |
| `api-db` | `postgres:18-alpine` | named volume |
| `nginx` | `nginx:1.27-alpine` | ports `80:80`, `443:443`; TLS certs volume |
| `certbot` | `certbot/certbot:v3.1.0` | renew loop, docker.sock for reload |

`api` starts after `migrate` completes; `migrate` and `api` start after `api-db` is healthy.

### 8.2 Changes vs the reference template

- Drop NATS, RabbitMQ, Redis, the five Nest services, and all but one Postgres DB.
- `client_max_body_size` raised from `2m` to `25m` for audio uploads.
- Health check in `deploy.sh` uses `curl`/Python instead of `node -e fetch`.
- Migrations via Alembic (`migrate` service), not TypeORM synchronize.
- No WebSocket location block.
- Audio stored on a named volume mounted at `/data/audio`.

### 8.3 Host bootstrap (once)

As root on the VPS (Ubuntu 24.04): install Docker + Compose v2, clone the repo to `/opt/talot-assessment`, copy `.env.example` to `.env`, generate secrets (`openssl rand -hex 32` for `JWT_SECRET`, `openssl rand -base64 24` for `POSTGRES_PASSWORD`), set `CERTBOT_EMAIL`, `DOMAIN`, `GHCR_OWNER`. Open firewall ports 22/80/443. Run `./scripts/init-letsencrypt.sh` (issues cert), then `IMAGE_TAG=... ./scripts/deploy.sh`.

## 9. CI/CD

### 9.1 Backend - GitHub Actions

`.github/workflows/deploy-backend.yml`:

- Trigger: push to `main` touching `apps/api/**`, `libs/**`, or `deploy/**`; plus `workflow_dispatch`.
- Build: `docker build` `apps/api` → tag `ghcr.io/${GHCR_OWNER}/talot-api:${sha}` and `:latest` → push to GHCR.
- Deploy: SSH to the VPS, `git pull`, set `IMAGE_TAG=${sha}` and `GHCR_OWNER` in `deploy/.env`, run `./scripts/deploy.sh`.

Secrets (repository): `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `VPS_SSH_PORT` (default 22). `GHCR_OWNER` is a repository variable. GHCR packages are public for pull (or the host logs in once via `ghcr-login.sh`).

### 9.2 Web apps - Vercel

Two Vercel projects with Git integration on this monorepo:

| Project | Root Directory | Env var |
|---|---|---|
| candidate-web | `apps/candidate-web` | `NEXT_PUBLIC_API_URL=https://talot-api.nate-ng.com` |
| hr-web | `apps/hr-web` | `NEXT_PUBLIC_API_URL=https://talot-api.nate-ng.com` |

Vercel auto-detects Next.js and deploys on push to the configured branch. Add `vercel.json` per app only if a custom build/route is needed.

## 10. Integration Runbook (post-implementation)

After all three implementations are merged, two wiring executions reconcile each web app against the live API:

1. **Backend first**: `docker compose up` locally, run migrations, import the data pack, confirm `/health` and scoring jobs reach `scored`.
2. **Candidate web app**: point `NEXT_PUBLIC_API_URL` at the API, exercise open-link → answer (text + audio) → resume → resubmit → confirmation.
3. **HR web app**: sign-in → roles → candidates → override score → retry a failed job.
4. Fix any contract drift (field names, status codes, headers) in the web apps.
5. Deploy: push backend (Actions → VPS), then Vercel builds, then re-verify against production URLs with the production CORS list.

## 11. Verification

### 11.1 Local

- `docker compose up` brings up all five services; `migrate` exits 0; `/health` returns `{"status":"ok"}`.
- Candidate flow and HR flow both work end-to-end from the browser against `http://localhost:3000`.

### 11.2 Production

- `curl -fsS https://talot-api.nate-ng.com/health` → `{"status":"ok"}`.
- Import the data pack via the HR UI; text answers reach `scored`, audio answers are `needs_a_person`.
- Both Vercel apps load over HTTPS and call the API cross-origin with correct CORS headers.

## 12. Assumptions & Not Built

- Web apps use Vercel default domains (no custom domains in phase 1).
- Single VPS; no replication, autoscaling, or external object storage.
- HTTPS only on the API; Vercel provides HTTPS for the web apps.
- No database backups or monitoring beyond the health endpoint (phase 2).
