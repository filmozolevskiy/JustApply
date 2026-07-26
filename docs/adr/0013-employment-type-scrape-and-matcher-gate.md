# 0013: Employment Type — scrape preference, matcher source of truth, attribute gate

## Status

Accepted.

## Context

Bright Data’s LinkedIn jobs discover API accepts a single `job_type` input and returns `job_employment_type` on listings. Live probes (Ontario) confirmed allowed values Full-time, Contract, Part-time, Temporary, and Volunteer; Internship and Other are rejected at validation. Filtering is discover-then-validate: mismatch rows arrive as errors when `include_errors=true`, so rare types can burn discoveries. JustApply had no Employment Type field, board refine, or gate.

ADR 0008 already made the Resume Matcher the classifier for remote type and seniority after evaluation. Employment Type needed the same clarity: scrape-time vs matcher ownership, multi-select vs Bright Data’s single `job_type`, and whether mismatches Reject.

## Decision

1. **Canonical term: Employment Type** — Full-time, Contract, Part-time, Temporary, Volunteer. Not “job type.”

2. **Dual path (persist + scrape preference)** — Store Employment Type on every job. Job Search Settings may select one or more types (default: none = “any”). Board Controls refine is multi-select (none checked = no type refine). Drawer Job Info shows the type; no Kanban card badge. Dashboard-only in v1; CLI treats Employment Type as “any.”

3. **Bright Data input only when exactly one type is selected** — Multi-select omits `job_type` and post-filters raw results to the selected set (same stage as company size). Exactly one still post-filters as a safety net for mismatch rows. “Any” neither sends nor post-filters by type. Unknown/blank scrape types drop when any preference is active.

4. **Resume Matcher wins** — After evaluation, matcher Employment Type is the stored source of truth (extends ADR 0008). Scraper value seeds the job and is the Unclassified poison fallback. Employment Type is part of the attribute gate with remote type and seniority when the run selected any types; “any” skips Employment Type in the gate. Gate prefs for search/backfill/reassess come from Job Search Settings at submit time (batch rounds persist them on the Batch Evaluation Job).

5. **Reassess gates, but only demotes Scraped/Matched** — Reassess refreshes matcher fields including Employment Type and applies the attribute gate from current Job Search Settings. Gate failure moves Scraped/Matched → Rejected; Accepted/Applied/Interviewing/Rejected keep their lane while fields still update.

## Considered Options

- **Board-only / scrape-only** — Rejected; dual path keeps credits controllable and board refine useful on stored types.
- **Fan-out one Bright Data input per selected type** — Rejected; surprise credit multiplication. Multi-select uses post-filter instead.
- **Scraper-only ownership (no matcher)** — Rejected in favor of matcher-wins consistency with remote/seniority.
- **No attribute gate for Employment Type** — Rejected; user wants Reject when prefs are set, same family as remote/seniority.
- **Reassess Reject from any lane** — Rejected; too destructive for jobs already being pursued.
