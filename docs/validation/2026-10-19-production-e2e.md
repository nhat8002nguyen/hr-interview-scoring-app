# Production end-to-end validation

**Date:** 2026-10-19
**Commit:** `2d77264` (`fix: honor pinned deploy tag and serialize deploys`)
**API image:** `ghcr.io/nhat8002nguyen/talot-api:2d7726465e43c8c1b8911a6645281cd3e369f98b`
**CI run:** https://github.com/nhat8002nguyen/talot-assessment/actions/runs/39188535569

## Environment

| Component | URL | Result |
|---|---|---|
| Candidate app | `https://talot-candidate-web.vercel.app` | HTTP 200 |
| HR app | `https://talot-hr-web.vercel.app/sign-in` | HTTP 200 |
| API | `https://talot-api.nate-ng.com/health` | `{"status":"ok"}` |
| Existing template API | `https://tbv-api.nate-ng.com/health` | `{"status":"ok"}` |

## API and data checks

- HR sign-in with the seeded account succeeds.
- CORS preflight from both production origins returns the matching
  `Access-Control-Allow-Origin` for `X-Candidate-Token`.
- Data-pack import returned 35 imported answers, 30 queued text jobs, and 5
  audio answers needing a person.
- Current scoring jobs: 41 total, 32 `scored`, 9 `needs_a_person`, 0 `failed`.
- A 3 MB audio upload through the production edge returned 201, confirming
  `client_max_body_size 25m`.
- Text answers reach `scored` with a real DeepSeek score.
- Audio answers remain `needs_a_person` in phase 1.

## Browser checks

Candidate flow, against the production Vercel app:

1. Question 1 of 6 renders.
2. Text answer submits and the confirmation appears.
3. Continue advances to Question 2.
4. Reload restores Question 2.
5. Audio upload submits and the confirmation appears.

HR flow, against the production Vercel app:

1. Sign-in and roles list work.
2. A role shows candidates and answer progress.
3. An answer shows the suggested score and reasoning.
4. Override with a reason updates the final score.
5. Scoring jobs show `scored` and `needs_a_person`.
6. The import page accepts the pack and reports an idempotent summary.
7. No browser console errors appeared.

## Local validation

- Backend: 126 tests passed, ruff clean, mypy clean.
- Candidate web: 31 tests passed, lint and typecheck clean, production build succeeds.
- HR web: 27 tests passed, typecheck clean, production build succeeds.
- Local Compose: five services, clean cold start, `scripts/smoke-local.sh` passes.
- Playwright: HR 4/4, candidate 3/3.

## Operational notes

- Production contains test candidates created by the validation runs
  (`Deployment Smoke`, `Edge Limit Smoke`, `Browser Smoke`) and one override
  on a data-pack candidate.
  The imported pack is otherwise intact.
- The GitHub Actions backend deploy is serialized with a concurrency group
  (`deploy-backend`).
- Deploy downtime, Vercel Git root-directory follow-ups, and credential
  rotation are owned by [`deploy/README.md`](../../deploy/README.md).
