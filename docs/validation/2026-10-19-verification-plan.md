# Production E2E verification plan

Date: 2026-10-19
Branch: `no-mistakes/production-e2e`

## Local codebase

1. Backend: `uv sync --all-packages --group dev`; `uv run ruff check .`; `uv run mypy libs src`; `uv run pytest -q` (expect 126 passed).
2. Candidate web: `npm test` (expect 31 passed), `npm run lint`, `npm run typecheck`, `npm run build`.
3. HR web: `npm test` (expect 27 passed), `npx tsc --noEmit`, `npm run build`.
4. Local Compose: `docker compose config --quiet`; `./scripts/smoke-local.sh` (expect `local smoke ok`).

## Production

1. `curl -fsS https://talot-api.nate-ng.com/health` returns `{"status":"ok"}`.
2. `curl -fsS https://tbv-api.nate-ng.com/health` returns a healthy status.
3. `curl -fsS -o /dev/null -w '%{http_code}' https://talot-candidate-web.vercel.app/` returns 200.
4. `curl -fsS -o /dev/null -w '%{http_code}' https://talot-hr-web.vercel.app/sign-in` returns 200.
5. CORS preflight on `/candidate/interview` with each Vercel origin returns that origin in `Access-Control-Allow-Origin`.
6. HR sign-in succeeds with the seeded account.
7. `GET /hr/roles` returns 5 roles.
8. `GET /hr/scoring-jobs` shows `scored` and `needs_a_person` jobs and zero `failed` jobs.
9. `scripts/smoke_integration.py` against production imports the pack, submits text and audio, observes `scored` and `needs_a_person`, and exits 0.
10. A 3 MB audio upload through the production edge returns 201.
11. The committed report `docs/validation/2026-10-19-production-e2e.md` matches the observed results.
