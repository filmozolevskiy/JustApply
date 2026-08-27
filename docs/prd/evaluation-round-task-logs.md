# [PRD] Evaluation Round Task Logs

> **GitHub Issue:** [#161](https://github.com/filmozolevskiy/JustApply/issues/161)

## Problem Statement

After a job search completes, **Task Logs** show how many listings were scraped, deduplicated, and saved to **Scraped**, but not how many were filtered out once the **Resume Matcher** and attribute gate run. Evaluation happens asynchronously via the **Batch Poller** minutes later; those outcomes are invisible in the console the user watches during search. The user cannot answer “how many jobs did the LLM attribute gate reject?” without manually counting cards in **Rejected**.

## Solution

Surface **Batch Poller** evaluation outcomes in **Task Logs** using aggregate counters only: per-chunk summaries as each **Batch Evaluation Job** completes, plus a final **Evaluation Round Summary** when the **Evaluation Lock** clears. Split rejections into **attribute-filtered** (post-LLM gate) and **fallback-rejected** (Unclassified poison path). Wire the dashboard to an always-on batch-poller SSE stream so evaluation lines appear in the same **Task Logs** panel as scrape logs. Emit identical lines on the CLI `--collect` path.

## User Stories

1. As a job seeker, I want to see how many jobs moved to **Matched** after evaluation, so that I know how many roles are worth triaging.

2. As a job seeker, I want to see how many jobs were **attribute-filtered** after the **Resume Matcher** ran, so that I understand how many listings failed remote-type or seniority preferences.

3. As a job seeker, I want **attribute-filtered** counts separate from **fallback-rejected** counts, so that I can tell LLM-classified rejections apart from scraper-fallback rejections.

4. As a job seeker, I want per-chunk evaluation summaries while batches are still running, so that I can start triaging early **Matched** cards before the whole round finishes.

5. As a job seeker, I want one **Evaluation Round Summary** when all in-flight batches finish, so that I get a single footer total for the round.

6. As a job seeker, I want evaluation summaries in the same **Task Logs** panel as scrape logs, so that I do not hunt a separate console.

7. As a job seeker, I want evaluation summaries to appear after a page reload while batches are still in flight, so that I do not lose observability mid-round.

8. As a job seeker, I want the round summary to label whether the round was **search** or **backfill**, so that I know which action produced the numbers.

9. As a job seeker, I want backfill rounds to emit the same evaluation log format as search, so that observability is consistent across pipeline entry points.

10. As a job seeker, I want evaluation logs to stay count-only without per-job `Attribute mismatch` lines, so that large searches remain readable.

11. As a job seeker, I want failed evaluation attempts (jobs still in **Scraped** awaiting retry) reported separately from rejections, so that I know when results are incomplete.

12. As a job seeker, I want **Unclassified** poison fallbacks that passed the gate reported in summaries, so that I understand how many cards landed in **Matched** without LLM classification.

13. As a job seeker running the CLI, I want `--collect --wait` to print the same chunk and round summaries as the dashboard, so that headless runs are equally observable.

14. As a job seeker running the CLI, I want the `--collect` footer to use the split rejection counters, so that terminal output matches dashboard totals.

15. As a maintainer, I want the **Batch Poller** to remain the single emission point for evaluation log lines, so that dashboard SSE and CLI stderr stay aligned.

16. As a maintainer, I want per-job attribute rejection log calls removed from the poller, so that dead log volume does not accumulate in memory.

17. As a maintainer, I want **CollectResult** (or its successor summary shape) to carry split rejection counters, so that aggregation and CLI footers stay consistent.

18. As a maintainer, I want round totals accumulated across all chunks in one evaluation round, so that the final summary is correct when search submits multiple **Batch Evaluation Jobs**.

19. As a maintainer, I want glossary terms in **CONTEXT.md** to reflect **Attribute-filtered Job**, **Fallback-rejected Job**, and **Evaluation Round Summary**, so that docs match runtime language.

20. As a job seeker, I want scrape summaries and evaluation summaries visually distinct (summary log level), so that I can scan the console for each phase.

21. As a job seeker, I want evaluation logs to exclude **Enrichment** activity, so that contact-sourcing logs do not mix with evaluation filtering counts.

22. As a job seeker, I want no new per-job entries in the **Job Activity Log** for attribute rejections, so that drawer history stays focused on actions I took.

## Implementation Decisions

- **Scope:** Resume Matcher + attribute gate outcomes only (**Scraped → Matched** / **Rejected**). Out of scope: scraper company-size post-filter aggregates, **Enrichment** logging changes, **Job Activity Log** attribute rejection entries.

- **Counter split:** Replace the single `rejected` bucket in poller summaries with:
  - `attribute-filtered` — `write_back_job_evaluation` returned rejected after a successful **Resume Matcher** result.
  - `fallback-rejected` — `apply_unclassified_fallback` returned rejected (scraper attributes gated out after poison exhaustion).
  - Retain `matched`, `failed` (retry still in **Scraped**), and `unclassified` (poison fallback that passed the gate).

- **Chunk log line:** Emit a `summary`-level line when each batch reaches `JOB_STATE_SUCCEEDED`, listing all five counters for that chunk.

- **Round summary:** When the **Evaluation Lock** transitions from active to inactive (no in-flight **Batch Evaluation Jobs**), emit one `summary`-level **Evaluation Round Summary** totaling counters across every chunk processed in that round. Include round kind (`search` or `backfill`) derived from the batch rows' `kind` field (homogeneous per round due to the global lock).

- **Round accumulation:** Track running totals in the poller loop across chunk completions within the current lock cycle; reset when the lock clears after emitting the round summary.

- **Remove per-job logs:** Delete `Attribute mismatch` per-job log emission from the poller; rejected jobs remain visible on the board in **Rejected**.

- **Dashboard delivery:** Subscribe the **Task Logs** panel to `/api/batch-poller/logs` SSE for the full dashboard session (always-on), reusing the existing task log client message handler and session log persistence. Support `skip` replay on connect so reload mid-round catches up.

- **Search task stream unchanged:** The search `/api/logs/{task_id}` stream still closes after scrape + batch submission; evaluation lines arrive via the batch-poller stream.

- **CLI parity:** Route poller `log_func` output to stderr for `--collect`; update the collect footer to print split counters and align naming with dashboard summaries.

- **CollectResult shape:** Extend the poller result object and `_summarize_collect_results` to expose `attribute_filtered` and `fallback_rejected` instead of a combined `rejected` field (update all callers and tests).

- **No schema changes:** No new DB columns; batch `kind` already distinguishes search vs backfill.

- **Documentation:** **CONTEXT.md** already defines **Attribute-filtered Job**, **Fallback-rejected Job**, and **Evaluation Round Summary**; keep aligned during implementation.

## Testing Decisions

Good tests assert external behavior — log message text, log levels, SSE payloads, CLI stderr/stdout, and summary counter totals — not private accumulator variable names.

**Preferred seams (highest first):**

1. **Batch poller collection with `log_func` callback** — mock Gemini batch download JSONL; assert chunk summary lines and returned counter totals. Prior art: `tests/test_batch_poller.py` (`collect_batch_results`, `write_back_job_evaluation`).

2. **Round summary on lock clear** — seed multiple terminal batches in one round; run one poller iteration or `poll_in_flight_batches` with mocked empty in-flight afterward; assert a single round summary line with aggregated totals. Prior art: `tests/test_batch_poller.py`, `tests/test_collect_cli.py`.

3. **CLI `--collect` footer** — assert stderr chunk lines and stdout footer include split counters. Prior art: `tests/test_collect_cli.py`.

4. **Batch-poller SSE endpoint** — HTTP test that `/api/batch-poller/logs` replays buffered poller log entries in SSE shape. Prior art: `tests/test_log_stream.py`.

5. **Dashboard JS wiring** — static or module test that dashboard startup connects batch-poller SSE through the task log client (no duplicate EventSource handlers). Prior art: `tests/test_dashboard_modules.py`, `tests/kanban_js.py`.

**New cases:**

- Post-LLM attribute gate failure increments `attribute-filtered`, not `fallback-rejected`.
- Poison fallback rejection increments `fallback-rejected`.
- Chunk summary uses `summary` log level.
- Round summary fires once when last in-flight batch completes.
- Per-job `Attribute mismatch` strings are not emitted.

## QA Validation

- [ ] On the **Kanban Dashboard**, run a job search (mock or real) and wait for evaluation to finish → **Task Logs** show at least one chunk summary with matched and rejection counts, then a round summary when assessing completes.
- [ ] After search completes but before evaluation finishes, reload the dashboard → **Task Logs** still receive evaluation chunk lines without starting a new search.
- [ ] Run a backfill from the dashboard (or CLI backfill if exposed) and wait for completion → **Task Logs** or terminal show evaluation summaries labeled as a backfill round.
- [ ] Run `python3 -m src.cli --collect --wait` while batches are in flight → terminal stderr shows chunk summaries and the footer reports split rejection counters.
- [ ] Complete a search where some jobs land in **Rejected** → rejected cards appear on the board; **Task Logs** do not list individual job titles for those rejections.

## Out of Scope

- Aggregate scraper post-filter counts (company size, keyword, timezone).
- Per-job `Attribute mismatch` lines in **Task Logs** or **Job Activity Log**.
- Linking search `task_id` to batch job rows for a single combined SSE stream.
- Changing **Batch Poller** poll cadence or **Evaluation Lock** semantics.
- **Enrichment** / Contact Sample logging changes.
- Dashboard UI beyond wiring batch-poller SSE into existing **Task Logs**.

## Further Notes

- Decisions were finalized in a domain review session; **CONTEXT.md** glossary entries were added ahead of implementation.
- This extends ADR 0010 logging intent (chunk completed + event-only poller logs) and supersedes ADR 0008's combined `rejected` counter in favor of split buckets.
- Example target log sequence:

  ```
  Pipeline complete. Scraped: 150 | Duplicates skipped: 12 | Saved to Scraped: 138 | Batch jobs submitted: 2
  Batch chunk completed: 95 matched, 3 attribute-filtered, 1 fallback-rejected, 0 failed, 1 unclassified
  Batch chunk completed: 38 matched, 0 attribute-filtered, 0 fallback-rejected, 0 failed, 0 unclassified
  Evaluation round complete (search): 133 matched, 3 attribute-filtered, 1 fallback-rejected, 0 failed, 1 unclassified
  ```
