# Talotrace HR Web

The HR area for the Talotrace interview-scoring app.
HR signs in, browses candidates per role, sees each answer with the LLM's suggested score and reasoning, overrides scores with a required reason, watches scoring jobs, retries failures, imports the data pack, and creates candidates.

## Prerequisites

- Node.js 20.9+
- A running Talotrace API (`apps/api`, FastAPI) backed by PostgreSQL, per the accepted API contract.
- The data pack imported, or available to import through the UI.

## Configuration

Copy the example env file and point it at the API:

```bash
cp .env.example .env.local
# NEXT_PUBLIC_API_URL=http://localhost:3000
```

`NEXT_PUBLIC_API_URL` is read by the server-side route handlers.
Tokens never reach browser JavaScript; the app holds them in httpOnly cookies.

## Setup

```bash
npm install
```

## Run

```bash
npm run dev
```

Open http://localhost:3002 and sign in with the seeded HR account.

## Test

Unit and component tests:

```bash
npm test
```

End-to-end tests, which require the running API and a seeded data pack:

```bash
npx playwright install
npx playwright test
```

Optional E2E environment variables: `E2E_HR_EMAIL`, `E2E_HR_PASSWORD`, `E2E_PACK_ZIP`, `NEXT_PUBLIC_API_URL`.

## Architecture

- Next.js 16 App Router, TypeScript, Tailwind CSS v4.
- Backend-for-frontend: the browser only talks to same-origin `/api/*` route handlers.
- The route handlers read the `hr_access` cookie, attach it as a Bearer token, and call the FastAPI API.
- On `401` they rotate the refresh token once (single-flight) and retry.
- Pages are client components that fetch `/api/*` and render loading, empty, and error states.
- Pages: `/sign-in`, `/roles`, `/roles/[roleId]`, `/candidates/[candidateId]`, `/candidates/new`, `/answers/[answerId]`, `/scoring-jobs`, `/import`.

## Not built (phase 2)

Score-agreement reporting, audio transcription, a curated "needs a person" list, candidate ordering, and a deployed demo.
