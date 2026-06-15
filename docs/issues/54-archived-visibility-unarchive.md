## Parent

Parent PRD: #51

## What to build

Browse archived jobs and restore them with **Auto-Archive Exemption**.

End-to-end behavior:

- `GET /api/jobs` accepts `archived=active|archived|all` (default `active`).
- Archive endpoint toggles un-archive: `archived = false`, **Auto-Archive Exemption** = true, log "Un-archived (auto-archive exempted)".
- Board Controls adds Active / Archived / All visibility toggle; persists in localStorage; passes mode to jobs fetch.
- Archived cards show un-archive icon on hover (any lane when visibility includes archived jobs).
- **All** view: archived cards use muted styling and an **Archived** badge.
- Lane counts respect the visibility filter.
- Manually un-archived job past the 14-day threshold remains on the active board after a subsequent jobs fetch (exemption blocks re-archive).

## Acceptance criteria

- [ ] `GET /api/jobs?archived=archived` returns only archived jobs; `?archived=all` returns both
- [ ] Un-archive clears archived flag, sets **Auto-Archive Exemption**, logs to **Job Activity Log**
- [ ] Exempted job survives auto-archive sweep on next fetch
- [ ] Board Controls three-way toggle drives fetch and lane counts; choice persists across reload
- [ ] **All** view shows muted cards with **Archived** badge on archived jobs
- [ ] Hover un-archive on archived cards restores job to active view
- [ ] Automated tests cover API and exemption behavior; `pytest tests/` passes

## Blocked by

- #52
