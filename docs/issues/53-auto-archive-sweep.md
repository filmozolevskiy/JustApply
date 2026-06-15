## Parent

Parent PRD: #51

## What to build

Automatic archival of stale Rejected jobs when the Kanban Dashboard loads jobs.

End-to-end behavior:

- At the start of `GET /api/jobs`, sweep eligible jobs: `status = rejected`, `archived = false`, **Auto-Archive Exemption** false, and **Rejected At** older than 14 days.
- Set `archived = true` and append "Auto-archived (rejected 14+ days)" to **Job Activity Log**.
- Sweep does not archive exempt jobs, non-Rejected jobs, or already-archived jobs.
- Default `GET /api/jobs` continues to hide newly auto-archived jobs from the active board.

Manual un-archive and **Auto-Archive Exemption** are handled in a later slice; this slice only implements the sweep and auto-archive logging.

## Acceptance criteria

- [ ] `GET /api/jobs` runs the auto-archive sweep before returning results
- [ ] Rejected job with **Rejected At** 15+ days ago is archived and logged on fetch
- [ ] Job with **Auto-Archive Exemption** true is not auto-archived
- [ ] Job not in Rejected status is not auto-archived even if **Rejected At** is old
- [ ] Auto-archived job is absent from default (active) jobs response
- [ ] Automated tests use backdated **Rejected At**; `pytest tests/` passes

## Blocked by

- #52
