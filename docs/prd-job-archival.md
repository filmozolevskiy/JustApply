# [PRD] Job Archival Lifecycle

## Problem Statement

Rejected jobs accumulate on the Kanban Dashboard indefinitely, cluttering the **Rejected** lane with listings the user has already dismissed. The user still needs those rows in the Job Tracker Database so the Search & Evaluation Pipeline deduplicates against them and does not re-introduce the same listings. There is no way to hide stale rejections early, review what was archived, or recover a card that was archived by mistake.

## Solution

Introduce **Archived Jobs**: a visibility layer (not a new pipeline lane) that hides rejected listings from the default board view while keeping them in the database for deduplication. Jobs auto-archive after two weeks in **Rejected** (measured from **Rejected At**). The user can manually archive Rejected cards sooner, browse archived cards via a three-way **Board Controls** filter, and un-archive with an exemption from future auto-archive. Archive and un-archive actions are recorded in the **Job Activity Log**.

## User Stories

1. As a job seeker, I want stale rejected jobs to disappear from my board automatically after two weeks, so that the Rejected lane stays manageable without manual cleanup.

2. As a job seeker, I want rejected jobs to remain in the database after archival, so that the Search & Evaluation Pipeline does not re-scrape and re-evaluate listings I already rejected.

3. As a job seeker, I want to manually archive a rejected job before the two-week threshold, so that I can dismiss it from the board immediately when I know I will not revisit it.

4. As a job seeker, I want an archive control on Rejected cards (on hover, like the reject button), so that archiving is quick and does not clutter the card face.

5. As a job seeker, I want the default board view to hide archived jobs, so that my active pipeline is the only thing I see when I open the Kanban Dashboard.

6. As a job seeker, I want a Board Controls filter with Active, Archived, and All visibility modes, so that I can browse hidden rejections or see both active and archived cards together.

7. As a job seeker, I want my archived visibility choice to persist across page reloads, so that I stay in the view I was using.

8. As a job seeker, I want archived cards in All view to look visually distinct (muted styling plus an Archived badge), so that I can tell active rejections from archived ones at a glance.

9. As a job seeker, I want to un-archive a job from the archived view using the same hover toggle, so that I can recover a card I archived by mistake.

10. As a job seeker, I want a manually un-archived job to stay on the active board even if it is past the two-week threshold, so that an explicit un-archive is not undone on the next page refresh.

11. As a job seeker, I want automatic archival to run when the dashboard loads jobs, so that stale rejections are cleaned up without a separate cron or CLI step.

12. As a job seeker, I want Rejected At recorded the first time a job enters the Rejected lane and never reset, so that the two-week clock reflects when I first rejected the listing.

13. As a job seeker, I want existing rejected jobs (before rollout) to get a fair grace period rather than archiving immediately on deploy, so that a database migration does not wipe my Rejected lane overnight.

14. As a job seeker, I want manual and automatic archive events in the Job Activity Log, so that I can see when and why a card disappeared from the active board.

15. As a job seeker, I want un-archive events in the Job Activity Log, so that I have a record when I restored a card.

16. As a job seeker, I want to drag an archived card to another lane while it stays archived, so that I can reorganize without un-archiving first.

17. As a job seeker, I want dragging an archived card onto Enriching to do nothing, so that I do not accidentally trigger enrichment (and Apify spend) on a hidden card.

18. As a job seeker, I want lane counts on the Kanban board to respect the archived visibility filter, so that counts match what I see.

19. As a job seeker, I want the un-archive toggle to appear on archived cards in any lane when viewing Archived or All mode, so that I can restore a card even if I previously dragged it out of Rejected while archived.

20. As a job seeker, I want only Rejected cards to offer the manual archive action, so that I cannot accidentally archive an active pipeline job.

21. As a job seeker, I want automatic archival to apply only to jobs still in Rejected status, so that jobs I moved to another lane while archived are not affected by the stale-rejection sweep.

22. As a job seeker, I want deduplication to match archived jobs the same as active jobs, so that link and title+company duplicates are skipped regardless of archive state.

## Implementation Decisions

### Domain model (see CONTEXT.md)

- **Archived Job**: hidden from default Kanban view via an `archived` flag; pipeline status is unchanged by archival alone.
- **Rejected At**: timestamp set on first move to `rejected`; never cleared or reset.
- **Auto-Archive Exemption**: flag set on manual un-archive; prevents future automatic archival even when Rejected At is older than two weeks.

### Schema changes (Job Tracker Database)

Add columns to the jobs table:

- `archived` — boolean, default false
- `rejectedAt` — ISO-8601 timestamp, nullable
- `autoArchiveExempt` — boolean, default false

Migration on init:

- Add columns if missing
- For rows with `status = 'rejected'` and null `rejectedAt`, backfill `rejectedAt` to migration time

### Rejected At lifecycle

- Set `rejectedAt` in the job status update path when status first becomes `rejected` and `rejectedAt` is currently null
- Do not clear or update `rejectedAt` on subsequent lane moves

### Automatic archival sweep

- Run at the start of the jobs fetch path (before filtering results)
- Eligible rows: `status = 'rejected'` AND `archived = false` AND `autoArchiveExempt = false` AND `rejectedAt` older than 14 days
- Action: set `archived = true`; append Job Activity Log entry (e.g. "Auto-archived (rejected 14+ days)")

### Manual archive / un-archive

- New API endpoint to toggle archive state on a job
- **Archive** (when `archived = false`): allowed only when `status = 'rejected'`; sets `archived = true`; logs "Archived"
- **Un-archive** (when `archived = true`): sets `archived = false`, sets `autoArchiveExempt = true`; logs "Un-archived (auto-archive exempted)"
- Does not change pipeline status

### Jobs fetch API

- Extend `GET /api/jobs` with an `archived` query parameter: `active` (default), `archived`, `all`
- Response includes `archived`, `rejectedAt`, and `autoArchiveExempt` on each job (for client rendering)
- Run automatic archival sweep before applying the visibility filter
- `active`: return rows where `archived = false`
- `archived`: return rows where `archived = true`
- `all`: return all rows

### Deduplication

- No change to deduplication logic: `job_exists` continues to match all rows regardless of `archived` flag

### Kanban Dashboard (Board Controls)

- Add three-way archived visibility toggle: Active / Archived / All
- Persist selection in browser local storage (same pattern as other board filters)
- Pass selected mode to `GET /api/jobs` on fetch

### Kanban Dashboard (cards)

- Rejected cards (active view): show archive icon on hover; hide reject control when already rejected (existing behavior)
- Archived cards (Archived or All view): show un-archive icon on hover (any lane)
- All view: archived cards use reduced opacity and an Archived badge

### Kanban Dashboard (drag-and-drop)

- Archived cards: lane drops update status normally except Enriching — drop on Enriching is a silent no-op (no enrichment trigger, no API error)
- Non-archived cards: existing behavior unchanged

### Job schema (Pydantic)

- Extend the Job model with `archived: bool`, `rejectedAt: str | null`, `autoArchiveExempt: bool`

## Testing Decisions

### What makes a good test

- Assert externally observable behavior: API response bodies, status codes, row counts, activity log messages, dedup outcomes
- Do not assert internal helper names or private function call order
- Use isolated temporary databases per test (existing `tmp_path` + `monkeypatch` pattern)

### Testing seams (highest first)

1. **HTTP API (FastAPI TestClient)** — primary seam. Covers sweep + filter on `GET /api/jobs`, archive toggle endpoint, and interaction with status updates. Prior art: `tests/test_dashboard_jobs.py`, `tests/test_activity_log.py` (API portions).

2. **Database module** — covers `rejectedAt` set-on-first-rejection, sweep eligibility, exemption flag, migration backfill, and `job_exists` against archived rows. Prior art: `tests/test_database.py`, `tests/test_activity_log.py`.

3. **Search & Evaluation Pipeline dedup** — confirm a scraped job is skipped when an archived duplicate exists. Prior art: `tests/test_search_pipeline.py` (`job_exists` side effects).

4. **Dashboard HTML** — optional smoke tests for presence of archived visibility control and archive endpoint wiring (string/assertion patterns in existing dashboard tests). Full drag/hover behavior validated in QA, not unit tests.

### Key test scenarios

- Default `GET /api/jobs` excludes archived rows
- Sweep archives rejected job when `rejectedAt` is 15 days ago; does not archive when exempt or not rejected
- Manual archive rejected job; manual un-archive sets exemption; subsequent sweep does not re-archive
- `rejectedAt` set once on first rejection; not updated on second rejection after intermediate lane move
- Migration backfills `rejectedAt` for pre-existing rejected jobs
- `job_exists` returns true for archived job with same link
- Activity log entries for manual archive, auto-archive, and un-archive
- `GET /api/jobs?archived=all` returns both active and archived
- Archive endpoint rejects archive when status is not `rejected`

## QA Validation

- [ ] Open Kanban Dashboard with default Board Controls → Rejected lane shows only non-archived rejected jobs; no Archived badges on visible cards
- [ ] Hover a Rejected card → archive icon appears → click archive → card disappears from Rejected lane
- [ ] Set Board Controls visibility to **Archived** → previously archived card appears in Rejected lane with muted styling
- [ ] Hover archived card → un-archive → set visibility back to **Active** → card reappears on Rejected lane
- [ ] Set visibility to **All** → both active and archived rejected cards visible; archived ones show Archived badge and muted styling
- [ ] Reload page while visibility is **Archived** → same visibility mode restored
- [ ] Drag archived card (Archived or All view) to **Sourced** → card moves to Sourced lane while staying archived; switch to **Active** → card hidden
- [ ] Drag archived card onto **Enriching** → nothing happens (no enrichment spinner / task log activity)
- [ ] Open drawer on a manually archived job (via Archived filter) → Job Activity Log contains an "Archived" entry
- [ ] Reject a new job, wait or simulate 14+ days (test env), reload dashboard → job auto-hides from Active view; visible under Archived filter with auto-archive log entry in drawer

## Out of Scope

- Salary normalization to per-year USD (explicitly deferred from Epic 5)
- Hard-deleting archived jobs or a separate dedup registry table
- Archiving jobs that are not in Rejected status (manual archive entry point)
- Server-side cron or CLI for archival (sweep is tied to jobs fetch only)
- Bulk archive / bulk un-archive actions
- ADR document (may be added separately)

## Further Notes

- Glossary terms **Archived Job**, **Rejected At**, and **Auto-Archive Exemption** are defined in `CONTEXT.md`.
- Automatic archival is intentionally lazy (on dashboard load) because dedup does not depend on the sweep — only board hygiene does.
- Dragging an archived card out of Rejected while staying archived is an intentional power-user path; Enriching is blocked to avoid accidental Apify spend.
