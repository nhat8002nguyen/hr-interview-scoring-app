# Candidate Web Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the candidate-facing Next.js app that walks a candidate through six interview questions (text or audio), confirms "answer received", and resumes at the same question on reload.

**Architecture:** A single client flow: one route `/interview/[token]` renders a client `InterviewFlow` that owns the wizard state, fetches through a typed `lib/api.ts` (which injects `X-Candidate-Token` and parses RFC 7807 errors), and persists the current question index to `localStorage` for resume.

**Tech Stack:** Next.js 16 App Router, TypeScript (strict), Tailwind CSS v4, Vitest + React Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-18-candidate-web-design.md`

## Global Constraints

- Next.js 16 App Router; TypeScript strict; Tailwind CSS v4 (spec §4).
- Token sent as `X-Candidate-Token` header on every API call; never in the URL sent to the API (spec §6).
- Base URL from `NEXT_PUBLIC_API_ORIGIN` (spec §10).
- App never requests or renders scores, grading guides, or HR data (spec §4).
- Errors are RFC 7807 problem details; parse into a typed `ApiError` carrying `status` + `detail` (spec §6).
- Resume persists the current question index to `localStorage` keyed by token (spec §7.1).
- One answer per question (text XOR audio) via a Type / Upload audio toggle (spec §4).

## Review Focus

The failure modes below are implied by the spec but easy to leave untested. Each is pinned by a test in the task that owns the code.

1. **Stored resume index is malformed or out of range** (e.g. `localStorage` holds `"abc"` or `"99"`). Expected: fall back to the first unanswered question, not crash. Test in Task 4.
2. **Fetch rejects at the network level** (not an HTTP error response). Expected: a generic inline error, app does not crash. Test in Task 4.
3. **Non-2xx response has an empty or non-JSON body.** Expected: `ApiError` still constructed with `status` and no `detail`. Test in Task 2.
4. **Empty/whitespace text submitted.** Expected: submit button disabled so it cannot be sent; if it reaches the API, a `422` surfaces as an inline error. Tests in Tasks 3 and 4.
5. **Audio file rejected by the API** (`422` invalid file / `413` too large). Expected: inline error on the question, no crash. Test in Task 4.

---

## File Structure

```text
talot-candidate-web/
├── app/
│   ├── layout.tsx                  # root layout, metadata, globals import
│   ├── page.tsx                    # fallback: "Open the interview link you were sent"
│   ├── globals.css                 # @import "tailwindcss";
│   ├── not-found.tsx               # default 404
│   └── interview/[token]/page.tsx  # server page, reads token, renders InterviewFlow
├── components/
│   ├── interview/
│   │   ├── interview-flow.tsx      # client: state machine, resume, orchestration
│   │   ├── question-card.tsx       # prompt + progress + answer-input
│   │   ├── answer-input.tsx        # Type/Upload audio toggle + inputs
│   │   ├── progress.tsx            # "Question n of 6"
│   │   ├── confirmation.tsx        # "answer received" + unchanged note
│   │   ├── loading.tsx
│   │   ├── invalid-link.tsx
│   │   └── completion.tsx
│   └── ui/
│       ├── button.tsx
│       ├── textarea.tsx
│       └── segmented-control.tsx
├── lib/
│   ├── types.ts                    # contract types + ApiError
│   └── api.ts                      # typed fetch client
├── tests/
│   ├── api.test.ts
│   └── components/
│       ├── answer-input.test.tsx
│       ├── progress.test.tsx
│       ├── confirmation.test.tsx
│       └── interview-flow.test.tsx
├── e2e/
│   └── interview.spec.ts
├── vitest.config.ts
├── playwright.config.ts
├── .env.example
└── package.json
```

---

### Task 1: Scaffold the Next.js app and test tooling

**Files:**
- Create: `package.json`, `tsconfig.json`, `next.config.ts`, `postcss.config.mjs`, `vitest.config.ts`, `playwright.config.ts`, `app/layout.tsx`, `app/page.tsx`, `app/globals.css`, `app/not-found.tsx`, `.env.example`, `.gitignore` (exists)

**Interfaces:**
- Produces: a runnable app. `app/page.tsx` renders the fallback text `"Open the interview link you were sent"`. Vitest configured with `environment: "jsdom"`, `setupFiles`, and `test.env.NEXT_PUBLIC_API_ORIGIN = "http://api.test"`. `playwright.config.ts` uses a `webServer` that runs the dev server. `@/*` maps to the repo root.

- [ ] **Step 1: Scaffold with create-next-app**

Run: `npx create-next-app@latest . --typescript --tailwind --app --eslint --import-alias "@/*" --use-npm`
Then remove the generated `README.md` and `public/` defaults only if you will not use them; keep `eslint` and `tailwind` as generated.

- [ ] **Step 2: Add test dependencies**

Run: `npm i -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event @playwright/test`

- [ ] **Step 3: Create `vitest.config.ts`**

Set `test.environment = "jsdom"`, `test.globals = true`, `test.setupFiles = ["./tests/setup.ts"]`, `test.env = { NEXT_PUBLIC_API_ORIGIN: "http://api.test" }`, and a `resolve.alias` for `@` -> repo root. Create `tests/setup.ts` that imports `@testing-library/jest-dom`.

- [ ] **Step 4: Create `playwright.config.ts`**

`testDir: "./e2e"`, `use.baseURL: "http://localhost:3000"`, and a `webServer` block with `command: "npm run dev"`, `url: "http://localhost:3000"`, `reuseExistingServer: true`.

- [ ] **Step 5: Create `.env.example` with the single required variable**

```
NEXT_PUBLIC_API_ORIGIN=http://localhost:8000
```

- [ ] **Step 6: Write `app/page.tsx` fallback text and add a smoke test**

`app/page.tsx` renders exactly the string `Open the interview link you were sent`.

Create `tests/smoke.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import Page from "@/app/page";

it("renders the fallback message", () => {
  render(<Page />);
  expect(screen.getByText("Open the interview link you were sent")).toBeInTheDocument();
});
```

- [ ] **Step 7: Verify build and tests pass**

Run: `npm run build` (expected: success) then `npm test` (expected: 1 passing smoke test)

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "chore: scaffold Next.js app with test tooling"
```

---

### Task 2: Typed API client (`lib/types.ts` + `lib/api.ts`)

**Files:**
- Create: `lib/types.ts`, `lib/api.ts`
- Test: `tests/api.test.ts`

**Interfaces:**
- Consumes: Vitest env `NEXT_PUBLIC_API_ORIGIN = "http://api.test"` (Task 1).
- Produces:
  - `type AnswerType = "text" | "audio"`
  - `interface Candidate { id: number; name: string | null; role: string }`
  - `interface Answer { answer_type: AnswerType; text: string | null; version: number; submitted_at: string }`
  - `interface Question { id: number; code: string; sort_order: number; prompt: string; answer: Answer | null }`
  - `interface Progress { answered: number; total: number }`
  - `interface InterviewResponse { candidate: Candidate; questions: Question[]; progress: Progress }`
  - `interface SubmitResponse { status: "received"; unchanged: boolean; answer: { answer_type: AnswerType; version: number; submitted_at: string } }`
  - `class ApiError extends Error { constructor(readonly status: number, detail?: string) }`
  - `getInterview(token: string): Promise<InterviewResponse>`
  - `submitTextAnswer(token: string, questionId: number, text: string): Promise<SubmitResponse>`
  - `submitAudioAnswer(token: string, questionId: number, file: File): Promise<SubmitResponse>`

- [ ] **Step 1: Write the failing tests**

Create `tests/api.test.ts`. Stub `global.fetch` with `vi.stubGlobal("fetch", vi.fn())` in `beforeEach`, `vi.unstubAllGlobals()` in `afterEach`. Cover these cases:

```tsx
it("getInterview sends the token header and returns the interview", async () => {
  const data = { candidate: { id: 1, name: "Nhi", role: "Backend Engineer" }, questions: [], progress: { answered: 0, total: 6 } };
  (fetch as any).mockResolvedValue({ ok: true, json: async () => data });
  const result = await getInterview("tok123");
  expect(fetch).toHaveBeenCalledWith("http://api.test/candidate/interview", { headers: { "X-Candidate-Token": "tok123" } });
  expect(result).toEqual(data);
});

it("submitTextAnswer posts JSON with answer_type and text", async () => {
  (fetch as any).mockResolvedValue({ ok: true, json: async () => ({ status: "received", unchanged: false, answer: { answer_type: "text", version: 1, submitted_at: "t" } }) });
  await submitTextAnswer("tok", 1, "my answer");
  const [url, init] = (fetch as any).mock.calls[0];
  expect(url).toBe("http://api.test/candidate/interview/answers/1");
  expect(init.method).toBe("POST");
  expect(init.headers["X-Candidate-Token"]).toBe("tok");
  expect(JSON.parse(init.body)).toEqual({ answer_type: "text", text: "my answer" });
});

it("submitAudioAnswer posts a FormData body with the file and no manual Content-Type", async () => {
  (fetch as any).mockResolvedValue({ ok: true, json: async () => ({ status: "received", unchanged: false, answer: { answer_type: "audio", version: 1, submitted_at: "t" } }) });
  const file = new File(["x"], "a.m4a", { type: "audio/mp4" });
  await submitAudioAnswer("tok", 2, file);
  const [url, init] = (fetch as any).mock.calls[0];
  expect(url).toBe("http://api.test/candidate/interview/answers/2/audio");
  expect(init.body).toBeInstanceOf(FormData);
  expect(init.body.get("file")).toBe(file);
  expect(init.headers["Content-Type"]).toBeUndefined();
});

it("throws ApiError with status and detail on a non-2xx JSON body", async () => {
  (fetch as any).mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: "text is empty" }) });
  await expect(getInterview("tok")).rejects.toMatchObject({ status: 422, detail: "text is empty" });
});

it("throws ApiError without detail on a non-JSON error body", async () => {
  (fetch as any).mockResolvedValue({ ok: false, status: 500, json: async () => { throw new Error("not json"); } });
  await expect(getInterview("tok")).rejects.toMatchObject({ status: 500 });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- tests/api.test.ts`
Expected: FAIL - `Cannot find module '@/lib/api'`

- [ ] **Step 3: Implement `lib/types.ts`**

Define every type and the `ApiError` class exactly as listed in the Interfaces block. `ApiError` sets `this.name = "ApiError"` and its message to `detail ?? "Request failed with status ${status}"`.

- [ ] **Step 4: Implement `lib/api.ts`**

Three exported async functions per the Interfaces block. Read `const API_ORIGIN = process.env.NEXT_PUBLIC_API_ORIGIN ?? ""` once at module top. A shared `request` helper sets the `X-Candidate-Token` header, and on `!response.ok` reads the body JSON, extracts `detail`, and throws `new ApiError(response.status, detail)`; if body parsing fails it throws `new ApiError(response.status)`. For `submitAudioAnswer`, build a `FormData` and append the file under key `"file"`; do not set `Content-Type` manually. For `submitTextAnswer`, set `Content-Type: application/json` and stringify `{ answer_type: "text", text }`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `npm test -- tests/api.test.ts`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add lib tests/api.test.ts
git commit -m "feat: add typed candidate API client"
```

---

### Task 3: Answer input, question card, progress, and confirmation

**Files:**
- Create: `components/ui/button.tsx`, `components/ui/textarea.tsx`, `components/ui/segmented-control.tsx`, `components/interview/answer-input.tsx`, `components/interview/question-card.tsx`, `components/interview/progress.tsx`, `components/interview/confirmation.tsx`
- Test: `tests/components/answer-input.test.tsx`, `tests/components/progress.test.tsx`, `tests/components/confirmation.test.tsx`

**Interfaces:**
- Consumes: `Answer` and `AnswerType` from `lib/types` (Task 2).
- Produces:
  - `AnswerInputProps { questionId: number; initialAnswer: Answer | null; submitting: boolean; onSubmitText: (questionId: number, text: string) => void; onSubmitAudio: (questionId: number, file: File) => void }`
  - `ProgressProps { index: number; total: number }` - renders `Question {index + 1} of {total}`
  - `ConfirmationProps { unchanged: boolean; onContinue: () => void }`
  - `QuestionCardProps { question: Question; index: number; total: number; submitting: boolean; onSubmitText: ...; onSubmitAudio: ... }`

- [ ] **Step 1: Write the failing tests**

`tests/components/answer-input.test.tsx` (use `@testing-library/user-event`):

```tsx
it("renders a textarea and a Type/Upload audio toggle", () => {
  render(<AnswerInput questionId={1} initialAnswer={null} submitting={false} onSubmitText={vi.fn()} onSubmitAudio={vi.fn()} />);
  expect(screen.getByLabelText("Your answer")).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "Type" })).toBeChecked();
});

it("prefills text from initialAnswer", () => {
  const answer = { answer_type: "text", text: "previous", version: 1, submitted_at: "t" };
  render(<AnswerInput questionId={1} initialAnswer={answer} submitting={false} onSubmitText={vi.fn()} onSubmitAudio={vi.fn()} />);
  expect(screen.getByLabelText("Your answer")).toHaveValue("previous");
});

it("disables submit while text is empty or whitespace", async () => {
  render(<AnswerInput questionId={1} initialAnswer={null} submitting={false} onSubmitText={vi.fn()} onSubmitAudio={vi.fn()} />);
  const submit = screen.getByRole("button", { name: "Submit answer" });
  expect(submit).toBeDisabled();
  await user.type(screen.getByLabelText("Your answer"), "   ");
  expect(submit).toBeDisabled();
});

it("calls onSubmitText with the question id and text", async () => {
  const onSubmitText = vi.fn();
  render(<AnswerInput questionId={3} initialAnswer={null} submitting={false} onSubmitText={onSubmitText} onSubmitAudio={vi.fn()} />);
  await user.type(screen.getByLabelText("Your answer"), "my answer");
  await user.click(screen.getByRole("button", { name: "Submit answer" }));
  expect(onSubmitText).toHaveBeenCalledWith(3, "my answer");
});

it("calls onSubmitAudio with the selected file", async () => {
  const onSubmitAudio = vi.fn();
  render(<AnswerInput questionId={2} initialAnswer={null} submitting={false} onSubmitText={vi.fn()} onSubmitAudio={onSubmitAudio} />);
  await user.click(screen.getByRole("radio", { name: "Upload audio" }));
  const file = new File(["x"], "a.m4a", { type: "audio/mp4" });
  await user.upload(screen.getByLabelText("Audio file"), file);
  await user.click(screen.getByRole("button", { name: "Submit answer" }));
  expect(onSubmitAudio).toHaveBeenCalledWith(2, file);
});
```

`tests/components/progress.test.tsx`:

```tsx
it("renders the one-based position", () => {
  render(<Progress index={1} total={6} />);
  expect(screen.getByText("Question 2 of 6")).toBeInTheDocument();
});
```

`tests/components/confirmation.test.tsx`:

```tsx
it("renders the received message and continue", async () => {
  const onContinue = vi.fn();
  render(<Confirmation unchanged={false} onContinue={onContinue} />);
  expect(screen.getByText("Your answer has been received")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Continue" }));
  expect(onContinue).toHaveBeenCalled();
});

it("notes when the submission was unchanged", () => {
  render(<Confirmation unchanged onContinue={vi.fn()} />);
  expect(screen.getByText("No changes to your previous answer.")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- tests/components`
Expected: FAIL - `Cannot find module '@/components/interview/answer-input'`

- [ ] **Step 3: Implement the components**

`answer-input.tsx` is a controlled-by-self component: it holds local `mode: AnswerType`, `text`, and `file` state, initialised from `initialAnswer` (prefill `text` when `answer_type === "text"`; start in `"audio"` mode when `answer_type === "audio"`). The toggle is a `segmented-control` with two radios labelled `Type` and `Upload audio`. The textarea has `aria-label="Your answer"`; the file input has `aria-label="Audio file"` and `accept="audio/*"`. Submit is disabled while `submitting`, while `mode === "text"` and `text.trim() === ""`, or while `mode === "audio"` and `file === null`. The submit button label is `Submit answer`.

`question-card.tsx` renders `question.code`, `question.prompt`, `Progress`, and `AnswerInput`. `progress.tsx` renders `Question {index + 1} of {total}` plus a simple visual bar. `confirmation.tsx` renders `Your answer has been received`, the unchanged note when `unchanged`, and a `Continue` button calling `onContinue`. `ui/button.tsx` and `ui/textarea.tsx` are thin styled wrappers.

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- tests/components`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add components tests/components
git commit -m "feat: add answer input and progress components"
```

---

### Task 4: Interview flow state machine and routing

**Files:**
- Create: `app/interview/[token]/page.tsx`, `components/interview/interview-flow.tsx`, `components/interview/loading.tsx`, `components/interview/invalid-link.tsx`, `components/interview/completion.tsx`
- Test: `tests/components/interview-flow.test.tsx`

**Interfaces:**
- Consumes: `getInterview`, `submitTextAnswer`, `submitAudioAnswer`, `ApiError` from `lib/api` (Task 2); `QuestionCard`, `Confirmation` (Task 3).
- Produces: `InterviewFlowProps { token: string }`. `app/interview/[token]/page.tsx` is an async server component that does `const { token } = await params` and renders `<InterviewFlow token={token} />`.

- [ ] **Step 1: Write the failing tests**

Mock `@/lib/api` with `vi.mock("@/lib/api", ...)` and seed `localStorage` per test (clear it in `beforeEach`). Cases:

```tsx
it("shows loading then the first question", async () => {
  let resolve: (v: InterviewResponse) => void;
  (getInterview as any).mockReturnValue(new Promise((r) => (resolve = r)));
  render(<InterviewFlow token="tok" />);
  expect(screen.getByText("Loading")).toBeInTheDocument();
  resolve(interview());
  expect(await screen.findByText("Question 1 of 6")).toBeInTheDocument();
});

it("shows invalid-link on a 401", async () => {
  (getInterview as any).mockRejectedValue(new ApiError(401, "not found"));
  render(<InterviewFlow token="tok" />);
  expect(await screen.findByText("This interview link is not valid.")).toBeInTheDocument();
});

it("resumes at the stored question index", async () => {
  localStorage.setItem("talotrace:interview:tok:currentQuestion", "2");
  (getInterview as any).mockResolvedValue(interview());
  render(<InterviewFlow token="tok" />);
  expect(await screen.findByText("Question 3 of 6")).toBeInTheDocument();
});

it("falls back to the first unanswered question when stored index is malformed", async () => {
  localStorage.setItem("talotrace:interview:tok:currentQuestion", "abc");
  (getInterview as any).mockResolvedValue(interviewWithFirstAnswered());
  render(<InterviewFlow token="tok" />);
  expect(await screen.findByText("Question 2 of 6")).toBeInTheDocument();
});

it("shows completion when all questions are answered and nothing is stored", async () => {
  (getInterview as any).mockResolvedValue(interviewAllAnswered());
  render(<InterviewFlow token="tok" />);
  expect(await screen.findByText(/complete/i)).toBeInTheDocument();
});

it("submits, confirms, and advances with a re-fetch", async () => {
  (getInterview as any).mockResolvedValue(interview());
  (submitTextAnswer as any).mockResolvedValue({ status: "received", unchanged: false, answer: { answer_type: "text", version: 1, submitted_at: "t" } });
  render(<InterviewFlow token="tok" />);
  await screen.findByText("Question 1 of 6");
  await user.type(screen.getByLabelText("Your answer"), "my answer");
  await user.click(screen.getByRole("button", { name: "Submit answer" }));
  expect(await screen.findByText("Your answer has been received")).toBeInTheDocument();
  (getInterview as any).mockResolvedValue(interviewWithFirstAnswered());
  await user.click(screen.getByRole("button", { name: "Continue" }));
  expect(await screen.findByText("Question 2 of 6")).toBeInTheDocument();
});

it("shows an inline error when submit rejects", async () => {
  (getInterview as any).mockResolvedValue(interview());
  (submitTextAnswer as any).mockRejectedValue(new Error("network down"));
  render(<InterviewFlow token="tok" />);
  await screen.findByText("Question 1 of 6");
  await user.type(screen.getByLabelText("Your answer"), "x");
  await user.click(screen.getByRole("button", { name: "Submit answer" }));
  expect(await screen.findByText(/could not submit/i)).toBeInTheDocument();
});
```

The `interview()` helper returns six questions (Q1..Q6, all `answer: null`) with `progress: { answered: 0, total: 6 }`; `interviewWithFirstAnswered()` answers Q1 so the first unanswered is Q2; `interviewAllAnswered()` answers all six.

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- tests/components/interview-flow.test.tsx`
Expected: FAIL - `Cannot find module '@/components/interview/interview-flow'`

- [ ] **Step 3: Implement `interview-flow.tsx`**

State: `phase: "loading" | "invalid-link" | "error" | "ready" | "complete"`, `interview: InterviewResponse | null`, `currentIndex: number`, `submit: "idle" | "submitting" | "received" | "error"`, `submitError: string | null`, `lastUnchanged: boolean`.

On mount, call `getInterview(token)`; on `ApiError` with `status === 401` set `phase = "invalid-link"`, on other failure set `phase = "error"`, on success resolve the start index per §7.1 of the spec (stored valid index wins; else first `answer === null`; if all answered and nothing stored, `phase = "complete"`). Persist `currentIndex` to `localStorage` under `talotrace:interview:${token}:currentQuestion` on every change.

`handleSubmitText(text)` and `handleSubmitAudio(file)` call the matching `lib/api` function with `interview.questions[currentIndex].id`, set `submit = "submitting"`, then `"received"` on success (recording `res.unchanged` in `lastUnchanged`) or `"error"` with `submitError` on failure.

`handleContinue()` re-fetches `getInterview(token)`, updates `interview`, then either sets `phase = "complete"` (when `currentIndex` is the last question) or advances `currentIndex` by one; resets `submit = "idle"`.

Render: `loading.tsx` (text `Loading`) for `phase === "loading"`; `invalid-link.tsx` (text `This interview link is not valid.`) for `"invalid-link"`; a generic full-screen error (`Something went wrong. Please try again.`) for `"error"`; `completion.tsx` (text `You've completed all six questions.`) for `"complete"`; otherwise `QuestionCard` for the current question when `submit !== "received"`, and `Confirmation` when `submit === "received"`, plus a `Previous` button to revisit an earlier question. On submit error, render a message such as `Your answer could not be submitted. Please try again.` (matches `/could not submit/i`).

- [ ] **Step 4: Implement `app/interview/[token]/page.tsx`**

Async server component with `params: Promise<{ token: string }>`; `const { token } = await params;` then `return <InterviewFlow token={token} />;`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `npm test -- tests/components/interview-flow.test.tsx`
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add app components/interview/interview-flow.tsx components/interview/loading.tsx components/interview/invalid-link.tsx components/interview/completion.tsx tests/components/interview-flow.test.tsx
git commit -m "feat: add interview flow with resume and submit"
```

---

### Task 5: End-to-end interview flow

**Files:**
- Create: `e2e/interview.spec.ts`

**Interfaces:**
- Consumes: a running backend at `E2E_API_ORIGIN` (default `http://localhost:8000`) with a valid candidate token supplied as `E2E_CANDIDATE_TOKEN`. This token is created in the backend (see the backend README); this plan does not design the backend.

- [ ] **Step 1: Write the failing test**

Create `e2e/interview.spec.ts`:

```tsx
import { test, expect } from "@playwright/test";

test("answers, confirms, and resumes on the same question", async ({ page }) => {
  const token = process.env.E2E_CANDIDATE_TOKEN!;
  await page.goto(`/interview/${token}`);
  await expect(page.getByText("Question 1 of 6")).toBeVisible();
  await page.getByLabel("Your answer").fill("A proud piece of work");
  await page.getByRole("button", { name: "Submit answer" }).click();
  await expect(page.getByText("Your answer has been received")).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("Question 2 of 6")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Question 2 of 6")).toBeVisible();
});
```

- [ ] **Step 2: Run to verify it fails (no server/backend yet)**

Run: `E2E_CANDIDATE_TOKEN=<token> npx playwright test`
Expected: FAIL - backend not reachable or app not served

- [ ] **Step 3: Wire the E2E app-to-API base URL**

Set `NEXT_PUBLIC_API_ORIGIN` to the backend origin for the dev server used by Playwright (in `playwright.config.ts` webServer env or `.env.local`, which is git-ignored). Confirm the app boots against a running backend.

- [ ] **Step 4: Run to verify it passes**

Run: `E2E_CANDIDATE_TOKEN=<token> npx playwright test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add e2e playwright.config.ts
git commit -m "test: add end-to-end interview flow"
```

---

## Self-Review Notes

- Spec §5 routing, §6 client, §7 resume, §8 components, §9 errors, §10 env, §11 testing are each covered by Tasks 1-5.
- Task 3 owns Review Focus #4 (empty text) and part of #5 (file selection); Task 4 owns #1 (malformed stored index), #2 (network rejection), #5 (submit error path); Task 2 owns #3 (non-JSON body).
