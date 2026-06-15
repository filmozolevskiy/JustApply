## Parent

Parent PRD: #51

## What to build

First tracer bullet for **Archived Jobs**: a Rejected job can be manually hidden from the default Kanban view while staying in the Job Tracker Database for deduplication.

End-to-end behavior:

- Job Tracker Database gains `archived`, `rejectedAt`, and `autoArchiveExempt` columns. Existing Rejected jobs get **Rejected At** backfilled to migration time.
- When a job first enters the Rejected lane, **Rejected At** is set once and never updated on later lane moves.
- `GET /api/jobs` returns only non-archived jobs by default and includes `archived`, `rejectedAt`, and `autoArchiveExempt` on each job.
- New archive endpoint: archive a Rejected job (`archived = true`), append "Archived" to **Job Activity Log**. Reject archive attempts when status is not `rejected`.
- Kanban Dashboard: hover archive icon on Rejected cards; clicking removes the card from the active board.
- Deduplication unchanged: `job_exists` still matches archived rows.

Un-archive, visibility filter, auto-sweep, and archived drag rules are out of scope for this slice.

## Acceptance criteria

- [ ] Schema migration adds `archived`, `rejectedAt`, `autoArchiveExempt`; existing Rejected jobs receive **Rejected At** backfill
- [ ] First move to Rejected sets **Rejected At**; a later reject after an intermediate lane move does not change it
- [ ] `GET /api/jobs` (default) excludes archived jobs and exposes new fields on returned jobs
- [ ] Archive endpoint archives a Rejected job, rejects non-Rejected jobs, and logs "Archived" to **Job Activity Log**
- [ ] Kanban hover archive on Rejected cards hides the card after success
- [ ] `job_exists` returns true for an archived job with the same link or title+company
- [ ] Automated tests cover DB, API, and dedup behavior; `pytest tests/` passes

## Blocked by

None — can start immediately
