# Interview Scoring - Groq Audio Transcription Design

**Date:** 2026-11-08
**Status:** Approved for planning
**Repo:** private monorepo
**Amends:** `2026-10-18-backend-design.md` (section 2 scope, section 9 audio enqueue, section 10 scoring pipeline)
**Related:** `2026-10-18-api-contract-design.md`, `2026-10-18-hr-web-design.md`

## 1. Goal

Transcribe audio answers with the Groq Whisper API inside the existing scoring background worker, then feed the transcript to the existing DeepSeek scoring path.

Audio answers should reach `scored` automatically when transcription and scoring succeed.
Human review remains the fallback when transcription cannot produce usable text.

## 2. Scope

In scope:

- Enqueue live and imported audio answers as `queued` (same as text).
- Extend `ScoringWorker` to transcribe audio before calling `ScoringLlmPort`.
- Persist successful transcripts on `answers.text` while keeping `audio_key` for playback.
- Add a `TranscriptionPort` and Groq Whisper adapter.
- Config, tests, README/deploy env documentation updates for Groq.

Out of scope:

- Migrating or auto-requeueing existing `needs_a_person` rows from phase 1.
- Extending `POST /hr/scoring-jobs/{id}/retry` to accept `needs_a_person` (retry stays `failed`-only).
- Non-English transcription, language auto-detect, or confidence thresholds.
- Human transcript editing UI.
- Chunking or special handling for files beyond Groq's documented upload limits.
- HR-web redesign beyond showing `text` when the detail payload already includes it.

## 3. Locked Decisions

| Topic | Decision |
|---|---|
| Integration shape | Single worker claim: transcribe (if needed) then score |
| Transcription provider | Groq OpenAI-compatible `POST /openai/v1/audio/transcriptions` |
| Default model | `whisper-large-v3` |
| Language | English only (`language=en`) |
| Transcript storage | Write non-empty Groq output to `answers.text`; keep `audio_key` |
| Live + import enqueue | Both use `status=queued` for audio |
| Existing `needs_a_person` rows | Leave unchanged; never auto-claimed |
| Transcription exhaustion | `needs_a_person` (HR can listen and override) |
| Scoring exhaustion after transcript saved | `failed` (existing text path); transcript retained |
| Empty / whitespace transcript | Counts as transcription failure |
| Answer already has text | Skip Groq; score with existing text |
| Retry endpoint | Unchanged: only `failed` -> `queued` |
| Attempt counter | One shared `attempt_count` for transcribe + score on the job |
| Schema | No new tables or status enum values |

## 4. Design

### 4.1 Why one worker step

Audio already shares the `scoring_jobs` row and claim loop with text.
A second status machine or second worker pool would add lease and retry complexity without a clear product need.
One claim that runs Groq then DeepSeek matches the requested "same background job" behavior and stays close to the current `ScoringWorker`.

Lease time may need a modest increase so both network calls fit one claim.
That is a config tweak, not a new subsystem.

### 4.2 Pipeline

1. Candidate audio submit or data-pack audio import creates or resets the scoring job to `queued`.
2. A worker claims the next `queued` job with `FOR UPDATE SKIP LOCKED` as today.
3. The worker loads scoring input (question prompt, grading guide, answer).
4. If `answer_type == audio` and `text` is missing or blank:
   - Read audio bytes from `FileStorage` using `audio_key`.
   - Call `TranscriptionPort.transcribe(data, filename=..., language="en")`.
   - On non-empty transcript, persist `answers.text = transcript`.
5. Call `ScoringLlmPort.score(prompt, grading_guide, answer_text)` with the transcript (or existing text).
6. Mark the job `scored` with suggested score/reasoning and set `final_score = suggested_score`, as today.

### 4.3 Status outcomes

| Stage | On exhaustion of `scoring_max_attempts` | Side effects |
|---|---|---|
| Transcription (transport, API error, missing audio file, empty transcript) | `needs_a_person` | `last_error` set; no scores; `answers.text` left null/blank |
| Scoring after transcript saved | `failed` | Existing failure path; `answers.text` retained |

Pre-existing `needs_a_person` jobs are not claimed and are not migrated.
HR can still override scores on `scored` and `needs_a_person` via the existing override rules.

### 4.4 Components

**Port** (`scoring/application/ports.py`):

```python
class TranscriptionPort(Protocol):
    async def transcribe(
        self,
        data: bytes,
        *,
        filename: str,
        language: str = "en",
    ) -> str: ...
```

`TranscriptionError` covers transport and API failures.
The worker (or adapter) treats empty/whitespace output as a transcription failure.

**Adapter** (`scoring/infrastructure/groq_transcription.py`):

- `httpx.AsyncClient` multipart POST to `{groq_base_url}/audio/transcriptions`
  (base URL default `https://api.groq.com/openai/v1`).
- Authorization bearer `groq_api_key`.
- Form fields: `file`, `model`, `language=en`, `response_format=json`.
- Default model `whisper-large-v3`.
- Supported pack/live formats already used by the product (notably `.m4a`) are within Groq's documented types.

**Worker** (`ScoringWorker`):

- Gains dependencies on `TranscriptionPort` and `FileStorage` (read by `audio_key`).
- Branches in `_process` per section 4.2.
- `TranscriptionError` (and empty-transcript handling) routes through failure recording with terminal status `needs_a_person`.
- All other processing errors keep today's terminal status `failed`.
- One shared `attempt_count` covers both stages on the same job.
  A job that burns attempts on Groq has fewer left for DeepSeek; that is accepted YAGNI versus a second counter.

**Enqueue** (`AnswersService.submit_audio`, `import_answer`):

- Pass `status="queued"` for audio instead of `needs_a_person`.

**Repository**:

- Add an update path to set `answers.text` after successful transcription.
- Extend failure recording so a job can terminate as `needs_a_person` with `last_error`.

### 4.5 Config

Add to `Settings`:

| Env / field | Default | Notes |
|---|---|---|
| `groq_api_key` | `""` | Required in environments that process audio |
| `groq_model` | `whisper-large-v3` | |
| `groq_base_url` | `https://api.groq.com/openai/v1` | OpenAI-compatible root |

Consider raising the default `scoring_lease_timeout_seconds` enough to cover Groq + DeepSeek under load.
Exact value is chosen during implementation with a short justification in the plan.

Wire the Groq adapter in `main.py` the same way `DeepSeekLlm` is wired.
Document the new vars in backend README, docker-compose, and deploy env examples.

### 4.6 API and HR surface

No request/response shape changes are required.
Audio answers already expose `text` and `audio_key` conceptually; after transcription, HR detail can show the transcript beside the existing audio player.
Import summary field `audio_answers_needing_person` should reflect reality after this change: fresh successful imports enqueue audio as queued jobs, so that count is `0` unless some other path still creates `needs_a_person`.
Smoke/e2e expectations that assert happy-path audio stays `needs_a_person` must be updated to expect `scored` when Groq (or a fake) succeeds.

### 4.7 Error handling details

- Missing `audio_key` or unreadable storage object: transcription failure.
- Groq non-2xx or malformed body: transcription failure.
- Blank transcript: transcription failure; do not persist blank text.
- After a transcript is saved, later scoring retries skip Groq because `answers.text` is present.
- `POST /hr/scoring-jobs/{id}/retry` remains valid only for `failed` jobs.
  A `needs_a_person` job is resolved by HR override (listen to audio), not by retry.

### 4.8 Testing

Unit (fake `TranscriptionPort`):

- Audio without text: transcribe -> save text -> score -> `scored`.
- Empty transcript: retry then `needs_a_person`.
- Scoring failure after saved transcript: eventually `failed`, text retained.
- Audio that already has text: skip transcription.
- Text answers: unchanged path (no transcription calls).

Service:

- `submit_audio` and import audio enqueue `queued`.

E2E / smoke:

- Imported or uploaded audio reaches `scored` with fake or configured Groq.
- Happy-path assertions no longer require `needs_a_person` for new audio.
- Existing leftover `needs_a_person` rows (if present in a fixture) remain unclaimed.

CI must not call the real Groq API.

## 5. Amendments to prior specs

Relative to `2026-10-18-backend-design.md`:

- Phase-1 "audio stored only / needs_a_person" is replaced for **new** audio by transcribe-then-score.
- Section 9/10 enqueue rules change: audio uses `queued`, not `needs_a_person`.
- `needs_a_person` remains a valid status for transcription exhaustion and for historical rows.
- LLM adapter section gains a sibling transcription adapter; scoring protocol itself is unchanged.

Where this document and the older backend design disagree on audio scoring, this document wins.

## 6. Traceability

| Requirement | Design guarantee |
|---|---|
| Transcribe in the same background job before scoring | Single `ScoringWorker` claim runs Groq then DeepSeek |
| HR can still handle bad audio | Transcription exhaustion -> `needs_a_person` + audio playback |
| Transcript visible with audio | Persist to `answers.text`; keep `audio_key` |
| Do not disturb old human-review rows | No migration; old `needs_a_person` not claimed |
| Import behaves like live upload | Both enqueue `queued` |
| English interviews | Hard-coded `language=en` |
| Scoring failure after transcript | `failed` with text retained; retry re-scores without Groq |
| No schema churn | Reuse `answers.text` and existing statuses |
