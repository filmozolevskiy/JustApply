# [PRD] Contacted Elsewhere Performance

> **GitHub Issue:** [#110](https://github.com/filmozolevskiy/JustApply/issues/110)

## Problem Statement

Every time the **Kanban Dashboard** loads jobs or opens a job drawer, the system recomputes **Contacted Elsewhere** indicators by scanning the entire **Job Tracker Database**. As the number of saved jobs and contacts grows, board refresh and drawer open become slower even when the user only views one card. This work is invisible to the user but degrades daily use of the dashboard.

## Solution

Replace the full-table scan with an indexed or cached lookup keyed by normalized LinkedIn profile identity, so **Contacted Elsewhere** enrichment runs in time proportional to the contacts on the jobs being displayed — not total historical jobs.

## User Stories

1. As a job seeker, I want the **Kanban Dashboard** to load quickly even with hundreds of saved jobs, so that daily triage stays responsive.

2. As a job seeker, I want opening a job drawer to feel instant, so that reviewing contacts is not sluggish.

3. As a job seeker, I want **Contacted Elsewhere** indicators to remain accurate after I mark someone contacted on another job, so that I do not double-message the same person.

4. As a job seeker, I want **Contacted Elsewhere** to update after I toggle contacted on the current job's contact row, so that cross-job hints stay current on refresh.

5. As a job seeker, I want **Contacted Elsewhere** to ignore archived jobs only when product rules say so, so that behavior matches existing domain expectations.

6. As a job seeker, I want the indicator to match normalized LinkedIn URLs (`/in/{slug}`), so that the same person on different URL variants still deduplicates.

7. As a maintainer, I want a performance regression test that fails if contact enrichment reintroduces full-table scans on single-job reads, so that future changes do not silently regress.

8. As a maintainer, I want **Contacted Elsewhere** recomputation to run when contacts or contacted flags change, so that the index/cache stays consistent without rereading all jobs on every GET.

9. As a maintainer, I want CLI and dashboard reads to share one implementation, so that behavior does not diverge.

10. As a job seeker, I want SSE job refresh after enrichment to show **Contacted Elsewhere** correctly on newly added contacts, so that enriched cards match drawer detail.

11. As a job seeker, I want **Load More Contacts** appended profiles to show **Contacted Elsewhere** when applicable, so that newly loaded rows behave like first-page contacts.

12. As a maintainer, I want migration/upgrade safe for existing databases, so that users with large `just_apply.db` files do not need manual steps.

## Implementation Decisions

- Introduce a persistent index or materialized map from normalized LinkedIn slug → list of `{job_id, contact display fields}` where `contacted=true`, updated on writes that touch contacts or contacted flags.
- Alternative acceptable approach: in-memory cache with explicit invalidation on contact mutations, if persistence is unnecessary — prefer persistent index if it simplifies correctness across dashboard restarts.
- **Single-job fetch** must not load all jobs; **list jobs** may batch-enrich only the returned page's contacts using the shared index.
- Normalization rules must match existing **Contacted Elsewhere** tests (URL variants, same slug).
- **Job Backup** rows in `jobs_backup` (if present) remain excluded per domain glossary — index only live job contacts unless tests specify otherwise.
- Index maintenance hooks belong at contact update, enrichment persist, load-more append, and re-classify paths that rewrite contact arrays.

## Testing Decisions

Test observable contact payload fields (`contactedElsewhere` or equivalent) and query counts — not private cache structure names.

- **Modules under test:** job read paths, contact mutation paths, contacted-elsewhere enrichment helper.
- **Prior art:** `test_contacted_elsewhere.py` scenarios; dashboard job list tests asserting indicator presence.
- **New cases:**
  - Large fixture DB (synthetic N jobs) — single `get_job` does not execute O(N) full-table load (assert via spy/mock on bulk loader or query counter seam).
  - After marking contacted on job A, job B's shared contact shows indicator.
  - After enrichment adds contacts, indicators appear without manual rebuild.
- **Seam:** highest existing seam is the job DB read API returning enriched `Job` models; add optional test hook to count bulk loads if no query counter exists yet.

## QA Validation

- [ ] Load the **Kanban Dashboard** with a populated database → board renders without noticeable delay versus pre-change baseline on the same data.
- [ ] Open a job drawer with multiple contacts → **Contacted Elsewhere** badges appear on rows where the same LinkedIn person was marked contacted on another job.
- [ ] Mark a contact contacted on one **Accepted Job**, refresh the board, open a second job sharing that profile → indicator visible on the second job.
- [ ] Run **Enrich Job** on a role whose contacts overlap prior jobs → new contact rows show **Contacted Elsewhere** where expected.

## Out of Scope

- Changing **Contacted Elsewhere** UX copy or making the indicator editable.
- Cross-database or multi-user sync (local SQLite single-user tool).
- Archival/auto-archive rule changes.
- Full-text search or **Board Search** performance (separate concern).

## Further Notes

This is pure infrastructure improvement; user-visible behavior must remain identical to current **Contacted Elsewhere** semantics. Any intentional behavior change requires a separate PRD.
