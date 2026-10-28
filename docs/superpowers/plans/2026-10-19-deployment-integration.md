# Deployment & Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the API, candidate web, and HR web into one local Docker Compose stack, then deploy the API to the existing `116.118.9.222` VPS behind its shared nginx and both web apps to Vercel at `https://talot-api.nate-ng.com`.

**Architecture:** Local Compose builds all three apps on ports 3000, 3001, and 3002.
Production runs only `api`, `api-db`, and `migrate` in `/opt/talot-assessment`.
The existing `type-by-voice` nginx joins a shared `talot-edge` Docker network and terminates TLS for `talot-api.nate-ng.com`, so the API stack never binds ports 80 or 443.
GitHub Actions builds `ghcr.io/nhat8002nguyen/talot-api` and SSH-redeploys the host.
Vercel builds each Next.js app with `NEXT_PUBLIC_API_URL`.

**Tech Stack:** Docker Compose v2, Python 3.14, uv, FastAPI, PostgreSQL 18, Next.js 16, nginx 1.27, certbot, GitHub Actions, GHCR, Vercel.

**Spec:** `docs/superpowers/specs/2026-10-18-deployment-integration-design.md`

## Global Constraints

- The API listens on `3000` in every environment.
- Local candidate-web listens on `3001`; local hr-web listens on `3002`.
- Production API origin is `https://talot-api.nate-ng.com`.
- Local API origin is `http://localhost:3000`.
- Use the exact environment variable names from spec section 5: `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS`, `CANDIDATE_WEB_ORIGIN`, `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `AUDIO_STORAGE_DIR`, `SCORING_WORKERS`, `SCORING_MAX_ATTEMPTS`, `NEXT_PUBLIC_API_URL`.
- Never commit a `.env` file or any credential.
- `NEXT_PUBLIC_API_URL` is a Docker build argument for candidate-web.
- Local hr-web uses `NEXT_PUBLIC_API_URL=http://api:3000` because every HR API call is server-side inside the container.
  This is the one deliberate local deviation from spec section 5.2.
- The candidate browser calls the API directly, so the API CORS allow-list must include the candidate origin.
- `Access-Control-Allow-Headers` must include `Content-Type`, `Authorization`, and `X-Candidate-Token`.
- Production nginx sets `client_max_body_size 25m`.
- Audio files live on the `audio-data` volume mounted at `/data/audio`.
- PostgreSQL 18 uses the volume mount `/var/lib/postgresql`, not `/var/lib/postgresql/data`.
- The existing `type-by-voice` stack must keep serving `https://tbv-api.nate-ng.com` throughout.
- Production Compose must not declare host ports 80 or 443.
- Do not use em dashes in repository text; use plain hyphens.

## Inputs Required Before Production Deploy

- VPS root access for `116.118.9.222`: the password is supplied out-of-band as `$VPS_PASSWORD` and must never be written to the repo.
- Vercel token for team `nhat8002nguyens-projects` was provided.
- `DEEPSEEK_API_KEY`: still required before text answers can reach `scored`.
- DNS: the user adds `A talot-api.nate-ng.com -> 116.118.9.222` with proxy disabled (grey cloud) for the first certificate.
- Certbot email: reuse the host value `nv.nhat8002@gmail.com` unless the user says otherwise.
- GHCR pull access: the host already has a `/root/.docker/config.json` entry for `ghcr.io`.
  Verify the first pull and add a `read:packages` token if that login is stale.
- Vercel GitHub integration needs the Vercel GitHub app installed on the private repository.
  The CLI deploy works without it; Git auto-deploy does not.

## Review Focus

- HR sign-in from local Compose: `NEXT_PUBLIC_API_URL` inside the HR container must resolve the API, not the container itself.
  Test: POST `/api/auth/sign-in` through `http://localhost:3002` and assert `200` plus the `hr_access` cookie.
- Candidate audio submission across origins: the browser preflight and the actual `multipart/form-data` upload must both allow the candidate origin and `X-Candidate-Token`.
  Test: OPTIONS and POST in `scripts/smoke_integration.py`.
- Clean-start ordering: on an empty volume, `migrate` must finish before `api`, and `api` must be healthy before the edge proxies.
  Test: `docker compose down -v`, then a cold `up` and health poll.
- Shared-host TLS: issuing a certificate for a second domain must not disturb `tbv-api.nate-ng.com`, and uploads over 2 MB must pass through the edge.
  Test: curl both domains; upload a 3 MB file through the production edge.
- Production build-time API URL: Vercel must inline `https://talot-api.nate-ng.com`, not localhost.
  Test: open the deployed candidate link in a browser and observe a successful cross-origin API request.
- Real scoring availability: text answers must reach `scored`, and a missing or invalid key must surface as `failed` with retry, never as a low score.
  Test: production smoke polls the answer until `scored`; HR UI shows the reasoning.

## File Structure

Create:

- `apps/candidate-web/Dockerfile` and `.dockerignore` - candidate production image.
- `apps/hr-web/Dockerfile` and `.dockerignore` - HR production image.
- `scripts/smoke-local.sh` - asserts the five Compose services and their basic endpoints.
- `scripts/make-pack-zip.sh` - builds the upload zip from the gitignored data pack.
- `scripts/smoke_integration.py` - exercises import, candidate text and audio, CORS, HR detail, and scoring.
- `deploy/docker-compose.yml` - production `api`, `api-db`, and `migrate`.
- `deploy/.env.example` - canonical production environment template.
- `deploy/.gitignore` - ignore `.env`.
- `deploy/nginx/talot-api.http-bootstrap.conf` - ACME-only HTTP server block.
- `deploy/nginx/talot-api.conf` - TLS server block with a 25m upload limit.
- `deploy/nginx/talot-edge.override.yml` - Compose override that joins the existing nginx to `talot-edge`.
- `deploy/scripts/edge-init.sh` - creates the shared network, joins nginx, and issues the certificate.
- `deploy/scripts/deploy.sh` - pulls the image, starts the stack, checks health, and reloads nginx.
- `deploy/scripts/ghcr-login.sh` - logs the host into GHCR when the package stays private.
- `deploy/README.md` - host bootstrap, DNS, edge, deploy, verification, and rollback.
- `.github/workflows/deploy-backend.yml` - test, build, push, and SSH deploy.

Modify:

- `docker-compose.yml` - add candidate-web and hr-web, an API healthcheck, and a shared local API image.
- `apps/backend/tests/test_e2e_import_and_score.py` - fix the data-pack path for the monorepo and skip when the pack is absent.
- `README.md` - document the five-service local stack and point to `deploy/README.md`.

---

### Task 1: Repair the data-pack E2E test

**Files:**
- Modify: `apps/backend/tests/test_e2e_import_and_score.py`

**Interfaces:**
- Produces: `_PACK_DIR = Path(__file__).resolve().parents[3] / "intial-resources" / "business-systems-pack"`.
- Produces: the test skips when that directory is missing.

- [ ] **Step 1: Confirm the current failure**

Run: `(cd apps/backend && uv run pytest tests/test_e2e_import_and_score.py -q)`

Expected: FAIL with `FileNotFoundError` for `<repo>/../intial-resources/business-systems-pack/questions.md`.

- [ ] **Step 2: Fix the path and add the skip**

Change the path to use `parents[3]` without `.parent`.
Add this before `_wait_until_ready` in the test:

```python
if not _PACK_DIR.is_dir():
    pytest.skip("business-systems-pack not present; skipping data-pack E2E")
```

- [ ] **Step 3: Verify**

Run: `(cd apps/backend && uv run pytest tests/test_e2e_import_and_score.py -q)`
Expected: `2 passed`.

Run: `(cd apps/backend && uv run pytest -q)`
Expected: `126 passed`.

- [ ] **Step 4: Commit**

```bash
git add apps/backend/tests/test_e2e_import_and_score.py
git commit -m "test: resolve data pack path in monorepo"
```

---

### Task 2: Build web images and run all five services locally

**Files:**
- Create: `apps/candidate-web/Dockerfile`, `apps/candidate-web/.dockerignore`
- Create: `apps/hr-web/Dockerfile`, `apps/hr-web/.dockerignore`
- Create: `scripts/smoke-local.sh`
- Modify: `docker-compose.yml`, `README.md`

**Interfaces:**
- Produces: Compose services `db`, `migrate`, `api`, `candidate-web`, `hr-web`.
- Produces: candidate-web on `http://localhost:3001` with build arg `NEXT_PUBLIC_API_URL=http://localhost:3000`.
- Produces: hr-web on `http://localhost:3002` with build arg and runtime env `NEXT_PUBLIC_API_URL=http://api:3000`.

- [ ] **Step 1: Write the local smoke script and watch it fail**

Create `scripts/smoke-local.sh` that asserts:

1. `docker compose ps --services` contains `db`, `api`, `candidate-web`, and `hr-web`.
2. `http://localhost:3000/health` returns 200.
3. `http://localhost:3001/` returns 200.
4. `http://localhost:3002/sign-in` returns 200.
5. `POST http://localhost:3002/api/auth/sign-in` with `{"email":"hr@example.com","password":"change-me"}` returns 200 and a `Set-Cookie: hr_access=` header.
6. `OPTIONS http://localhost:3000/candidate/interview` with `Origin: http://localhost:3001` and `Access-Control-Request-Headers: x-candidate-token` returns `Access-Control-Allow-Origin: http://localhost:3001`.

Use a retry loop of up to 120 seconds for the HTTP checks because the API takes about 10 seconds to become ready.
Run `chmod +x scripts/smoke-local.sh && ./scripts/smoke-local.sh`.
Expected: FAIL because the two web services do not exist yet.

- [ ] **Step 2: Create both web Dockerfiles**

Each Dockerfile has four stages: `deps`, `builder`, `runner`.
The `deps` stage runs `npm ci --no-audit --no-fund`.
The `builder` stage accepts `ARG NEXT_PUBLIC_API_URL`, sets it in `ENV`, sets `NEXT_TELEMETRY_DISABLED=1`, copies `node_modules`, copies the app, and runs `npm run build`.
The `runner` stage sets `NODE_ENV=production`, `NEXT_TELEMETRY_DISABLED=1`, `HOSTNAME=0.0.0.0`, copies `node_modules`, `.next`, `package.json`, and `next.config.ts`, and runs `npm run start`.

Use these exact ports:

- candidate-web: `PORT=3001`, `EXPOSE 3001`.
- hr-web: `PORT=3002`, `EXPOSE 3002`, plus `COPY --from=builder /app/public ./public`.

- [ ] **Step 3: Add Docker ignore files**

The backend is now a self-contained workspace at `apps/backend`, so its existing `apps/backend/.dockerignore` is the build-context ignore file and no root `.dockerignore` is needed.
Each web app `.dockerignore` must exclude `node_modules`, `.next`, `.env*`, `e2e`, `tests`, `playwright-report`, `test-results`, `*.log`, `README.md`, and `AGENTS.md`.

- [ ] **Step 4: Update the local Compose file**

Add an extension anchor:

```yaml
x-api-build: &api-build
  context: ./apps/backend
  dockerfile: Dockerfile.dev
```

Use `image: talot-assessment-api:local` and `build: *api-build` for both `migrate` and `api` so Compose builds one image.
Set `restart: unless-stopped` on `db` and `api`, and `restart: "no"` on `migrate`.

Add this API healthcheck:

```yaml
healthcheck:
  test:
    - CMD
    - python
    - -c
    - "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/health', timeout=3)"
  interval: 5s
  timeout: 5s
  retries: 12
  start_period: 30s
```

Add the web services with these exact values:

| Service | Build context | Build arg | Ports | Depends on |
|---|---|---|---|---|
| `candidate-web` | `./apps/candidate-web` | `NEXT_PUBLIC_API_URL=http://localhost:3000` | `3001:3001` | `api` healthy |
| `hr-web` | `./apps/hr-web` | `NEXT_PUBLIC_API_URL=http://api:3000` | `3002:3002` | `api` healthy |

Set `NEXT_PUBLIC_API_URL=http://api:3000` again in the hr-web runtime environment.

- [ ] **Step 5: Start from a clean volume and verify**

Run:

```bash
docker compose down -v
docker compose up -d --build
./scripts/smoke-local.sh
```

Expected: `migrate` exits 0, the four long-running services are up, and the script prints `local smoke ok`.

- [ ] **Step 6: Run the app-level checks**

```bash
(cd apps/candidate-web && npm test && npm run lint && npm run typecheck)
(cd apps/hr-web && npm test && npx tsc --noEmit)
docker compose config --quiet
```

Expected: all commands exit 0.

- [ ] **Step 7: Update README and commit**

Replace the "Related repositories" note with a "Full stack with Docker Compose" section that names ports 3000, 3001, and 3002 and points to `scripts/smoke-local.sh`.

```bash
git add docker-compose.yml README.md scripts/smoke-local.sh \
  apps/candidate-web/Dockerfile apps/candidate-web/.dockerignore \
  apps/hr-web/Dockerfile apps/hr-web/.dockerignore
git commit -m "feat: run all three apps in local compose"
```

---

### Task 3: Verify the local integration end to end

**Files:**
- Create: `scripts/make-pack-zip.sh`, `scripts/smoke_integration.py`

**Interfaces:**
- `scripts/make-pack-zip.sh` writes `intial-resources/business-systems-pack.zip`.
- `scripts/smoke_integration.py` accepts `--api-url`, `--candidate-origin`, `--pack`, `--audio`, `--hr-email`, and `--hr-password`.

- [ ] **Step 1: Add the pack zip builder**

`scripts/make-pack-zip.sh` must zip `questions.md`, `pipeline_log.csv`, and `answers/` with those paths at the zip root.
Run it and verify with `unzip -l` that the zip contains `questions.md`, `pipeline_log.csv`, and 40 files under `answers/`.

- [ ] **Step 2: Write the integration smoke**

Create `scripts/smoke_integration.py` using `httpx`.
Use a unique email such as `smoke+<unix-timestamp>@example.com` for each run.

The script must assert:

1. `POST /hr/import` returns `answers_imported=35`, `scoring_jobs_queued=30`, and `audio_answers_needing_person=5` on a fresh database.
   On an already-imported database it returns `0/0/0`; the script accepts both and prints the summary.
2. `GET /hr/roles` returns 5 roles.
3. `POST /hr/candidates` returns 201 and a `session_token`.
4. `GET /candidate/interview` with `X-Candidate-Token` returns 200 and 6 questions.
5. OPTIONS `/candidate/interview` with the candidate origin returns 200 and `Access-Control-Allow-Origin` equal to that origin.
6. `POST /candidate/interview/answers/<q1>` returns 201 with `unchanged=false`.
7. Repeating the identical text returns 200 with `unchanged=true`.
8. `POST /candidate/interview/answers/<q2>/audio` with `A031.m4a` returns 201 and the candidate CORS header.
9. `GET /hr/candidates/<id>` returns two answers; the audio answer is `needs_a_person`.
10. `GET /hr/answers/<q1_answer_id>` reaches `scored` within 600 seconds with `1 <= suggested_score <= 4`.
    If it reaches `failed`, print `last_error` and exit non-zero.

- [ ] **Step 3: Run the local integration**

Put the DeepSeek key in a gitignored root `.env`, restart Compose, and run:

```bash
printf 'DEEPSEEK_API_KEY=%s\n' "$DEEPSEEK_API_KEY" > .env
docker compose up -d
(cd apps/backend && uv run python ../../scripts/smoke_integration.py \
  --api-url http://localhost:3000 \
  --candidate-origin http://localhost:3001 \
  --pack ../../intial-resources/business-systems-pack.zip \
  --audio ../../intial-resources/business-systems-pack/answers/A031.m4a \
  --timeout 600)
```

Expected: the import summary, both answer statuses, and exit 0.

- [ ] **Step 4: Run the existing Playwright flows**

```bash
(cd apps/candidate-web && npx playwright install chromium)

(cd apps/hr-web && \
  E2E_HR_PASSWORD=change-me \
  E2E_PACK_ZIP="$PWD/../../intial-resources/business-systems-pack.zip" \
  npx playwright test)
```

Create a fresh candidate through the HR API and run the candidate suite with `E2E_CANDIDATE_TOKEN` and `E2E_API_URL=http://localhost:3000`.
Expected: both suites pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/make-pack-zip.sh scripts/smoke_integration.py
git commit -m "test: add local integration smoke and pack builder"
```

---

### Task 4: Add production deploy artifacts for the shared host

**Files:**
- Create: `deploy/docker-compose.yml`, `deploy/.env.example`, `deploy/.gitignore`
- Create: `deploy/nginx/talot-api.http-bootstrap.conf`, `deploy/nginx/talot-api.conf`, `deploy/nginx/talot-edge.override.yml`
- Create: `deploy/scripts/edge-init.sh`, `deploy/scripts/deploy.sh`, `deploy/scripts/ghcr-login.sh`
- Create: `deploy/README.md`

**Interfaces:**
- Produces: Compose project `talot-assessment` with `api-db`, `migrate`, and `api`.
- Produces: API alias `talot-api` on external network `talot-edge`.
- Produces: `deploy/scripts/deploy.sh` as the only host deploy entry point.
- Produces: `deploy/scripts/edge-init.sh` as the one-time certificate bootstrap.

- [ ] **Step 1: Write the production environment template**

`deploy/.env.example` must contain exactly these keys:

```text
IMAGE_TAG=latest
GHCR_OWNER=nhat8002nguyen
POSTGRES_USER=talot
POSTGRES_PASSWORD=REPLACE_WITH_LONG_RANDOM
JWT_SECRET=REPLACE_WITH_64_HEX_CHARS
SEED_HR_EMAIL=hr@example.com
SEED_HR_PASSWORD=REPLACE_WITH_LONG_RANDOM
CORS_ORIGINS=https://talot-candidate-web.vercel.app,https://talot-hr-web.vercel.app
CANDIDATE_WEB_ORIGIN=https://talot-candidate-web.vercel.app
DEEPSEEK_API_KEY=REPLACE_WITH_REAL_KEY
DEEPSEEK_MODEL=deepseek-chat
AUDIO_STORAGE_DIR=/data/audio
SCORING_WORKERS=2
SCORING_MAX_ATTEMPTS=3
DOMAIN=talot-api.nate-ng.com
CERTBOT_EMAIL=nv.nhat8002@gmail.com
TBV_DEPLOY_DIR=/opt/type-by-voice/deploy
```

`deploy/.gitignore` contains `.env`.

- [ ] **Step 2: Write the production Compose file**

Use `name: talot-assessment`.
The `api-db` service uses `postgres:18-alpine`, database `talot`, volume `api-db-data:/var/lib/postgresql`, and a `pg_isready` healthcheck.
The `migrate` service uses the API image, `restart: "no"`, and command `["uv", "run", "alembic", "upgrade", "head"]`.
The `api` service uses the API image, `restart: unless-stopped`, `stop_grace_period: 30s`, volume `audio-data:/data/audio`, and the healthcheck from Task 2.

The `api` service must have this exact network block:

```yaml
networks:
  default:
  talot-edge:
    aliases:
      - talot-api
```

It must not declare `ports`.
It depends on `api-db` being healthy and `migrate` completing successfully.
Declare `talot-edge` as `external: true` and volumes `api-db-data` and `audio-data`.
Set sensible memory limits: `api` 512m, `api-db` 256m.

The shared environment block uses the exact names from the global constraints and:

```text
DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@api-db:5432/talot
AUDIO_STORAGE_DIR=/data/audio
```

- [ ] **Step 3: Write the nginx configs**

`deploy/nginx/talot-api.http-bootstrap.conf` is an HTTP-only server for `talot-api.nate-ng.com` that serves `/.well-known/acme-challenge/` from `/var/www/certbot` and returns 503 for every other path.

`deploy/nginx/talot-api.conf` must contain:

- An upstream `talot_api` pointing to `talot-api:3000` with keepalive.
- An HTTP server on 80 that serves ACME challenges and redirects everything else to HTTPS.
- A TLS server on 443 with `http2 on`, `client_max_body_size 25m`, and certificate paths `/etc/letsencrypt/live/talot-api.nate-ng.com/fullchain.pem` and `privkey.pem`.
- An ACME location on 443 as well as 80.
- A proxy location that sets `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`, and `Connection ""`, then proxies to `http://talot_api`.

`deploy/nginx/talot-edge.override.yml` attaches the existing nginx service to `default` and external `talot-edge`.

- [ ] **Step 4: Write the edge bootstrap script**

`deploy/scripts/edge-init.sh` must:

1. Source `deploy/.env`.
2. Require `DOMAIN` and `CERTBOT_EMAIL`.
3. Create the `talot-edge` network if missing.
4. Copy `deploy/nginx/talot-edge.override.yml` to `$TBV_DEPLOY_DIR/docker-compose.override.yml` when absent.
   If the override exists, fail unless it already references `talot-edge`.
5. Copy the HTTP bootstrap config to `$TBV_DEPLOY_DIR/nginx/conf.d/talot-api.conf`.
6. From `$TBV_DEPLOY_DIR`, run `docker compose up -d --no-deps nginx`, `nginx -t`, and `nginx -s reload`.
7. Run certbot once with `certonly --webroot -w /var/www/certbot --email "$CERTBOT_EMAIL" --agree-tos --no-eff-email --domains "$DOMAIN"`.
8. Print that the certificate is issued and that `deploy.sh` installs the TLS site.

- [ ] **Step 5: Write the deploy script**

`deploy/scripts/deploy.sh` must:

1. Source `deploy/.env`.
2. Require `IMAGE_TAG` and `GHCR_OWNER`.
3. Run `docker compose pull` and `docker compose up -d --remove-orphans`.
4. Poll `docker compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/health', timeout=3)"` for up to 90 seconds.
5. Find the existing nginx by the labels `com.docker.compose.project=type-by-voice` and `com.docker.compose.service=nginx`.
6. Connect that nginx container to `talot-edge` if it is not already attached.
7. Copy `deploy/nginx/talot-api.conf` to `$TBV_DEPLOY_DIR/nginx/conf.d/talot-api.conf`.
8. From `$TBV_DEPLOY_DIR`, run `nginx -t` and `nginx -s reload`.

`deploy/scripts/ghcr-login.sh` reads `GHCR_USER` and `GHCR_TOKEN` and runs `docker login ghcr.io --password-stdin`.

- [ ] **Step 6: Write the deploy README**

Cover DNS, host layout, the shared edge, first run (`edge-init.sh` then `deploy.sh`), verification of both API domains, rollback by changing `IMAGE_TAG`, and the security note about `.env` and the Docker socket.

- [ ] **Step 7: Validate the artifacts**

```bash
chmod +x deploy/scripts/*.sh
bash -n deploy/scripts/edge-init.sh
bash -n deploy/scripts/deploy.sh
bash -n deploy/scripts/ghcr-login.sh
docker compose -f deploy/docker-compose.yml --env-file deploy/.env.example config --quiet
```

Validate nginx with a throwaway certificate and a resolvable upstream:

```bash
tmp="$(mktemp -d)"
openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
  -subj "/CN=talot-api.nate-ng.com" \
  -keyout "$tmp/privkey.pem" -out "$tmp/fullchain.pem" >/dev/null 2>&1
docker run --rm --add-host talot-api:127.0.0.1 \
  -v "$PWD/deploy/nginx/talot-api.conf:/etc/nginx/conf.d/default.conf:ro" \
  -v "$tmp:/etc/letsencrypt/live/talot-api.nate-ng.com:ro" \
  nginx:1.27-alpine nginx -t
```

Expected: `syntax is ok` and `test is successful`.

- [ ] **Step 8: Commit**

```bash
git add deploy
git commit -m "feat: add production deploy artifacts for shared nginx host"
```

---

### Task 5: Add the backend CI workflow

**Files:**
- Create: `.github/workflows/deploy-backend.yml`

**Interfaces:**
- Consumes: secrets `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `VPS_SSH_PORT` and variable `GHCR_OWNER`.
- Produces: `ghcr.io/<owner>/talot-api:<sha>` and `:latest`.
- Produces: an SSH deploy that updates `IMAGE_TAG` in `/opt/talot-assessment/deploy/.env` and runs `deploy/scripts/deploy.sh`.

- [ ] **Step 1: Write the workflow**

The workflow triggers on pushes to `main` touching `apps/backend/**`, `apps/backend/Dockerfile`, `apps/backend/pyproject.toml`, `apps/backend/uv.lock`, `deploy/**`, or the workflow file, plus `workflow_dispatch`.
Set `permissions: contents: read` and `packages: write`.

The `test` job:

1. Checks out the repo.
2. Uses `astral-sh/setup-uv@v6`.
3. Runs every command with `working-directory: apps/backend`:
   `uv sync --all-packages --group dev`, `uv run ruff check .`, `uv run mypy libs src`, and `uv run pytest -q`.

The `build-and-deploy` job needs `test` and:

1. Logs in to `ghcr.io` with `github.actor` and `secrets.GITHUB_TOKEN`.
2. Builds with `docker/build-push-action@v6`, context `apps/backend`, file `Dockerfile`, pushing `ghcr.io/${{ github.repository_owner }}/talot-api:${{ github.sha }}` and `:latest`.
3. Deploys with `appleboy/ssh-action@v1` using the four secrets and this script:

```bash
set -euo pipefail
cd /opt/talot-assessment
git fetch origin main
git reset --hard origin/main
cd deploy
sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=${{ github.sha }}/" .env
./scripts/deploy.sh
```

- [ ] **Step 2: Validate the YAML**

Run: `python3 -c 'import yaml, pathlib; yaml.safe_load(pathlib.Path(".github/workflows/deploy-backend.yml").read_text())'`
Expected: exit 0.

- [ ] **Step 3: Commit but do not push**

```bash
git add .github/workflows/deploy-backend.yml
git commit -m "ci: build and deploy backend image"
```

Do not push until Task 7 has created the host clone, `.env`, and the CI key.

---

### Task 6: Create the Vercel projects and record production URLs

**Files:**
- No repository files.

**Interfaces:**
- Consumes: Vercel token and team ID `team_tKyNGOwj1S8o3c7LpazY2Nte`.
- Produces: projects `talot-candidate-web` with root `apps/candidate-web` and `talot-hr-web` with root `apps/hr-web`.
- Produces: the two production URLs used for CORS and `CANDIDATE_WEB_ORIGIN`.

- [ ] **Step 1: Create both projects with the correct root directory**

Use `POST https://api.vercel.com/v11/projects?teamId=$TEAM_ID` with:

```json
{"name":"talot-candidate-web","framework":"nextjs","rootDirectory":"apps/candidate-web"}
```

and the same body with `talot-hr-web` and `apps/hr-web`.
If a project already exists, fetch it with `GET /v9/projects/<name>` and verify `rootDirectory`.

- [ ] **Step 2: Set the API URL on both projects**

Use `POST https://api.vercel.com/v10/projects/<id>/env?teamId=$TEAM_ID` with:

```json
{"key":"NEXT_PUBLIC_API_URL","value":"https://talot-api.nate-ng.com","type":"plain","target":["production","preview"]}
```

- [ ] **Step 3: Record the production URLs**

Fetch both projects and record their names and assigned production URLs.
Expected defaults are `https://talot-candidate-web.vercel.app` and `https://talot-hr-web.vercel.app`.
If Vercel assigned different URLs, use the actual values for `CORS_ORIGINS` and `CANDIDATE_WEB_ORIGIN` in Task 7.

- [ ] **Step 4: Link each app locally**

```bash
(cd apps/candidate-web && vercel link --yes --team "$TEAM_ID" --project talot-candidate-web --token "$VERCEL_TOKEN")
(cd apps/hr-web && vercel link --yes --team "$TEAM_ID" --project talot-hr-web --token "$VERCEL_TOKEN")
```

Expected: `.vercel/project.json` exists in each app and is ignored by Git.

- [ ] **Step 5: Connect Git integration**

```bash
(cd apps/candidate-web && vercel git connect https://github.com/nhat8002nguyen/talot-assessment --token "$VERCEL_TOKEN")
(cd apps/hr-web && vercel git connect https://github.com/nhat8002nguyen/talot-assessment --token "$VERCEL_TOKEN")
```

Expected: both report the repository connected.
If the Vercel GitHub app is not installed, record it as a manual follow-up; the CLI deploy in Task 9 still works.

---

### Task 7: Bootstrap the VPS and issue the shared-edge certificate

**Files:**
- Host only: `/opt/talot-assessment/deploy/.env`
- Host only: `/opt/type-by-voice/deploy/docker-compose.override.yml`
- Host only: `/opt/type-by-voice/deploy/nginx/conf.d/talot-api.conf`

**Interfaces:**
- Produces: external network `talot-edge`.
- Produces: certificates at `/etc/letsencrypt/live/talot-api.nate-ng.com/` in the shared `certbot-certs` volume.
- Produces: a CI deploy key and GitHub repository secrets.

- [ ] **Step 1: Generate the CI key and install its public half**

```bash
keydir="$(mktemp -d)"
ssh-keygen -t ed25519 -f "$keydir/talot-ci" -N '' -C talot-ci
SSHPASS="$VPS_PASSWORD" sshpass -e ssh-copy-id \
  -o StrictHostKeyChecking=accept-new \
  -o PreferredAuthentications=password \
  -o PubkeyAuthentication=no \
  -i "$keydir/talot-ci.pub" root@116.118.9.222
```

Expected: `ssh -i "$keydir/talot-ci" root@116.118.9.222 'echo ok'` prints `ok`.
Keep the private key in the temporary directory only.

- [ ] **Step 2: Create a host GitHub deploy key and clone the repository**

Generate a host key, print its public half, add it as a read-only GitHub deploy key, configure a `github-talot` SSH alias, and clone to `/opt/talot-assessment`.

Use `gh repo deploy-key add` with `--allow-read` and `--title talot-vps`.
The host SSH config entry is:

```text
Host github-talot
  HostName github.com
  User git
  IdentityFile /root/.ssh/talot_deploy
  IdentitiesOnly yes
```

Expected: `/opt/talot-assessment/.git` exists.

- [ ] **Step 3: Write the host `.env`**

Generate `POSTGRES_PASSWORD` with `openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 32`, `JWT_SECRET` with `openssl rand -hex 32`, and `SEED_HR_PASSWORD` with `openssl rand -base64 18`.
Write `deploy/.env` from `deploy/.env.example`, set `IMAGE_TAG=latest`, use the actual Vercel URLs from Task 6, and set `DEEPSEEK_API_KEY` when the user provides it.
Set `CERTBOT_EMAIL=nv.nhat8002@gmail.com` and `DOMAIN=talot-api.nate-ng.com`.
Run `chmod 600 .env`.
Record the generated HR password for the handoff.

- [ ] **Step 4: Verify DNS**

The user adds `A talot-api.nate-ng.com -> 116.118.9.222` with proxy off.
Run `dig +short talot-api.nate-ng.com`.
Expected: `116.118.9.222`.

- [ ] **Step 5: Run the edge bootstrap**

```bash
SSHPASS="$VPS_PASSWORD" sshpass -e ssh \
  -o PreferredAuthentications=password \
  -o PubkeyAuthentication=no \
  root@116.118.9.222 \
  'cd /opt/talot-assessment && git pull --ff-only && cd deploy && chmod +x scripts/*.sh && ./scripts/edge-init.sh'
```

Expected: certbot reports `Successfully received certificate` for `talot-api.nate-ng.com`.
A non-zero exit after certificate issuance is acceptable if nginx cannot validate the upstream before the API stack exists.

- [ ] **Step 6: Verify the certificate and the existing service**

```bash
SSHPASS="$VPS_PASSWORD" sshpass -e ssh \
  -o PreferredAuthentications=password \
  -o PubkeyAuthentication=no \
  root@116.118.9.222 \
  'docker exec type-by-voice-nginx-1 ls /etc/letsencrypt/live/talot-api.nate-ng.com && curl -fsS https://tbv-api.nate-ng.com/health'
```

Expected: certificate files exist and `tbv-api` still returns `{"status":"ok"}`.

- [ ] **Step 7: Set GitHub secrets and variable**

```bash
gh secret set VPS_HOST --body '116.118.9.222' --repo nhat8002nguyen/talot-assessment
gh secret set VPS_USER --body 'root' --repo nhat8002nguyen/talot-assessment
gh secret set VPS_SSH_PORT --body '22' --repo nhat8002nguyen/talot-assessment
gh secret set VPS_SSH_KEY < "$keydir/talot-ci" --repo nhat8002nguyen/talot-assessment
gh variable set GHCR_OWNER --body 'nhat8002nguyen' --repo nhat8002nguyen/talot-assessment
```

Expected: `gh secret list` shows all four secrets and `gh variable list` shows `GHCR_OWNER`.

---

### Task 8: Deploy the backend and verify production

**Files:**
- Host `.env` may be updated with the DeepSeek key and final Vercel URLs.

**Interfaces:**
- Consumes: Tasks 4, 5, and 7.
- Produces: `https://talot-api.nate-ng.com/health` returning `{"status":"ok"}`.
- Produces: imported data pack with 30 text jobs and 5 audio answers.

- [ ] **Step 1: Push to trigger CI**

```bash
git push origin main
gh run list --workflow deploy-backend.yml --limit 1
```

Expected: the workflow is queued or running.

- [ ] **Step 2: Watch the first deploy**

```bash
gh run watch --workflow deploy-backend.yml
```

Expected: test, build, push, and SSH deploy are green.
If the deploy fails, read the failing step and fix the artifact or host setting before retrying.

- [ ] **Step 3: Verify both APIs**

```bash
curl -fsS https://talot-api.nate-ng.com/health
curl -fsS https://tbv-api.nate-ng.com/health
```

Expected: both return `{"status":"ok"}`.
If the first fails with TLS or 502, inspect `docker compose -f /opt/talot-assessment/deploy/docker-compose.yml ps` and `docker exec type-by-voice-nginx-1 nginx -t`.

- [ ] **Step 4: Verify GHCR pull access**

If the deploy failed pulling the image, run `docker pull ghcr.io/nhat8002nguyen/talot-api:latest` on the host.
If it fails, make the package public or run `ghcr-login.sh` with a fresh `read:packages` token.

- [ ] **Step 5: Set the DeepSeek key and redeploy**

Update `DEEPSEEK_API_KEY` in the host `.env` and run `./scripts/deploy.sh` from `/opt/talot-assessment/deploy`.

- [ ] **Step 6: Run the production integration smoke**

```bash
(cd apps/backend && uv run python ../../scripts/smoke_integration.py \
  --api-url https://talot-api.nate-ng.com \
  --candidate-origin https://talot-candidate-web.vercel.app \
  --pack ../../intial-resources/business-systems-pack.zip \
  --audio ../../intial-resources/business-systems-pack/answers/A031.m4a \
  --timeout 600)
```

Expected: import summary, both answer statuses, and exit 0.

- [ ] **Step 7: Verify the 25 MB edge limit**

Create a 3 MB file with `dd if=/dev/zero of=/private/var/folders/26/x_2dj2111lq4y0wj9gpjbmfr0000gn/T/smoke-3m.m4a bs=1m count=3`.
Submit it through `https://talot-api.nate-ng.com/candidate/interview/answers/<q2>/audio` with a fresh candidate token and `-F file=@...`.
Expected: `201`, proving the edge accepts more than the old 2 MB limit.

- [ ] **Step 8: Verify scoring and audio states**

Sign in to the production API and inspect `/hr/scoring-jobs`.
Expected: text jobs move from `queued` to `scored`, audio jobs are `needs_a_person`, and no text job is `failed` when the DeepSeek key is valid.

- [ ] **Step 9: Verify CORS from both production origins**

For each of `https://talot-candidate-web.vercel.app` and `https://talot-hr-web.vercel.app`, send OPTIONS to `/candidate/interview` with `Access-Control-Request-Headers: x-candidate-token`.
Expected: the response echoes the matching `Access-Control-Allow-Origin`.

---

### Task 9: Deploy both Vercel apps and verify the browser flows

**Files:**
- Optionally modify: `README.md` with live URLs.

**Interfaces:**
- Consumes: Tasks 6 and 8.
- Produces: live candidate and HR URLs that call `https://talot-api.nate-ng.com`.

- [ ] **Step 1: Deploy candidate-web**

```bash
export VERCEL_TOKEN='<provided token>'
(cd apps/candidate-web && vercel --prod --yes \
  --build-env NEXT_PUBLIC_API_URL=https://talot-api.nate-ng.com \
  --token "$VERCEL_TOKEN")
```

Expected: a production URL is printed and matches the candidate CORS origin.

- [ ] **Step 2: Deploy hr-web**

```bash
(cd apps/hr-web && vercel --prod --yes \
  --build-env NEXT_PUBLIC_API_URL=https://talot-api.nate-ng.com \
  --token "$VERCEL_TOKEN")
```

Expected: a production URL is printed and matches the HR CORS origin.

- [ ] **Step 3: Verify both deployments respond**

```bash
curl -fsS -o /dev/null -w '%{http_code}\n' https://talot-candidate-web.vercel.app/
curl -fsS -o /dev/null -w '%{http_code}\n' https://talot-hr-web.vercel.app/sign-in
```

Expected: `200` for both.
Use the actual team-scoped URLs if Vercel assigned them.

- [ ] **Step 4: Verify the candidate browser flow**

Open a fresh interview link and check:

1. Question 1 of 6 renders.
2. A text answer submits and the confirmation appears.
3. Continue moves to Question 2.
4. Reload restores Question 2.
5. The network panel shows `https://talot-api.nate-ng.com` returning 200.
6. An audio upload succeeds.

- [ ] **Step 5: Verify the HR browser flow**

Sign in at the HR production URL and check:

1. The five roles list.
2. A role shows candidates and answer progress.
3. A text answer shows the suggested score and reasoning.
4. Override with a reason updates the final score.
5. Scoring jobs show `scored` and `needs_a_person`, and failed jobs offer retry.
6. The import page accepts the pack zip and reports the summary.
7. No browser console errors.

- [ ] **Step 6: Verify Git auto-deploy if connected**

Push a no-op docs change and confirm both Vercel projects start deployments.
If the GitHub app is not installed, record it as a manual follow-up.

- [ ] **Step 7: Record the live URLs and commit**

Add a short "Live" section to `README.md` if the user wants the URLs in the repo.

```bash
git add README.md
git commit -m "docs: record production URLs"
git push origin main
```

---

### Task 10: Final verification and handoff

- [ ] **Step 1: Run the full local verification**

```bash
(cd apps/backend && uv sync --all-packages --group dev)
(cd apps/backend && uv run ruff check .)
(cd apps/backend && uv run mypy libs src)
(cd apps/backend && uv run pytest -q)
(cd apps/candidate-web && npm test && npm run lint && npm run typecheck && npm run build)
(cd apps/hr-web && npm test && npx tsc --noEmit && npm run build)
docker compose config --quiet
./scripts/smoke-local.sh
```

Expected: every command exits 0.

- [ ] **Step 2: Run the production verification**

```bash
curl -fsS https://talot-api.nate-ng.com/health
curl -fsS https://tbv-api.nate-ng.com/health
(cd apps/backend && uv run python ../../scripts/smoke_integration.py \
  --api-url https://talot-api.nate-ng.com \
  --candidate-origin https://talot-candidate-web.vercel.app \
  --pack ../../intial-resources/business-systems-pack.zip \
  --audio ../../intial-resources/business-systems-pack/answers/A031.m4a \
  --timeout 600)
```

Expected: both health checks pass and the smoke exits 0.

- [ ] **Step 3: Confirm the repository is clean**

```bash
git status --short
git log --oneline -8
```

Expected: no uncommitted files and the deployment commits are on `main`.

- [ ] **Step 4: Hand off**

Report:

- Local URLs and the local health check.
- Production API health URL.
- Candidate and HR production URLs.
- HR email and the generated password.
- The running image tag.
- The location of `deploy/.env` and that it is not committed.
- That `DEEPSEEK_API_KEY` is set and text answers reach `scored`.
- Any manual item, such as installing the Vercel GitHub app.
- A security reminder to rotate the Vercel token and the VPS root password after handoff.
