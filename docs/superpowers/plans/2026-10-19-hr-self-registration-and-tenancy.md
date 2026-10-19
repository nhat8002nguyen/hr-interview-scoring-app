# HR Self-Registration and Tenancy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let any person create their own HR account, where each HR owns their own candidates, answers, scoring jobs, and interview links via a `candidates.owner_id`.

**Architecture:** `roles` and `questions` stay shared reference data; `candidates` gains a `NOT NULL` `owner_id` (foreign key to `users.id`). Ownership of answers and scoring jobs is resolved by joining through `candidate_id`. A `POST /auth/sign-up` endpoint creates `role=hr` accounts. Every HR read/write is scoped by the caller's `owner_id`; cross-tenant access returns `404`.

**Tech Stack:** Python 3.14 + FastAPI + SQLAlchemy (async) + Alembic, PostgreSQL 18. Next.js 16 (App Router) + TypeScript + Tailwind + zod for `apps/hr-web`.

**Spec:** `docs/superpowers/specs/2026-10-19-hr-self-registration-and-tenancy-design.md` (authoritative). The plan argues from it; executors read both.

## Global Constraints

- Python `>=3.14`; `ruff`, `mypy --strict` (excludes `migrations/` and `tests/`); `pytest` with `asyncio_mode=auto`.
- Next.js 16 breaking changes exist - read `apps/hr-web/node_modules/next/dist/docs/` before writing frontend code; the session guard is `apps/hr-web/proxy.ts`, not `middleware.ts`.
- Errors are RFC 7807 problem details: `{"type":"about:blank","title","status","detail"}`.
- One sentence per physical line in long Markdown files; no em dash ("-"); commit messages carry no agent co-author.
- `users.email` stays globally unique. `candidates.session_token` stays globally unique. `candidates.email` and `candidates.external_ref` become per-owner unique.
- The scoring worker claims jobs globally (ignores owner); only the HR read/retry/override surface is owner-scoped.

## Review Focus

The spec is silent on these inputs; each must behave, and each is pinned by a test in the owning task.

1. **Cross-tenant id guessing** - an HR who requests another owner's candidate/answer/job id must get `404`, never `200` or `403`. Pinned in Task 3 and Task 4.
2. **Two owners importing the same pack** - must produce two isolated candidate sets, not collide on `email`/`external_ref`, and each owner's answer dedup must not skip records the other owner already imported. Pinned in Task 4.
3. **Duplicate email at sign-up** - must return `409`; a duplicate `candidates.email` in a different tenant must still be allowed. Pinned in Task 2 and Task 3.
4. **Malformed sign-up input** - bad email or short password returns `422` with a clear detail, and no user is created. Pinned in Task 2.
5. **Legacy backfill** - pre-existing candidates get the seeded user's `owner_id`; a fresh database has no `owner_id IS NULL` rows after `NOT NULL` is applied. Pinned in Task 1.
6. **Scoring worker unaffected** - after tenancy, any tenant's queued text job is still scored. Pinned in Task 4 (regression).

---

### Task 1: `owner_id` data layer, migration, and candidate creation

**Files:**
- Create: `apps/backend/migrations/versions/20261019_0002_hr_tenancy.py`
- Modify: `apps/backend/src/api/candidates/infrastructure/models.py`
- Modify: `apps/backend/src/api/candidates/domain/entities.py`
- Modify: `apps/backend/src/api/candidates/domain/repositories.py`
- Modify: `apps/backend/src/api/candidates/infrastructure/repository.py`
- Modify: `apps/backend/src/api/candidates/application/service.py`
- Modify: `apps/backend/src/api/candidates/presentation/hr_router.py`
- Modify: `apps/backend/src/api/importing/application/service.py`
- Test: `apps/backend/tests/test_candidates_service.py`, `apps/backend/tests/test_hr_router.py`, `apps/backend/tests/test_import_service.py`, `apps/backend/tests/test_import_router.py`, `apps/backend/tests/test_e2e_import_and_score.py`

**Interfaces:**
- Produces: `Candidate` gains field `owner_id: int` positioned between `role_id` and `session_token`. `CandidatesService.create_candidate(*, name, email, role_id, owner_id, external_ref=None) -> Candidate`. `ImportService.import_zip(data: bytes, owner_id: int) -> ImportSummary`. `CandidateRepository.add(candidate)`, `get`, `get_by_session_token` unchanged; read methods `get_by_email`, `get_by_external_ref`, `list_by_role`, `count_by_role` later gain an `owner_id` (Task 3), so keep their current single-arg forms for now except `add`.

- [ ] **Step 1: Write the migration** `20261019_0002_hr_tenancy` (`down_revision = "20261018_0001"`) with this `upgrade()` order:

  1. `op.add_column("candidates", sa.Column("owner_id", sa.Integer(), nullable=True))` then `op.create_foreign_key("fk_candidates_owner_id_users", "candidates", "users", ["owner_id"], ["id"])`.
  2. `op.execute("UPDATE candidates SET owner_id = (SELECT id FROM users ORDER BY id LIMIT 1) WHERE owner_id IS NULL")`.
  3. `op.alter_column("candidates", "owner_id", nullable=False)`.
  4. `op.drop_index("ix_candidates_email", table_name="candidates")`; `op.create_unique_constraint("uq_candidates_owner_email", "candidates", ["owner_id", "email"])`.
  5. `op.drop_index("ix_candidates_external_ref", table_name="candidates")`; `op.create_unique_constraint("uq_candidates_owner_external_ref", "candidates", ["owner_id", "external_ref"])`.
  6. `op.create_index("ix_candidates_owner_role", "candidates", ["owner_id", "role_id"])`.
  7. `downgrade()` reverses in opposite order (drop constraints/indexes, drop column).

- [ ] **Step 2: Update `CandidateModel`** to match: add `owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)`; remove `unique=True, index=True` from `email` and `external_ref` (keep `external_ref` `nullable=True`); add `__table_args__ = (UniqueConstraint("owner_id", "email", name="uq_candidates_owner_email"), UniqueConstraint("owner_id", "external_ref", name="uq_candidates_owner_external_ref"), Index("ix_candidates_owner_role", "owner_id", "role_id"))`. Keep `session_token` unique/indexed. Import `UniqueConstraint`, `Index`.

- [ ] **Step 3: Add `owner_id` to the `Candidate` entity** (between `role_id` and `session_token`) and to `CandidateRepository.add` signature stays `add(candidate)`. Update `SqlAlchemyCandidateRepository.add` to set `owner_id=candidate.owner_id` and `_to_candidate` to read `owner_id=row.owner_id`.

- [ ] **Step 4: Thread `owner_id` into `CandidatesService.create_candidate`** - add `owner_id: int` as a required keyword arg and set it on the constructed `Candidate`.

- [ ] **Step 5: Update `hr_router.create_candidate`** - add `user: CurrentUserDep` parameter (import `CurrentUserDep` from `iam`) and pass `owner_id=user.sub` to `candidates.create_candidate`.

- [ ] **Step 6: Update `ImportService`** - `import_zip(self, data: bytes, owner_id: int)`; `_create_candidate(...)` passes `owner_id=owner_id` into `self._candidates.create_candidate(...)`. Update `importing/presentation/router.py` `import_pack` to add `user: CurrentUserDep` and call `importer.import_zip(data, owner_id=user.sub)`.

- [ ] **Step 7: Update test fakes and construction sites** so the suite passes: every `Candidate(...)` and `CandidateModel(...)` call gains `owner_id` (use `owner_id=1` in fakes). In `test_e2e_import_and_score.py`, create a `UserModel(email="hr@example.com", password_hash="x", role="hr")` row before creating `CandidateModel(...)`, then set `owner_id=user.id`. Update `import_zip(...)` test calls to pass `owner_id=1`.

- [ ] **Step 8: Run backend tests and lint**

Run: `cd apps/backend && uv run pytest -q && uv run ruff check . && uv run mypy libs src`
Expected: PASS (all pre-existing tests green with the mechanical updates).

- [ ] **Step 9: Verify migration against Postgres with seeded data**

Run: start the stack (`docker compose up -d db` then `docker compose run --rm migrate`, or `cd apps/backend && docker compose up --build`), then `psql`/`alembic` inspect that `candidates.owner_id` is `NOT NULL` and that pre-existing rows point at the seeded user.
Expected: `owner_id` non-null on all rows; `\d candidates` shows the two composite uniques and the `(owner_id, role_id)` index.

- [ ] **Step 10: Commit**

```bash
git add apps/backend/migrations/versions/20261019_0002_hr_tenancy.py apps/backend/src/api/candidates apps/backend/src/api/importing apps/backend/tests
git commit -m "feat: add candidates.owner_id with tenancy migration"
```

---

### Task 2: Self-service sign-up

**Files:**
- Modify: `apps/backend/pyproject.toml` (add `"email-validator>=2.2"` to `dependencies`)
- Modify: `apps/backend/src/api/auth/domain/exceptions.py`
- Modify: `apps/backend/src/api/auth/application/service.py`
- Modify: `apps/backend/src/api/auth/presentation/schemas.py`
- Modify: `apps/backend/src/api/auth/presentation/router.py`
- Modify: `apps/backend/src/api/auth/presentation/errors.py`
- Modify: `apps/backend/src/api/config.py`
- Test: `apps/backend/tests/test_authentication_service.py`, `apps/backend/tests/test_authentication.py`

**Interfaces:**
- Produces: `AuthenticationService.sign_up(email: str, password: str) -> AuthTokens`. `SignUpBody {email: EmailStr, password: str}`. `EmailAlreadyExistsError(email: str)` mapped to `409`. `POST /auth/sign-up` returns `201` + `AuthTokensResponse`. `Settings.password_min_length: int = 8`.

- [ ] **Step 1: Add config** - `password_min_length: int = 8` to `Settings`.

- [ ] **Step 2: Add `EmailAlreadyExistsError`** to `auth/domain/exceptions.py` (stores `self.email`), and map it to `409` in `auth/presentation/errors.py`.

- [ ] **Step 3: Write the failing service test** in `test_authentication_service.py`:

```python
async def test_sign_up_creates_hr_and_issues_tokens():
    # service with empty FakeUserRepository; sign_up("new@example.com", "password123")
    # assert tokens.user.role == Role.HR, tokens.user.email == "new@example.com"
    # assert the user was added (repo has it) and refresh_tokens.saved has one entry

async def test_sign_up_duplicate_email_raises():
    # pre-populate by_email with new@example.com; with pytest.raises(EmailAlreadyExistsError): sign_up(...)
```

- [ ] **Step 4: Run to verify it fails** (EmailAlreadyExistsError and sign_up do not exist yet).

- [ ] **Step 5: Implement `sign_up`** in `AuthenticationService` - if `await self._users.get_by_email(email)` is not None, raise `EmailAlreadyExistsError(email)`; hash the password; `add(User(id=0, email=email, password_hash=..., role=Role.HR))`; then `return await self._issue_tokens(user)`.

- [ ] **Step 6: Add `SignUpBody`** to `auth/presentation/schemas.py`: `email: EmailStr`, `password: str = Field(min_length=...)` - validate min length via the configured setting is not possible in a schema default, so use `min_length=8` and re-check in the router is unnecessary; keep it simple with `password: str` and a `field_validator` that requires `len >= 8`. Import `EmailStr` (from `pydantic`).

- [ ] **Step 7: Add the route** to `auth/presentation/router.py`:

```python
@auth_router.post("/sign-up", response_model=AuthTokensResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(_require_none)])
async def sign_up(body: SignUpBody, service: AuthenticationServiceDep) -> AuthTokensResponse:
    tokens = await service.sign_up(body.email, body.password)
    return _to_response(tokens)
```

- [ ] **Step 8: Write the failing HTTP test** in `test_authentication.py` (extend `FakeAuthenticationService` with `sign_up`): `test_sign_up_returns_201_and_tokens`, `test_sign_up_duplicate_email_409`, `test_sign_up_short_password_422` (assert problem detail status). Run to verify fail, then implement the fake and assert pass.

- [ ] **Step 9: Add `email-validator` to `apps/backend/pyproject.toml`** dependencies; run `uv sync`.

- [ ] **Step 10: Run backend tests and lint** (`uv run pytest -q`, `ruff`, `mypy`) - PASS.

- [ ] **Step 11: Commit**

```bash
git add apps/backend/pyproject.toml apps/backend/uv.lock apps/backend/src/api/auth apps/backend/src/api/config.py apps/backend/tests/test_authentication.py apps/backend/tests/test_authentication_service.py
git commit -m "feat: add HR self-service sign-up endpoint"
```

---

### Task 3: Ownership scoping - candidates and roles

**Files:**
- Modify: `apps/backend/src/api/candidates/domain/repositories.py`
- Modify: `apps/backend/src/api/candidates/infrastructure/repository.py`
- Modify: `apps/backend/src/api/candidates/application/service.py`
- Modify: `apps/backend/src/api/candidates/presentation/hr_router.py`
- Modify: `apps/backend/src/api/catalog/application/ports.py`
- Modify: `apps/backend/src/api/catalog/application/service.py`
- Modify: `apps/backend/src/api/catalog/presentation/router.py`
- Test: `apps/backend/tests/test_hr_router.py`, `apps/backend/tests/test_catalog_service.py`, `apps/backend/tests/test_catalog_router.py`

**Interfaces:**
- Produces: `CandidateRepository.get_by_email(owner_id, email)`, `get_by_external_ref(owner_id, external_ref)`, `list_by_role(owner_id, role_id)`, `count_by_role(owner_id, role_id)`. `CandidatesService.get_owned_candidate(candidate_id, owner_id) -> Candidate` (raises `CandidateNotFoundError`). `CandidatesService.list_candidates_for_role(role_id, owner_id)`, `count_by_role(role_id, owner_id)`. `RoleCandidateCounter.count_by_role(role_id, owner_id)`. `CatalogService.list_roles(owner_id)`. `GET /hr/roles` and `GET /hr/roles/{role_id}/candidates` scope by owner.

- [ ] **Step 1: Change candidate read signatures** in `CandidateRepository` and `SqlAlchemyCandidateRepository` (and the service delegations) to take `owner_id` first, filtering by `CandidateModel.owner_id == owner_id` in the SQL. `get(candidate_id)` and `get_by_session_token(session_token)` stay global.

- [ ] **Step 2: Add `CandidatesService.get_owned_candidate(candidate_id, owner_id)`** - load via `uow.candidates.get(candidate_id)`; if `None` or `candidate.owner_id != owner_id`, raise `CandidateNotFoundError(candidate_id)`; else return.

- [ ] **Step 3: Write the failing isolation test** in `test_hr_router.py`:

```python
async def test_cross_tenant_candidate_detail_is_404():
    # candidate owner_id=2; token sub=1; GET /hr/candidates/{id} -> 404 (title "Not Found")
async def test_list_candidates_for_role_scopes_by_owner():
    # two candidates same role, owner_id 1 and 2; token sub=1 -> only owner 1's candidate returned
```

Run to verify fail (scoping not yet enforced).

- [ ] **Step 4: Scope `hr_router` candidate reads** - `list_candidates_for_role(role_id, user)` passes `owner_id=user.sub`; `get_candidate_detail` uses `candidates.get_owned_candidate(candidate_id, user.sub)`. Add `user: CurrentUserDep` to both handlers.

- [ ] **Step 5: Scope role counts** - change `RoleCandidateCounter.count_by_role(role_id, owner_id)`; `CatalogService.list_roles(owner_id)` passes `owner_id` to the counter; `catalog_router.list_roles(user: CurrentUserDep)` passes `user.sub`.

- [ ] **Step 6: Update the catalog tests** for the new `count_by_role`/`list_roles` signatures, and add `test_roles_candidate_count_scoped_to_owner` (role with 3 candidates from owner 1 and 2 from owner 2 -> owner 1 sees count 3).

- [ ] **Step 7: Run backend tests and lint** - PASS.

- [ ] **Step 8: Commit**

```bash
git add apps/backend/src/api/candidates apps/backend/src/api/catalog apps/backend/tests/test_hr_router.py apps/backend/tests/test_catalog_service.py apps/backend/tests/test_catalog_router.py
git commit -m "feat: scope candidate and role reads by owner"
```

---

### Task 4: Ownership scoping - answers, scoring, and import

**Files:**
- Modify: `apps/backend/src/api/candidates/application/service.py` (AnswersService)
- Modify: `apps/backend/src/api/candidates/domain/repositories.py` (AnswerRepository)
- Modify: `apps/backend/src/api/candidates/infrastructure/repository.py`
- Modify: `apps/backend/src/api/candidates/presentation/hr_router.py`
- Modify: `apps/backend/src/api/scoring/domain/repositories.py`
- Modify: `apps/backend/src/api/scoring/infrastructure/repository.py`
- Modify: `apps/backend/src/api/scoring/application/service.py`
- Modify: `apps/backend/src/api/scoring/presentation/router.py`
- Modify: `apps/backend/src/api/importing/application/service.py`
- Test: `apps/backend/tests/test_scoring_router.py`, `apps/backend/tests/test_scoring_service.py`, `apps/backend/tests/test_import_service.py`, `apps/backend/tests/test_e2e_import_and_score.py`

**Interfaces:**
- Produces: `AnswerRepository.get_by_external_ref(candidate_id, external_ref)`. `AnswersService.get_owned(answer_id, owner_id) -> Answer` (raises `AnswerNotFoundError`). `ScoringJobRepository.list(status, owner_id)`, `get_owned(job_id, owner_id) -> ScoringJob | None`. `ScoringService.list_jobs(status, owner_id)`, `retry(job_id, owner_id)`. `ImportService.import_zip(data, owner_id)` dedups answers by `(candidate_id, external_ref)`.

- [ ] **Step 1: Add `AnswersService.get_owned(answer_id, owner_id)`** - within one `CandidatesUnitOfWork`, load the answer and its candidate; if the answer is missing or `candidate.owner_id != owner_id`, raise `AnswerNotFoundError(answer_id)`.

- [ ] **Step 2: Scope answer detail/audio in `hr_router`** - `get_answer_detail` and `get_answer_audio` use `answers.get_owned(answer_id, user.sub)` (add `user: CurrentUserDep`), then `read_audio`/`catalog.get_question` as before.

- [ ] **Step 3: Scope scoring reads** - `build_list_statement(status, owner_id)` adds `CandidateModel.owner_id == owner_id`; `ScoringJobRepository.list(status, owner_id)`; add `get_owned(job_id, owner_id)` (join scoring_jobs -> answers -> candidates, filter owner, return `ScoringJob | None`). `ScoringService.list_jobs(status, owner_id)` and `retry(job_id, owner_id)` (raise `ScoringJobNotFoundError` when `get_owned` is None).

- [ ] **Step 4: Scope scoring router** - `list_scoring_jobs` and `retry_scoring_job` add `user: CurrentUserDep` and pass `owner_id=user.sub`. `override_answer_score` first calls `answers.get_owned(answer_id, user.sub)` to enforce ownership before `scoring.override_score(...)`.

- [ ] **Step 5: Scope import answer dedup** - change `AnswerRepository.get_by_external_ref` to `(candidate_id, external_ref)` and update `AnswersService.get_by_external_ref(candidate_id, external_ref)`. In `ImportService.import_zip`, replace the two `self._answers.get_by_external_ref(answer_id)` pre-checks with `self._answers.get_by_external_ref(candidate.id, answer_id)` (candidate is already resolved per-owner). Update the e2e test's `answers.get_by_external_ref("A001")` call to pass the candidate id.

- [ ] **Step 6: Write failing isolation tests** in `test_scoring_router.py` and `test_import_service.py`:

```python
async def test_cross_tenant_scoring_job_retry_is_404(): ...
async def test_scoring_jobs_list_scopes_by_owner(): ...
async def test_import_same_pack_two_owners_isolated():
    # owner 1 then owner 2 import the same pack; each has 2 candidates; no email/external_ref collision
```

Run to verify fail.

- [ ] **Step 7: Run backend tests and lint** - PASS (including the e2e import/score regression: worker still scores text jobs).

- [ ] **Step 8: Commit**

```bash
git add apps/backend/src/api/candidates apps/backend/src/api/scoring apps/backend/src/api/importing apps/backend/tests
git commit -m "feat: scope answers, scoring, and import by owner"
```

---

### Task 5: Rate limiting on sign-in and sign-up

**Files:**
- Create: `apps/backend/src/api/auth/application/rate_limit.py`
- Modify: `apps/backend/src/api/config.py`
- Modify: `apps/backend/src/api/auth/presentation/router.py`
- Modify: `apps/backend/src/api/auth/presentation/dependencies.py`
- Test: `apps/backend/tests/test_rate_limit.py`

**Interfaces:**
- Produces: `RateLimiter(max_requests: int, window_seconds: float)` with `async def check(key: str) -> None` raising `RateLimitExceededError`. Config `auth_rate_limit: int = 60`, `auth_rate_limit_window_seconds: float = 60.0`. A `require_rate_limit(key)` dependency applied to `POST /auth/sign-in` and `POST /auth/sign-up` keyed by client IP (and email on sign-up).

- [ ] **Step 1: Add config** `auth_rate_limit` and `auth_rate_limit_window_seconds` to `Settings`.

- [ ] **Step 2: Write the failing unit test** `test_rate_limit.py` - a limiter with `max_requests=2` allows two `check` calls and raises on the third within the window; a limiter with a tiny window allows again after `asyncio.sleep`.

- [ ] **Step 3: Implement `RateLimiter`** - in-process fixed window: a `dict[str, list[float]]` of timestamps; prune entries older than the window; raise `RateLimitExceededError` when the count reaches the max. Map `RateLimitExceededError` to `429` in `auth/presentation/errors.py`.

- [ ] **Step 4: Wire the dependency** - in `auth/presentation/dependencies.py`, a `RateLimiter` built from `app.state.settings`; a `rate_limit_sign_in(request)` and `rate_limit_sign_up(request, body)` dependency. Add these to the two routes in `router.py`.

- [ ] **Step 5: Add a router test** asserting `429` after exceeding the limit on `POST /auth/sign-up` (lower the configured max via a test app state).

- [ ] **Step 6: Run backend tests and lint** - PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/backend/src/api/auth apps/backend/src/api/config.py apps/backend/tests/test_rate_limit.py
git commit -m "feat: rate-limit HR sign-in and sign-up"
```

---

### Task 6: HR web sign-up page and route handler

**Files:**
- Create: `apps/hr-web/app/sign-up/page.tsx`
- Create: `apps/hr-web/app/api/auth/sign-up/route.ts`
- Modify: `apps/hr-web/lib/validation/schemas.ts`
- Modify: `apps/hr-web/app/sign-in/page.tsx`
- Modify: `apps/hr-web/proxy.ts`
- Test: `apps/hr-web/lib/validation/schemas.test.ts`, `apps/hr-web/app/api/auth/sign-up/route.test.ts`

**Interfaces:**
- Consumes: `createApiClient`, `createNextSessionStore`, `problemResponse`, `AuthResponse` (already in `lib/contracts/types.ts`).
- Produces: `signUpSchema` (email + password min 8). `POST /api/auth/sign-up` sets both httpOnly cookies and returns `{ user }`.

- [ ] **Step 1: Add `signUpSchema`** to `lib/validation/schemas.ts`: `z.object({ email: z.email(), password: z.string().min(8) })`, export `SignUpInput`. Add a passing schema test (min-8 enforcement).

- [ ] **Step 2: Create the route handler** `app/api/auth/sign-up/route.ts` mirroring `app/api/auth/sign-in/route.ts`: parse JSON, `signUpSchema.safeParse`, call `client.request("POST", "/auth/sign-up", { body: parsed.data })`, `store.setTokens(...)`, return `NextResponse.json({ user })`; map `ApiError` to `problemResponse`.

- [ ] **Step 3: Create the page** `app/sign-up/page.tsx` mirroring `app/sign-in/page.tsx`: email + password fields, submit to `/api/auth/sign-up`, `router.push("/roles")` on success, inline error on `ClientError`, and a link to `/sign-in`.

- [ ] **Step 4: Add the sign-up link** to `app/sign-in/page.tsx` ("Create an account" -> `/sign-up`).

- [ ] **Step 5: Update `proxy.ts`** - add `/sign-up` to `PUBLIC_PREFIXES` and to the `matcher` negative-lookahead list.

- [ ] **Step 6: Add route handler test** (mocked `lib/api`) asserting cookies set on success and `409`/`422` mapped.

- [ ] **Step 7: Run HR web checks** - `cd apps/hr-web && npm test && npm run lint && npm run typecheck` (or the script the app exposes). PASS.

- [ ] **Step 8: Commit**

```bash
git add apps/hr-web
git commit -m "feat: add HR sign-up page and BFF route"
```

---

### Task 7: Update docs and README

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-10-18-api-contract-design.md`
- Modify: `docs/superpowers/specs/2026-10-18-backend-design.md`
- Modify: `docs/superpowers/specs/2026-10-18-hr-web-design.md`

- [ ] **Step 1: Amend the API contract** - add an "Amended by `2026-10-19-hr-self-registration-and-tenancy-design.md`" banner at the top; add `POST /auth/sign-up` to the auth table with its request/response and `409`/`422`; add `owner_id` + per-owner uniqueness to the `candidates` table in section 6.3; add an ownership-scoping note to the HR endpoint section; add an ownership row to the traceability table.

- [ ] **Step 2: Amend the backend design** - update section 6.2 (sign-up in `AuthenticationService`), 6.4 (candidates `owner_id` and scoped repositories), 7.2 (`candidates` table), 8 (sign-up + ownership scoping), 11 (import owner), 13 (migration), and add `password_min_length`, `auth_rate_limit*` to the config table.

- [ ] **Step 3: Amend the HR web design** - add the `/sign-up` page and route handler to sections 6 and 7, note all data is per-owner, and update the sign-in flow to mention the sign-up link.

- [ ] **Step 4: Update the README** - document self-registration, per-account data isolation, and the two documented limitations (no email verification, no password reset); keep the seeded demo credentials as-is.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/superpowers/specs
git commit -m "docs: document HR self-registration and tenancy"
```

---

## Self-Review Notes

- Spec coverage: sections 5 (data model) -> Task 1; 6 (migration) -> Task 1; 7 (sign-up) -> Task 2; 8 (scoping) -> Tasks 3-4; 9 (import) -> Task 4; 10 (rate limit) -> Task 5; 11 (frontend) -> Task 6; 14 (docs) -> Task 7. Every spec section maps to a task.
- Type consistency: `owner_id` name is uniform across entity, model, repository, service, and tests; `get_owned`/`get_owned_candidate`/`list_jobs(status, owner_id)` are used consistently.
- Review Focus items 1-6 are each pinned by a named test in Tasks 2-4.
- The migration is not covered by pytest (integration tests use `Base.metadata.create_all`); Task 1 Step 9 adds the manual Postgres verification.
