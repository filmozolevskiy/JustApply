# [PRD] Enrichment Pipeline Hardening

> **GitHub Issue:** [#109](https://github.com/filmozolevskiy/JustApply/issues/109)

## Problem Statement

When enrichment infrastructure fails early — for example, when **Outreach Settings** cannot be read from the **Job Tracker Database** — the enrichment pipeline can crash with an internal error instead of recording an **Enrichment Note** and completing gracefully. The user sees a broken task rather than a recoverable failure on their **Accepted Job** card. Related enrichment lifecycle code also has fragile error boundaries and no automated test for this failure mode.

## Solution

Harden the enrichment pipeline so every failure path produces a predictable outcome: an **Enrichment Note** on the **Accepted Job**, both **Outreach Message Templates** still generated when contacts are empty, and Task Logs that explain what went wrong. Initialize safe defaults before optional steps so downstream template generation never references undefined state.

## User Stories

1. As a job seeker, I want **Enrich Job** to finish with an **Enrichment Note** when settings cannot be loaded, so that I understand what failed instead of seeing a silent crash.

2. As a job seeker, I want enrichment failures to keep my job in the **Accepted** lane, so that my board layout stays stable.

3. As a job seeker, I want **Enrichment Failure** to still produce Recruiter and Russian Speaker **Outreach Message Templates**, so that I can cold-connect manually even when contact sourcing failed.

4. As a job seeker, I want Task Logs to show a clear error when enrichment infrastructure fails, so that I can retry or fix configuration.

5. As a job seeker, I want partial enrichment warnings (e.g. one audience stream empty) to appear as warnings, not hard failures, so that I know when **Load More Contacts** might help.

6. As a job seeker, I want **Enrich Job** on an **Accepted Job** that already has contacts to re-run classification and templates without losing prior work unexpectedly, so that re-enrichment is predictable.

7. As a job seeker, I want **Load More Contacts** to behave consistently with **Enrich Job** when errors occur, so that error messaging follows the same patterns.

8. As a maintainer, I want enrichment orchestration to use a single coordinator entry point for status transitions, so that **Found**/**Matched**/**Accepted** rules stay in one place.

9. As a maintainer, I want automated tests covering settings-load failure during enrichment, so that regressions are caught before release.

10. As a maintainer, I want automated tests covering enrichment when contact sourcing raises, so that **Enrichment Note** text is always persisted.

11. As a maintainer, I want automated tests covering the warning path when one **Outreach Audience** stream is empty but the other is not, so that **enrichmentNoteKind** stays `warning`.

12. As a maintainer, I want the CLI `--promote` path to share the same hardened enrichment behavior as the **Kanban Dashboard**, so that both surfaces behave identically.

13. As a job seeker, I want **Re-classify** failures to surface as drawer-visible notes or Task Log errors, so that free LLM actions still fail gracefully.

14. As a maintainer, I want enrichment background tasks on the dashboard to always clear in-progress UI state when the pipeline returns, so that spinner badges do not stick.

15. As a job seeker, I want **Enrichment Note** cleared on successful re-enrichment, so that stale failure text does not linger.

## Implementation Decisions

- Initialize **Outreach Settings** to documented defaults before attempting to read persisted settings or source contacts. If reading settings fails, record an **Enrichment Note** describing the failure and proceed to template generation with defaults.
- Ensure template generation never depends on variables assigned only inside a guarded block that may not run.
- Keep **Accepted Job** status unchanged on infrastructure failure; only **Enrichment Note** and templates update.
- Preserve existing coordinator behavior: **Enrich Job** moves **Scraped** or **Matched** jobs to **Accepted** before sourcing; in-flight enrichment keeps the card in **Accepted**.
- Do not change Apify spend rules, **Contact Sample Cache** semantics, or **Spend Confirmation** flows in this PRD.
- Consolidate duplicate enrichment-note assembly only where it reduces drift between **Enrich Job**, **Load More Contacts**, and **Re-classify** — without changing user-visible copy.
- Deprecate or stop exporting the legacy DB-only enrichment start helper if the coordinator remains the sole owner of status transitions; update callers and tests accordingly.

## Testing Decisions

Good tests assert external behavior: persisted **Enrichment Note**, template fields, job status, and Task Log lines — not private variable assignment order.

- **Modules under test:** enrichment pipeline orchestration, service adapter that invokes it, dashboard enrichment background task wiring.
- **Prior art:** existing enrichment pipeline tests that mock contact sourcing and settings reads; partial enrichment warning tests; coordinator tests requiring **begin_enrichment** before pipeline run.
- **New cases:**
  - Settings read raises → job stays **Accepted**, **Enrichment Note** set, templates still written, no unhandled exception.
  - Contact sourcing raises → same outcome pattern.
  - Warning path when one audience stream empty → `enrichmentNoteKind` is `warning`, job still enriched with partial contacts.
- **Seams:** mock the settings reader and contact sourcer at the pipeline boundary; assert DB row fields via existing job fetch helpers used in tests today.

## QA Validation

- [ ] On the **Kanban Dashboard**, open an **Accepted Job** and click **Enrich Job** when the app is configured normally → enrichment completes or shows a readable **Enrichment Note**; card stays in **Accepted**.
- [ ] After a successful enrichment, open the job drawer → Recruiter and Russian Speaker templates are present or sensibly empty with an explanatory note.
- [ ] Trigger **Re-classify** on an enriched **Accepted Job** → templates refresh or a visible error/note appears; card does not leave **Accepted**.
- [ ] Run `python3 -m src.cli --promote` on a **Matched Job** with valid env → promotion/enrichment completes without traceback in the terminal.

## Out of Scope

- Multi-worker / multi-process coordinator state (single local dashboard process remains the assumption).
- Apify pricing, cache keying, or **Load More Contacts** pagination policy changes.
- Rewriting **Outreach Generator** prompts or **Complete Outreach** skeleton text.
- Performance work on **Contacted Elsewhere** (separate PRD).

## Further Notes

This PRD addresses the highest-severity defect from the codebase audit: enrichment can raise an internal error when settings loading fails before template generation. Other enrichment reliability items (coordinator in-memory prior-status map) remain acceptable for localhost single-process use but should not block this fix.
