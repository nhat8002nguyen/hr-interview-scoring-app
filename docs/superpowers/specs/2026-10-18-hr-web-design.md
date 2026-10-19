# Talotrace Interview Scoring - HR Web App Design

**Date:** 2026-10-18
**Status:** Accepted
**Repo:** `talot-assessment` monorepo, branch `spec/hr-web`
**Frontend:** Next.js 16 (App Router), TypeScript, Tailwind CSS v4
**Consumes:** `apps/api` (FastAPI monolith) per the accepted API contract
**Auth model:** BFF proxy, tokens held in httpOnly cookies, never in browser JS

> **Amended by `2026-10-19-hr-self-registration-and-tenancy-design.md`.**
> That spec adds HR self-registration and per-account tenancy and is authoritative where it changes this document.

## 1. Goal

Define the design of the HR area frontend, the second of the three implementation specs listed in the API contract.
This document is the single source of truth for building `apps/hr-web`.

The HR area is the decision-making surface.
It lets an HR account sign in, browse candidates per role, see each answer with its suggested score and reasoning, override a score with a required reason, watch scoring-job status, retry failed jobs, import the data pack, and create new candidates to generate interview links.

This spec consumes the accepted API contract (`2026-10-18-api-contract-design.md`) and does not redefine any backend behavior.
Endpoint paths, request/response shapes, status codes, and the scoring status model are all fixed there.

## 2. Scope

### 2.1 Phase 1 (in scope)

- JWT sign-in (against the seeded HR account or any self-registered account) with a real sign-in form, plus self-service sign-up.
- Browse roles, candidates per role, and answers with suggested score, final score, and reasoning.
- Override a score with a required reason.
- View scoring-job status across all four statuses, and retry failed jobs.
- Import the data-pack zip and show the returned summary.
- Create a candidate and display the generated interview link.
- Play back audio answers.

### 2.2 Phase 2 (out of scope, optional extras)

- Score-agreement report vs `hr_reference_scores.csv`.
- Transcribe and score the audio-only answers.
- A dedicated "needs a person" list (the status is shown in the job list, but no curated list).
- Candidate list ordered to help HR decide who to read first.
- Consent screen and microphone check (candidate area only, not HR).
- Deployed demo.

## 3. System Context

```text
                       +----------------------+
  HR browser  <------> | apps/hr-web          |  httpOnly cookies: hr_access, hr_refresh
  (same-origin)        | Next.js 16           |
                       | route handlers (BFF) |--\
                       +----------------------+   \  Authorization: Bearer <hr_access>
                                                   |
                                                   +-----v-----------+
                                                   | apps/api        |
                                                   | FastAPI monolith|
                                                   | PostgreSQL 18   |
                                                   | scoring workers |
                                                   +-----------------+
```

- The HR browser only ever talks to `apps/hr-web` on its own origin.
- The JWT access token and refresh token never reach browser JavaScript.
- `apps/hr-web` route handlers read the access cookie, attach it as a Bearer token, and call the FastAPI monolith.
- The FastAPI base URL is provided via `NEXT_PUBLIC_API_URL` and read only by the server-side route handlers.

## 4. Locked Decisions

| Topic | Decision |
|---|---|
| Framework | Next.js 16 App Router, TypeScript, Tailwind CSS v4. |
| Auth model | BFF proxy. Both tokens live in httpOnly cookies set by `apps/hr-web`. Browser JS never reads them. |
| Data access | All FastAPI calls happen server-side in route handlers. Pages fetch same-origin `/api/*` route handlers. |
| Mutations | Route handlers (POST/PATCH). Forms validate with `zod` before the handler calls FastAPI. |
| Token refresh | On FastAPI `401`, the route-handler layer rotates via `POST /auth/refresh-tokens`, writes updated cookies, and retries once. |
| Refresh concurrency | Single-flight: concurrent requests that hit `401` share one rotation, so the single-use refresh token is consumed exactly once. |
| Styling | Tailwind CSS v4 plus a few hand-rolled primitives (Card, Badge, Button, Textarea, Select). No heavy UI library. Light-only: `:root` declares `color-scheme: light` with `--background: #ffffff` and `--foreground: #171717`; no `prefers-color-scheme: dark` palette, `dark:` variants, or theme toggle. |
| State management | None beyond React local state. Server route handlers are the source of truth; the client reflects their responses. |
| Types | TypeScript types for every contract response, defined in `lib/contracts` and kept in lock-step with the API contract. |
| Audio | Streamed through a route handler (`/api/hr/answers/[answerId]/audio`) so auth rides the same-origin cookie and the bearer token is not needed in an `<audio>` tag. |
| Error handling | RFC 7807 problem details from the API are mapped to typed client errors and surfaced inline. |

## 5. Authentication & Session

### 5.1 Cookies

| Cookie | Content | Attributes |
|---|---|---|
| `hr_access` | JWT access token (TTL 1h) | HttpOnly; Secure in production; SameSite=Lax; Path=/ |
| `hr_refresh` | Refresh token (single-use rotation) | HttpOnly; Secure in production; SameSite=Lax; Path=/ |

Both cookies are set and cleared only by `apps/hr-web` route handlers.
They are never written by the browser, never placed in localStorage or sessionStorage, and never read by client-side JavaScript.

### 5.2 Flows

- **Sign in:** `POST /api/auth/sign-in` calls FastAPI `POST /auth/sign-in`, then sets both cookies and returns the `user` object.
  The sign-in page links to the sign-up page.
- **Sign up:** `POST /api/auth/sign-up` calls FastAPI `POST /auth/sign-up`, then sets both cookies and returns the `user` object.
- **Sign out:** `POST /api/auth/sign-out` calls FastAPI `POST /auth/sign-out` with the refresh token, then clears both cookies.
- **Refresh:** when a route handler receives `401` from FastAPI, it reads `hr_refresh`, calls `POST /auth/refresh-tokens`, and rewrites both cookies.
  The retry uses the new access token.
- **Guard:** `proxy.ts` checks for the presence of the session cookies on protected routes and redirects unauthenticated visitors to `/sign-in`.
  `/sign-in` and `/sign-up` are public; all other pages are behind the guard.
  The middleware performs no network I/O and no token validation; it is a UX guard, not a security boundary.

The security boundary is the API: every `/hr/*` call carries a valid Bearer JWT or fails with `401`/`403`.
The browser's inability to read the tokens means a successful XSS cannot exfiltrate the session.

## 6. Routes (Pages)

| URL | Purpose |
|---|---|
| `/sign-in` | Email and password form. Links to `/sign-up`. |
| `/sign-up` | Email and password form to create an HR account. |
| `/` | Redirects to `/roles`. |
| `/roles` | Role list with candidate counts. |
| `/roles/[roleId]` | Candidates for a role: name, answer progress, per-answer scoring badge. |
| `/candidates/[candidateId]` | Candidate detail: full scoring per answer, `interview_link` with copy button. |
| `/answers/[answerId]` | One answer: prompt, transcript or audio player, grading guide, suggested score and reasoning, override form. |
| `/scoring-jobs` | Job list with status filter and retry on failed jobs. |
| `/import` | Data-pack zip upload and summary. |
| `/candidates/new` | Create candidate and show the generated `interview_link`. |

All pages other than `/sign-in` and `/sign-up` are behind the session guard.

All list and detail screens are unchanged in shape; their data is scoped to the signed-in HR account by the API.
A signed-in HR account sees only its own candidates, answers, scoring jobs, and candidate counts.

## 7. Route Handlers (BFF surface)

The following same-origin handlers mirror the API contract one to one.
Each handler reads cookies, calls FastAPI, and returns the typed JSON (or streamed bytes for audio).

| Handler | FastAPI target | Notes |
|---|---|---|
| `POST /api/auth/sign-in` | `POST /auth/sign-in` | Sets cookies. |
| `POST /api/auth/sign-up` | `POST /auth/sign-up` | Sets cookies; maps `409`/`422` to inline errors. |
| `POST /api/auth/sign-out` | `POST /auth/sign-out` | Clears cookies. |
| `GET /api/hr/roles` | `GET /hr/roles` | |
| `GET /api/hr/roles/[roleId]/candidates` | `GET /hr/roles/{role_id}/candidates` | |
| `GET /api/hr/candidates/[candidateId]` | `GET /hr/candidates/{candidate_id}` | |
| `POST /api/hr/candidates` | `POST /hr/candidates` | Validates with zod first. |
| `GET /api/hr/answers/[answerId]` | `GET /hr/answers/{answer_id}` | |
| `GET /api/hr/answers/[answerId]/audio` | `GET /hr/answers/{answer_id}/audio` | Streams bytes with the audio content type. |
| `PATCH /api/hr/answers/[answerId]/score` | `PATCH /hr/answers/{answer_id}/score` | Validates with zod first. |
| `GET /api/hr/scoring-jobs` | `GET /hr/scoring-jobs` | Forwards `?status=`. |
| `POST /api/hr/scoring-jobs/[jobId]/retry` | `POST /hr/scoring-jobs/{job_id}/retry` | |
| `POST /api/hr/import` | `POST /hr/import` | Forwards the multipart file. |

Refresh has no public route.
It is an internal step in the route-handler wrapper.

## 8. API Client Layer

A single server-side module (`lib/api/server.ts`) owns all FastAPI interaction.

- `request<T>(method, path, body?)` reads `hr_access`, calls `{NEXT_PUBLIC_API_URL}{path}` with `Authorization: Bearer`, and parses the response.
- On `401`, it performs a single-flight refresh (section 5.2), rewrites cookies, and retries once.
- On any other error, it throws a typed `ApiError` carrying the RFC 7807 `status` and `detail`.
- Every route handler delegates to this module; no route handler makes a raw `fetch` of its own.

Client components use a thin typed helper (`lib/api/client.ts`) that calls the same-origin `/api/*` handlers.
Types are shared between server and client in `lib/contracts`.

## 9. UI Behaviors

### 9.1 Scoring status

A `ScoringBadge` renders one of four states with distinct styling:

- `queued` - neutral, "waiting".
- `scored` - shows the score.
- `failed` - error styling, shows "failed" and never a score.
- `needs_a_person` - warning styling, "needs a person".

A `failed` job is always rendered as failed, never as a low score.
Its `last_error` and `attempt_count` are shown, with a Retry action.

### 9.2 Override form

On `/answers/[answerId]`, an override form submits `PATCH /api/hr/answers/[answerId]/score` with `final_score` (1-4) and `override_reason` (required non-empty).
Both fields are validated with zod on the client and again server-side.
The form is enabled only when the job status is `scored` or `needs_a_person`.
A `409` or `422` response is surfaced inline.

### 9.3 Resubmission visibility

Each answer shows `version` and `submitted_at` so HR can see which submission counts.
The active answer is the single row the contract guarantees per candidate and question.

### 9.4 Audio playback

`<audio src="/api/hr/answers/[answerId]/audio" controls />`.
The route handler streams the bytes and sets the correct content type.
The browser attaches the session cookie automatically, so the bearer token is not needed in markup.

### 9.5 Import

`/import` uploads the data-pack zip to `POST /api/hr/import` and renders the summary: `roles_created`, `questions_created`, `candidates_created`, `answers_imported`, `scoring_jobs_queued`, `audio_answers_needing_person`.

### 9.6 Create candidate

`/candidates/new` submits `name`, `email`, and `role_id` to `POST /api/hr/candidates` and displays the returned `interview_link` with a copy button.
A `409` duplicate email is shown inline.

### 9.7 Interview link

`/candidates/[candidateId]` shows the `interview_link` from `GET /hr/candidates/{id}` with a copy-to-clipboard action.

## 10. Error Handling

- A global error boundary catches unhandled errors and offers retry.
- `401` from any protected route handler triggers a redirect to `/sign-in`.
- `404` renders a not-found state.
- `409` and `422` are mapped to inline form errors using the problem `detail`.
- `413` (upload too large) and `400` (unreadable import) are shown inline on `/import`.
- Loading and empty states exist on every data view.

## 11. Cross-Cutting Concerns

- **Config (env):** `NEXT_PUBLIC_API_URL` (FastAPI base URL, read server-side). Tokens are never exposed to the browser.
- **CORS:** not required between the HR browser and `apps/hr-web` (same-origin).
  The API's own `CORS_ORIGINS` allow-list is unchanged.
- **Validation:** zod schemas for the sign-up, override, create-candidate, and import forms.
- **Logging:** the HR app does not log tokens.
  Session errors are logged server-side without cookie values.

## 12. Testing

- **Component/unit (Vitest + React Testing Library):** `ScoringBadge` state-to-render mapping, override form validation, sign-up form validation, the sign-in -> sign-up link, "failed never renders a score".
- **Route handler (unit, mocked `lib/api`):** cookie set/clear on sign-in/sign-up/sign-out, single-flight refresh, problem-detail mapping (`409`/`422` on sign-up).
- **End-to-end (Playwright against the real API and a seeded data pack):** sign in, roles to candidates to answer, override with reason, retry a failed job, import the pack and observe the summary, and confirm a duplicate submission yields a single score.
- **Theme regression (Playwright):** `e2e/sign-in-theme.spec.ts` emulates light and dark `prefers-color-scheme` on `/sign-in` and asserts computed body, card, heading, label, and input colors stay light (`rgb(23, 23, 23)` on white) with `color-scheme: light`.
- Mirrors the frontend section of API contract section 13.

## 13. Traceability

| Requirement | Design guarantee |
|---|---|
| HR sign-in or sign-up | Real forms via `POST /api/auth/sign-in` and `POST /api/auth/sign-up`; JWT held in httpOnly cookies. |
| See candidates for a role with scores and reasoning | `/roles/[roleId]` and `/answers/[answerId]` render suggested and final scores plus `suggested_reasoning`. |
| Override requires a reason | zod + server validation of `override_reason`; `409`/`422` surfaced inline. |
| Failed job visible with retry, never shown as a score | `ScoringBadge` failed state plus Retry; no score rendered for `failed`. |
| Tokens never in the browser | BFF proxy with httpOnly cookies; browser JS has no access to either token. |
| HR sees which submission counts | `version` and `submitted_at` shown on every answer. |
| Audio answer visible to HR | `/api/hr/answers/[id]/audio` streams the stored audio. |
| Import the data pack | `/import` uploads the zip and renders the summary counts. |
| Create candidate and generate link | `/candidates/new` posts to `POST /hr/candidates` and shows `interview_link`. |

## 14. Non-Goals (Phase 2)

Everything listed in section 2.2 is out of scope for this spec.
In particular, no audio transcription, no score-agreement report, and no dedicated "needs a person" list beyond the status shown in the job list.
