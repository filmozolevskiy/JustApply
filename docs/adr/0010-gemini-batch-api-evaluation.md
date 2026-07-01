# 0010: Asynchronous Gemini Batch API Evaluation with a Background Poller

## Status

Accepted — supersedes ADR 0011 (Parallel Batch Evaluation). The term "batch" is redefined: it now means an asynchronous **Batch Evaluation Job** submitted to the Gemini Batch API, not the prior prompt-packing-plus-parallel-HTTP strategy.

## Context

ADR 0011 evaluated jobs by packing 15 jobs into one prompt and firing up to 30 such prompts concurrently as live HTTP calls ("Prompt Packing"). This broke down for bulk work: backfilling ~2,661 historically-unevaluated jobs hammered the API into high error rates, and large packed prompts (~62K chars) hung and timed out. The client also used the deprecated `google.generativeai` library.

The Gemini Batch API is an asynchronous endpoint for exactly this: submit all requests once, poll, retrieve results, at 50% of interactive cost.

**Empirical measurement drove the design.** A probe submitting real JustApply payloads (resume + one job per request, file-based JSONL) measured turnaround on a single sample:

| Batch size | JSONL | Turnaround |
|---|---|---|
| 10 jobs | 91 KB | 17.8 min |
| 100 jobs | 1.0 MB | 8.5 min |
| 500 jobs | 5.0 MB | 23.8 min |

Turnaround is **queue-dominated, 8-24 min, with no correlation to size** — the smallest batch was the slowest. There is no fast path. This makes a blocking, interactive search untenable: a user would stare at a multi-minute spinner every search, and any reasonable timeout (e.g. 10 min) would routinely fire *before* the batch finished, falsely reporting failure while the batch quietly completed minutes later.

## Decision

Evaluation becomes fully asynchronous, with a two-lane board split and a background poller.

1. **Replace Prompt Packing with a Batch Evaluation Job everywhere.** Both search and backfill submit one asynchronous Gemini Batch API job. There is no live, per-request, parallel evaluation path.

2. **One job per request, keyed by `job_id`.** Each job is one line in a file-based JSONL submission carrying the single-job Resume Matcher prompt, with `response_mime_type: application/json` for structured output. Responses correlate to rows by `job_id`. This deletes the packed-prompt builder, index sorting, count-mismatch handling, and markdown-fence stripping. (Validated in the probe: results returned as clean per-key JSON.)

3. **Two new lanes: Scraped → Matched.** The board gains a raw, pre-evaluation lane (**Scraped**) and a post-evaluation lane (**Matched**). Flow: scrape → save instantly into **Scraped** (`matchType=''`) → Batch Evaluation Job → on success, write back scores and either move to **Matched** (passes the attribute gate) or **Rejected** (fails it). Triage (drag to Accepted) now happens from **Matched**.

4. **Async submit, never block.** Search scrapes, saves Scraped jobs, submits batches covering all Scraped jobs not already in flight, persists each batch job name, and returns immediately. Backfill is the same minus the scrape step (optional `--wait` to block inline for headless runs). `job_id` exists before submission because jobs are saved first.

4a. **Chunked fan-out for incremental results.** Because turnaround is independent per batch and queue-dominated (the probe's concurrently-submitted 10/100/500-job batches finished at 17.8/8.5/23.8 min), a submission is split into multiple Batch Evaluation Jobs of **100 jobs each** rather than one large batch, with at most ~10-15 in flight at once (further chunks submit as earlier ones finish). This does not reduce total completion time (the slowest chunk bounds it) but sharply reduces time-to-first-results: the **Batch Poller** writes back each chunk independently, so **Matched** fills incrementally and the user can triage early arrivals while later chunks are still processing. Most valuable for the ~2,661-job backfill (~27 chunks), which would otherwise be all-or-nothing. A search with ≤100 new jobs is a single chunk. Chunk size is a UX/robustness choice, not a limit constraint (a single 2,661-job batch is only ~24 MB against a 2 GB / 200,000-request ceiling).

4b. **Evaluation Lock — one round at a time.** While any Batch Evaluation Job is in flight, starting a new search or backfill is blocked, so rounds cannot overlap and pile up. The lock is *derived*, not stored: it is active whenever a `batch_jobs` row exists in a non-terminal state, so it is automatically correct across dashboard restarts. It releases when every in-flight batch reaches a terminal state — bounded by the 3-attempt poison rule and the ~48h expiry, so it cannot hang indefinitely. The lock is **global** (a running backfill blocks a new search and vice versa). A **Cancel** control aborts the in-flight set via `batches.cancel()`, leaving those jobs in **Scraped**, to release immediately. The dashboard disables the search/backfill controls with an "Assessing N jobs…" indicator; the CLI refuses with the same explanation. `--collect` is always allowed (it never submits).

5. **Background poller in the dashboard.** The FastAPI dashboard hosts a poller that, on startup, **resumes** in-flight batches (from a persisted `batch_jobs` record) and polls them; it does **not** auto-submit new batches (spend stays tied to explicit actions). Poll cadence, reconstructed from each batch's `submitted_at` so it survives restarts: every **1 min** for 0-10 min, **2 min** for 10-40 min, **5 min** for 40 min-3 h, then **15 min** until the batch reaches a terminal state or Google expires it (~48 h). A `--collect` CLI command does a one-shot poll/write-back for headless use.

6. **Terminal handling and poison jobs.** `SUCCEEDED` → write back + move cards. `FAILED`/`EXPIRED`/`CANCELLED` (whole job), or a failed/malformed per-request line, leaves that job in **Scraped** for resubmission, incrementing a per-job attempt count. After **3** failed attempts, fall back to scraper-derived `remoteType`/`seniority`, mark the job **Unclassified**, and move it to **Matched** so it leaves Scraped and stops being re-billed.

7. **Migrate to `google.genai` and keep a synchronous path.** Replace the deprecated client. A synchronous `generate_text` is retained for the interactive single-job reassess path and the Outreach Generator.

8. **One-time data migration.** Every unscored job → **Scraped** (this resurfaces ~1,136 unscored `rejected` jobs for evaluation); scored `found` jobs → **Matched** (~59); scored `rejected` and downstream lanes unchanged. Result: 2,661 Scraped, 59 Matched, 392 Rejected. The status enum becomes `{scraped, matched, accepted, applied, interviewing, rejected}` (rename `found` → `scraped`, add `matched`); `add_job` defaults to `scraped`.

## Implementation notes

- **Persistence.** New `batch_jobs` table: `id`, `batchName` (Gemini `batches/...` resource, unique), `displayName`, `state` (`JOB_STATE_*`), `kind` (`search`/`backfill`), `submittedAt` (drives poll cadence), `lastPolledAt`, `resultFileName` (nullable), `jobIds` (JSON array of member `job_id`s). Plus a `jobs.batchAttempts` (INTEGER, default 0) column for the poison-job counter. The Evaluation Lock is `SELECT 1 FROM batch_jobs WHERE state NOT IN (terminal)`.
- **`--collect`.** One-shot: poll all in-flight batches, write back completed ones, exit (cron-friendly). `--collect --wait` loops on the poll cadence until all in-flight batches are terminal. Never submits.
- **Logging.** Poller emits Task Logs/SSE on events only (submitted, chunk completed with matched/rejected counts, failed/expired, poison fallback) — never per poll tick. Dashboard shows a derived "Assessing N jobs…" indicator and a Cancel control.
- **Dependency.** Add `google-genai` to `requirements.txt`; remove `google-generativeai` once the client and Resume Import are migrated.

## Considered Options

- **Keep Prompt Packing for interactive search, Batch for backfill only** — rejected; a single async path everywhere is simpler and the measured turnaround makes live search impossible anyway.
- **Blocking search with a timeout, then error** — rejected after measurement: 8-24 min turnaround means timeouts fire before completion and the spinner is intolerable.
- **Collect results only on the next search/backfill run** (no poller) — rejected; the user wants scores to fill in automatically without re-running a command.
- **Auto-submit batches on dashboard startup** — rejected; keeps spend predictable and consistent with existing Apify spend gating.
- **Pack ~15 jobs per request** — rejected; per-request `job_id` keys plus 50% pricing make packing pointless and it reintroduces fragile parsing and a wide partial-failure blast radius.
- **Retry poison jobs forever** / **dead-letter state** — rejected in favor of bounded retries (3) then the existing Unclassified fallback.

## Consequences

- **Interactive search no longer returns scored jobs.** Cards appear instantly in **Scraped** and gain scores minutes later when the batch lands. Sort-by-score is meaningless for Scraped cards until then.
- **Cost drops ~50%** on evaluation, and bulk backfill no longer triggers rate-limit storms.
- **The evaluation code simplifies**: no semaphores, no per-batch sequential fallback, no index/count-mismatch parsing, no fence stripping.
- **New persistence**: a `batch_jobs` table (batch name, `submitted_at`, state, member `job_id`s) and a per-job batch attempt count.
- **Search and backfill converge** into one submit → poll → write-back path; backfill is search without scraping.
- **Attribute-filtered jobs are persisted, not discarded.** Today search `continue`s past gate failures without saving them, so a re-scrape re-sends them to Gemini every time. Save-first persists them (gate failures → `rejected`), so `job_exists` skips them on re-scrape and `get_unevaluated_jobs()` never re-batches them. Dedup stays keyed on the existing link / title+company match — verified collision-free against the live DB (3,105 distinct LinkedIn job IDs, zero duplicate rows), so no dedup-key change is needed.
- **Batch creation is not idempotent** — the in-flight `batch_jobs` record guards against double-submitting jobs already covered by a running batch.
- **Status enum changes.** Recommended: introduce `scraped` and `matched` status values (label "Scraped"/"Matched") and migrate the old `found` rows accordingly; a lower-churn alternative is to reuse `found` internally for the Scraped lane and add only `matched`.
