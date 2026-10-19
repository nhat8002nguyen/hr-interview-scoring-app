# Talotrace Interview Scoring - HR Self-Registration and Tenancy Design

**Date:** 2026-10-19
**Status:** Accepted
**Repo:** private monorepo
**Amends:** `2026-10-18-api-contract-design.md`, `2026-10-18-backend-design.md`, `2026-10-18-hr-web-design.md`

## 1. Goal

Let any person create their own HR account instead of relying on the single admin-created seeded account.

Each HR account owns its own candidates and therefore its own answers, scoring jobs, and interview links.
HR accounts never share candidate data, even when they share the same role name.

This spec is the authoritative design for the feature.
Where it changes an existing spec, this spec wins and the amended spec points back here.

## 2. Scope

In scope:

- Self-service HR sign-up with email and password, no email verification.
- Per-HR ownership of candidates, answers, and scoring jobs via an `owner_id` on `candidates`.
- Every HR read and write scoped to the caller's own data, with cross-tenant access returning `404`.
- Import and candidate creation tagged with the caller's `owner_id`.
- A migration that backfills legacy data to the seeded HR account and applies per-owner uniqueness.
- Amendments to the API contract, backend design, HR web design, and README.

Out of scope:

- Email verification, password reset, and any email delivery.
- An `admin`/superuser role that can see all tenants' data.
- Per-owner copies of `roles` and `questions` (they stay shared).
- Transferring ownership between HR accounts.

## 3. Locked Decisions

| Topic | Decision |
|---|---|
| Tenancy boundary | `roles` and `questions` are shared, read-only reference data. `candidates`, `answers`, and `scoring_jobs` are owned. |
| Ownership anchor | `owner_id` lives only on `candidates`. Ownership of answers and jobs is resolved by joining through `candidate_id`. |
| Sign-up identity | Email + password only. No username. |
| Email normalization | HR emails are stripped and lowercased in `AuthenticationService` on both sign-up and sign-in before lookup and persist. |
| Sign-up response | `201` with the same `AuthTokensResponse` as sign-in (auto-login). |
| Duplicate email | `409` on both sign-up and create-candidate, now scoped per owner for candidates. Concurrent unique violations map to the same `409` domain errors. |
| Cross-tenant access | `404` for both "not yours" and "does not exist". |
| Seeded account | Stays a normal HR tenant. Legacy data is backfilled to it. Its credentials stay documented in the README. |
| Password reset | Out of scope. Documented as a known limitation. |
| Rate limiting | Lightweight in-process fixed-window limiter on sign-in and sign-up. |
| Imported audio keys | Deterministic per owning candidate: `audio/import/{candidate_id}/{answer_id}.m4a`. |

## 4. Tenancy Model

### 4.1 Shared vs owned

`roles` (the five open roles) and `questions` (the six questions with grading guides) are static reference data every HR needs identically.
They stay global and are shared across all HR accounts.
Import keeps upserting them globally and idempotently.

Everything a candidate produces is owned:

```text
users 1 ---- N candidates 1 ---- N answers 1 ---- 1 scoring_jobs
                | (owner_id)
```

`answers` and `scoring_jobs` are not given their own `owner_id`.
They are always reached through a candidate, so their owner is the candidate's owner.

### 4.2 Why `owner_id` on `candidates` only

Three options were considered:

- `owner_id` on `candidates` only (chosen).
- `owner_id` denormalized onto `candidates`, `answers`, and `scoring_jobs`.
- Postgres Row-Level Security per tenant.

The chosen option is the simplest and most maintainable.
It adds one column and a few indexes, with no denormalization that could drift.
The scoring-jobs list still joins through `answers` and `candidates` for display fields, so denormalizing `owner_id` would save almost nothing.

Row-Level Security was rejected because the app uses a single shared database role and connection pool.
Setting a per-request tenant id would fight the pool and is overkill at this scale.

The cost of the chosen option is that correctness depends on a single scoped-read choke point being used everywhere.
The choke point is the scoped-read methods in section 8.1, every one of which an HR endpoint uses, backed by isolation tests.

## 5. Data Model Changes

### 5.1 `users`

No change.
The `email` unique index stays global.
Sign-up inserts rows with `role = "hr"`.

### 5.2 `candidates`

| Change | Detail |
|---|---|
| Add `owner_id` | `int FK -> users.id`, `NOT NULL`, indexed |
| Add composite index | `(owner_id, role_id)` for the per-owner role listing |
| `email` uniqueness | drop global unique -> composite unique `(owner_id, email)` |
| `external_ref` uniqueness | drop global unique -> composite unique `(owner_id, external_ref)` |
| `session_token` | stays globally unique, so a candidate link resolves regardless of owner |

`email` becomes unique per owner so two HRs can interview the same person without colliding.
`external_ref` becomes unique per owner so import idempotency is per tenant.
`session_token` remains globally unique because it is an unguessable secret, not an ownership key.

### 5.3 `answers` and `scoring_jobs`

No schema change.
Ownership is resolved by joining `answer -> candidate` or `job -> answer -> candidate`.
`scoring_jobs.overridden_by` still records which HR performed an override.

## 6. Migration

A new Alembic revision `20261019_0002_hr_tenancy` (down revision `20261018_0001`) runs these steps in order:

1. `add_column` `candidates.owner_id` (nullable `Integer`, `ForeignKey("users.id")`).
2. Backfill every candidate to the sole existing HR user:

   ```sql
   UPDATE candidates
   SET owner_id = (SELECT id FROM users ORDER BY id LIMIT 1)
   WHERE owner_id IS NULL;
   ```

3. `alter_column` `owner_id` to `NOT NULL`.
4. Drop the global unique index `ix_candidates_email`; create a unique index on `(owner_id, email)`.
5. Drop the global unique index `ix_candidates_external_ref`; create a unique index on `(owner_id, external_ref)`.
6. Create index `ix_candidates_owner_id` on `owner_id`.
7. Create index `ix_candidates_owner_id_role_id` on `(owner_id, role_id)`.

The backfill is safe on both databases:

- On a fresh database there are no candidate rows, so the `UPDATE` is a no-op and `NOT NULL` is trivially satisfied.
- On the existing demo database the only user is the seeded HR account, so all imported candidates become its rows.

The backfill selects the lowest-id user instead of hardcoding an email, so it stays correct even when `SEED_HR_EMAIL` is customized.
A candidate is never transferred between owners after creation, so the backfill never changes meaning.

## 7. Authentication - Self-Service Sign-Up

### 7.1 Endpoint

`POST /auth/sign-up` (public, `AuthType.NONE`).

Request:

```json
{ "email": "newhr@example.com", "password": "..." }
```

Response `201` (same shape as sign-in):

```json
{
  "user": { "id": 2, "email": "newhr@example.com", "role": "hr" },
  "access_token": "<jwt>",
  "refresh_token": "<jwt>"
}
```

- `409` when the email is already registered.
- `422` when the email is malformed or the password is shorter than the configured minimum.

### 7.2 Service

`AuthenticationService` gains a `sign_up(email, password)` method:

1. Normalize the email (strip whitespace, lowercase). `sign_in` uses the same normalization before lookup.
2. Reject a too-short password with `WeakPasswordError` (`422`).
3. Reject the request with `409` if `UserRepository.get_by_email(email)` returns a user.
4. Hash the password with the existing `HashingServiceProtocol`.
5. Add the user with `role = Role.HR`. On a unique-violation `IntegrityError`, roll back and raise `EmailAlreadyExistsError` so a concurrent duplicate still returns `409`.
6. Issue tokens through the existing `_issue_tokens` path, so sign-up reuses sign-in's token rotation exactly.

`EmailAlreadyExistsError` is added to `auth/domain/exceptions.py` and mapped to `409`.
`CandidatesService.create_candidate` maps a unique-violation `IntegrityError` on `(owner_id, email)` to `CandidateAlreadyExistsError` the same way.

### 7.3 Validation and config

- `SignUpBody.email` is a Pydantic `EmailStr` (adds the small `email-validator` dependency).
- `SignUpBody.password` only requires a non-empty value (`min_length=1`).
- The password minimum is enforced in `AuthenticationService`, which takes `min_password_length` wired from `Settings.password_min_length` (default `8`).
  A too-short password raises `WeakPasswordError`, mapped to `422`.
- No composition rules.

## 8. Authorization - Ownership Scoping

### 8.1 The choke point

The caller's id comes from the existing `CurrentUserDep` (`ActiveUserData.sub`).

Ownership is enforced in the scoped-read choke points:

- `CandidatesService.get_owned_candidate(candidate_id, owner_id)` loads the candidate and raises `CandidateNotFoundError` unless `candidate.owner_id == owner_id`.
- `AnswersService.get_owned(answer_id, owner_id)` loads the answer, resolves its candidate, and raises `AnswerNotFoundError` unless the candidate is owned.
- The scoring repository's `get_owned(job_id, owner_id)` is used by `ScoringService.retry` to load a job; a non-owned or missing job raises `ScoringJobNotFoundError`.

Each of these not-found errors is mapped to `404`, so "not yours" and "does not exist" are indistinguishable.

Every HR endpoint threads `owner_id` into its service call.
No HR endpoint reads or mutates a candidate, answer, or job without an ownership check.

### 8.2 Endpoint changes

| Endpoint | Change |
|---|---|
| `GET /hr/roles` | `candidate_count` is computed for the caller only |
| `GET /hr/roles/{role_id}/candidates` | returns only the caller's candidates for that role |
| `GET /hr/candidates/{candidate_id}` | `404` unless owned |
| `POST /hr/candidates` | creates the candidate with `owner_id = caller` |
| `GET /hr/answers/{answer_id}` and `/audio` | `404` unless owned (via candidate) |
| `PATCH /hr/answers/{answer_id}/score` | `404` unless owned; `overridden_by` still records the caller |
| `GET /hr/scoring-jobs` | filters to the caller's jobs |
| `POST /hr/scoring-jobs/{job_id}/retry` | `404` unless owned |
| `POST /hr/import` | roles/questions global; candidates/answers tagged with the caller |

Candidate-facing `/candidate/*` is unchanged.
The session token resolves globally by design.

### 8.3 Service and repository changes

- `Candidate` entity gains `owner_id`.
- `CandidateRepository` methods that read by id, email, external ref, or role now take an `owner_id`.
- `CandidatesService.create_candidate`, `list_candidates_for_role`, and `count_by_role` accept an `owner_id`; `get_owned_candidate(candidate_id, owner_id)` is the ownership choke point for loading a candidate by id.
- `CatalogService.list_roles` and the `RoleCandidateCounter` count candidates per owner.
- `ScoringService.list_jobs` and `retry` accept an `owner_id`.
- `AnswersService` read methods used by HR resolve ownership through the candidate.

## 9. Import Ownership

`ImportService.import_zip` gains an `owner_id` parameter:

- `roles` and `questions` upsert globally and idempotently, exactly as today.
- Candidate find-or-create keys on `(owner_id, external_ref)` instead of global `external_ref`.
- New candidates are created with the caller's `owner_id`.
- Answers attach to the owned candidate.
- Imported audio is stored under `audio/import/{candidate_id}/{answer_id}.m4a`, so two owners importing the same pack never share a blob.

Consequences:

- Re-importing the same pack as the same owner is idempotent (no duplicates), including the same audio key per candidate and answer.
- A different owner importing the same pack gets their own isolated copies (DB rows and audio blobs).

## 10. Security and Robustness

### 10.1 No email verification

Dropping verification is accepted; its costs are documented, not hidden:

- Account enumeration: `POST /auth/sign-up` returns `409` on a duplicate email, which reveals registration state. Accepted for UX; documented as a trade-off.
- No password reset: a forgotten password locks the account out. Documented as a known limitation.

### 10.2 Rate limiting

A lightweight in-process fixed-window limiter guards `POST /auth/sign-in` and `POST /auth/sign-up`.

- Keyed by client IP and, for sign-up, by email.
- Configured via `auth_rate_limit` (requests) and `auth_rate_limit_window_seconds`.
- Counters live in process memory, so limits reset on restart. Acceptable at this scale.

### 10.3 Cross-tenant isolation

Cross-tenant access returns `404` for both "not yours" and "does not exist", so resource existence is never leaked.
The ownership check happens inside the repository/service read path, not only at the router boundary, so a future endpoint defaults to scoped behavior.

## 11. Frontend - HR Web

The HR web app changes in two small ways:

- Add a `/sign-up` page (email + password) that posts to a new `POST /api/auth/sign-up` BFF route handler.
- Add a link from the sign-in page to the sign-up page.

The BFF handler mirrors sign-in: it forwards to FastAPI `POST /auth/sign-up`, sets the two httpOnly cookies from the returned tokens, and returns the user object.
All existing list and detail screens are unchanged in shape; their data is simply scoped to the signed-in HR by the API.

## 12. Testing

Backend:

- Sign-up: `201` creates a user and tokens; `409` on duplicate email; `422` on malformed email or short password.
- Isolation: HR A creates/imports candidates; HR B gets `404` on A's candidate, answer, audio, and scoring job.
- Per-owner counts: `GET /hr/roles` candidate counts reflect only the caller.
- Cross-tenant `404` across every `/hr/*` resource, including retry.
- Import ownership: two HRs import the same pack and get separate candidates; the same HR re-importing is idempotent.
- Migration: legacy candidates backfill to the seeded user; a fresh database has no orphan rows.
- Regression: the scoring worker still claims jobs globally and scores any tenant's queued jobs; the candidate-facing flow is unchanged.

Frontend (hr-web):

- Sign-up form validation and the link from sign-in.
- BFF handler sets cookies and maps `409`/`422` to inline errors.

## 13. Traceability

| Requirement | Design guarantee |
|---|---|
| A user can create an HR account | `POST /auth/sign-up` with email + password, no verification. |
| Each HR owns only their own data | `candidates.owner_id` set on create/import; every HR read scoped by owner. |
| HRs do not share data, even with the same role | `owner_id` scoping is independent of `role_id`. |
| Legacy data stays with the seeded account | Migration backfills `owner_id` to the sole existing user. |
| Cross-tenant access does not leak existence | `404` for both "not yours" and "does not exist". |
| Same pack imported by two HRs stays isolated | Import keys candidates on `(owner_id, external_ref)` and audio on `audio/import/{candidate_id}/{answer_id}.m4a`. |
| `roles` and `questions` stay shared | They are unchanged global reference data. |
| Candidate links keep working | `session_token` stays globally unique and is resolved without owner. |
| No admin escalation needed | Seeded account is a normal tenant; no new role. |

## 14. Documentation Changes

This spec is authoritative.
The following docs are amended to stay consistent:

1. `2026-10-18-api-contract-design.md` - add a top "Amended by" banner, `POST /auth/sign-up` to the auth table, `owner_id` and per-owner uniqueness to the `candidates` table, ownership scoping to the HR endpoints, and an ownership entry in the traceability table.
2. `2026-10-18-backend-design.md` - update the auth service (sign-up), candidates module (`owner_id`), data-model tables, authorization section, import section, and migration section.
3. `2026-10-18-hr-web-design.md` - add the sign-up page, the sign-up route handler, and note that all data is per-owner.
4. `README.md` - document self-registration, per-account data isolation, and the two limitations (no email verification, no password reset).
