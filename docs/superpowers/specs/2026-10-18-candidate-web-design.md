# Talotrace Candidate Web - Design Spec

**Date:** 2026-10-18
**Status:** Draft
**App:** `talot-candidate-web` (Next.js 16 App Router)
**Depends on:** `docs/superpowers/specs/2026-10-18-api-contract-design.md` (Accepted)
**Sibling specs:** Frontend - HR area, Backend service

## 1. Goal

Define the design of the candidate-facing web app, one of the three downstream specs the API contract calls for.

This app is the unauthenticated area where a candidate opens a personal, unguessable interview link, answers six questions one at a time, and receives an immediate "answer arrived" confirmation.
It consumes only the three `/candidate/*` endpoints and never shows scores, grading guides, other candidates, or HR data.

## 2. Scope

### 2.1 Phase 1 (in scope)

- Open the interview from the personal link `/interview/{session_token}`.
- Walk the candidate through six questions one at a time (linear wizard).
- Answer each question as either typed text or an audio file upload (a Type / Upload audio toggle).
- Receive an immediate "answer received" confirmation after submit.
- Reload the page and resume at the same question.
- Show progress (`Question n of 6`).
- Handle an invalid link (unknown/expired token) with a clear screen.

### 2.2 Phase 2 (out of scope)

- Consent screen and microphone check.
- Transcribe or score audio answers (audio is uploaded and stored only in phase 1).
- Polished candidate-facing error messages and retry flow.
- Deployed demo.

## 3. System Context

The candidate-web app is a standalone Next.js 16 app deployed independently from the HR app and the API.
It talks to the FastAPI monolith (`apps/api`) over JSON HTTP.

```text
  candidate link  ---> +--------------------------+
  /interview/{token}   | talot-candidate-web       |--\
  (unauthenticated)    | Next.js 16 App Router     |   \  X-Candidate-Token
                       +---------------------------+    \      |
                                                         +-----v-----------+
                                                         | FastAPI monolith |
                                                         | /candidate/*    |
                                                         +-----------------+
```

- The token lives in the URL (so the link is shareable/pasteable) and is extracted from the route.
- The token travels to the API in the `X-Candidate-Token` header, keeping it out of API server access logs (per API contract §5.2).
- No server-side proxy or BFF in phase 1: the client calls the API directly.

## 4. Locked Decisions

| Topic | Decision |
|---|---|
| Framework | Next.js 16 App Router, TypeScript (strict), Tailwind CSS v4. |
| Auth model | No credentials. Token extracted from `/interview/[token]` route and sent as `X-Candidate-Token` on every API call. |
| API calls | Direct client-side fetch against `NEXT_PUBLIC_API_ORIGIN` (no BFF). |
| Input per question | Type / Upload audio toggle; one answer per question (text XOR audio). |
| Navigation | Linear wizard, one question at a time, with Previous / Next and a progress indicator. |
| Resume | Exact question persisted to `localStorage` keyed by token; restore on load (see §7). |
| Score visibility | The app never requests or renders scores, grading guides, or any HR data. |
| Error format | RFC 7807 problem details parsed into a typed `ApiError`. |
| Shared types | Hand-written TypeScript types in `lib/types.ts` (no codegen; `libs/contracts` is optional). |

## 5. Routing & Pages

```text
app/
├── layout.tsx                  # root layout, metadata, global styles
├── page.tsx                    # fallback: "Open the interview link you were sent"
├── globals.css
├── not-found.tsx               # default 404
└── interview/
    └── [token]/
        └── page.tsx            # the only functional page
```

- `app/interview/[token]/page.tsx` is a server component that reads `params.token` (a Promise in Next 16) and renders the client `<InterviewFlow token={token} />`.
- There is no candidate "home" or "sign-in" page. Candidates always arrive via the link.
- The root `app/page.tsx` is a minimal fallback for anyone who lands without a token.

## 6. API Client

`lib/api.ts` plus `lib/types.ts` isolate all HTTP and typing from the UI.

`lib/types.ts` mirrors the contract (§7.2): `Candidate`, `Question`, `Answer`, `InterviewResponse`, `Progress`, `SubmitResponse`, and `ProblemDetails`.

`lib/api.ts` exposes three functions:

| Function | HTTP call |
|---|---|
| `getInterview(token)` | `GET /candidate/interview` |
| `submitTextAnswer(token, questionId, text)` | `POST /candidate/interview/answers/{question_id}` |
| `submitAudioAnswer(token, questionId, file)` | `POST /candidate/interview/answers/{question_id}/audio` |

Behavior:

- Every call sets the `X-Candidate-Token` header and uses `NEXT_PUBLIC_API_ORIGIN` as the base.
- Text submits send JSON `{ answer_type: "text", text }`.
- Audio submits send `multipart/form-data` with a `file` field (built from a `File` object).
- Non-2xx responses are parsed into a typed `ApiError` carrying `status` and the RFC 7807 `detail`.
- All functions return typed success values; callers never inspect raw `fetch` responses.

## 7. State & Resume Semantics

The wizard is a single client component (`InterviewFlow`) with local state.

Top-level status: `loading -> invalid-link | ready | complete`.
Per-question submit: `idle -> submitting -> received | error`.

State held:

- `interview: InterviewResponse | null`
- `currentIndex: number` (0..5)
- `draft: { mode: "text" | "audio"; text: string; file: File | null }`
- `submit: "idle" | "submitting" | "received" | "error"`
- `fatalError: string | null`

### 7.1 Resume

The candidate must reload and come back to the same question. The API does not track a candidate's viewing position (it only stores which questions are answered), so the app persists it client-side:

1. On every navigation (Previous / Next / after submit), write `currentIndex` to `localStorage` under a key derived from the token, e.g. `talotrace:interview:{token}:currentQuestion`. Keying by token prevents cross-candidate bleed on a shared device.
2. On load, after `getInterview(token)` succeeds:
   - If a stored index is a valid `0..5`, resume at that question.
   - Otherwise default to the first unanswered question (`answer === null`), or Q1 when none are answered.
3. The completion screen is shown after submitting the last question, or on load when all six are answered and there is no stored position.

`localStorage` (not `sessionStorage`) is used so an accidental close or a browser reopen also lands on the same question.

### 7.2 Refresh after submit

After a successful submit, the app re-fetches `getInterview(token)` to refresh `progress` and the question's `answer` (version and `submitted_at`), then advances.
Re-fetching keeps the app consistent with the server after resubmission without mirroring the backend's upsert/versioning logic client-side.

## 8. Components & Data Flow

```text
components/
├── interview/
│   ├── interview-flow.tsx    # client: fetch, state machine, error screens
│   ├── question-card.tsx     # prompt + "Question n of 6" + input
│   ├── answer-input.tsx      # Type / Upload audio toggle, textarea, file input
│   ├── progress.tsx          # progress bar / dots
│   ├── confirmation.tsx      # "answer received" (notes `unchanged`)
│   ├── invalid-link.tsx      # 401 screen
│   ├── completion.tsx        # all six answered
│   └── loading.tsx
└── ui/                       # minimal primitives: Button, Textarea, SegmentedControl
```

Submit flow:

1. Candidate types text (or selects an audio file) and clicks "Submit answer".
2. `answer-input` calls the appropriate `api.ts` function with the token.
3. On `201`/`200` the app shows `confirmation.tsx` ("Your answer has been received").
   When the response has `unchanged: true`, a subtle note indicates the submission matched the existing answer.
4. The app re-fetches the interview, then advances to the next question (or shows `completion.tsx` after Q6).

The textarea submit is disabled while the text is empty/whitespace as a first guard; the audio input requires a selected file before submit.

## 9. Error Handling (phase-1 minimal)

| Condition | Behavior |
|---|---|
| `401` (unknown/expired token) | `invalid-link.tsx` full screen: "This interview link is not valid." No retry. |
| `404` (unknown question) | Generic failure message (should not occur with valid data). |
| `422` (empty text / invalid file) | Inline message on the question; client-side guards prevent the common cases. |
| Network / 5xx | Generic inline failure on the question. |

The richer candidate-facing error messaging and retry flow is phase 2 (API contract §2.2).
The `401` invalid-link screen and basic inline errors are kept in phase 1 for correctness.

## 10. Configuration & Environment

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_ORIGIN` | FastAPI base URL (must be `NEXT_PUBLIC_` for client-side use). |

Note for the backend/ops: the API's `CORS_ORIGINS` must include this app's origin so browser requests from the candidate area succeed.

## 11. Testing & Verification

- **Unit** (`lib/api.ts`, mocked `fetch`): header injection on every call, RFC 7807 error parsing, and `multipart/form-data` construction for audio.
- **Component** (`InterviewFlow` with mocked `fetch`): happy path, resume (stored index vs first-unanswered), text submit, audio submit, `401` invalid-link, and submit error.
- **End-to-end (Playwright, against the real API in docker-compose):** open the link, answer a question, see the confirmation, reload and verify the same question is restored, resubmit, and confirm the duplicate submission does not create a new score.
- Tooling: ESLint + Prettier, Vitest + React Testing Library, Playwright.

## 12. "What Must Be True" Traceability

| Requirement | Design guarantee |
|---|---|
| Candidate cannot see scores / grading guides / other candidates / HR data | App calls only the three `/candidate/*` endpoints; `lib/types.ts` does not model scoring fields; no HR routes are referenced. |
| Token stays out of API server logs | Token travels only in the `X-Candidate-Token` header (§6). |
| Reload resumes at the same question | `currentIndex` persisted to `localStorage` keyed by token and restored on load (§7.1). |
| Same answer twice does not create two scores | The app only forwards submits; idempotency is enforced server-side by `content_hash` (API contract §6.4). The app surfaces `unchanged` in the confirmation. |
| Immediate "answer arrived" confirmation | `confirmation.tsx` shown synchronously after `201`/`200`. |
| Text and audio are both supported in phase 1 | Type / Upload audio toggle dispatches to the correct endpoint (§8). |

## 13. Project Structure

```text
talot-candidate-web/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   ├── not-found.tsx
│   └── interview/[token]/page.tsx
├── components/
│   ├── interview/
│   └── ui/
├── lib/
│   ├── api.ts
│   └── types.ts
├── tests/              # Vitest + React Testing Library
├── e2e/                # Playwright
├── next.config.ts
├── tsconfig.json
├── package.json
└── .env.example        # NEXT_PUBLIC_API_ORIGIN
```
