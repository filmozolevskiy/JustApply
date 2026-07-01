# [PRD] Database Migration Framework and Schema Hygiene

> **GitHub Issue:** [#113](https://github.com/filmozolevskiy/JustApply/issues/113)

## Problem Statement

The **Job Tracker Database** evolves through ad-hoc `ALTER TABLE` attempts on every startup. There is no schema version, making fresh installs and upgrades hard to reason about. `CONTEXT.md` documents a **Job Backup** (`jobs_backup` table) that is not implemented. SQLite connections are opened per call without WAL/busy-timeout tuning, which risks lock contention as the dashboard, **Batch Poller**, and background enrichment overlap.

## Solution

Introduce a versioned migration mechanism, resolve the **Job Backup** documentation-vs-implementation gap, and apply conservative SQLite pragmas for local concurrent access — without changing Kanban-visible fields or breaking existing `just_apply.db` files.

## User Stories

1. As a maintainer, I want a recorded schema version, so that I know which migrations ran on a database file.

2. As a maintainer, I want migrations to run once per version bump, so that startup is not a chain of silent try/except ALTERs.

3. As a contributor, I want a template for adding new columns, so that schema changes follow one pattern.

4. As a maintainer, I want existing user databases to upgrade in place on next dashboard or CLI start, so that users are not forced to delete `data/just_apply.db`.

5. As a maintainer, I want the **Job Backup** concept either implemented or removed from the glossary, so that agents do not assume a table exists.

6. As a job seeker, I want my jobs, contacts, and **Contact Sample Cache** preserved across upgrades, so that daily use is uninterrupted.

7. As a maintainer, I want seed data still guarded so empty DB init does not wipe real data in production-like local use, so that the safety story stays intact.

8. As a maintainer, I want WAL mode or busy timeout configured, so that concurrent reads during **Batch Poller** and writes during enrichment collide less often.

9. As a maintainer, I want migration tests that apply from an older schema fixture to current, so that upgrades are regression-tested.

10. As an agent, I want destructive operations still gated by the **Database Safety Gate**, so that migrations do not bypass snapshot rules.

11. As a maintainer, I want batch evaluation persistence tables included in migration versioning if they exist outside inline init, so that batch state survives upgrades cleanly.

12. As a contributor, I want rollback strategy documented (restore from **Database Snapshot**), so that failed migrations have a human recovery path.

## Implementation Decisions

- Add `schema_version` (integer or semver string) stored in DB metadata table or `PRAGMA user_version`.
- Convert existing inline migrations in connection init into numbered migration steps with idempotent apply function per version.
- On startup: read version → apply pending migrations in order → bump version.
- **Job Backup** decision (pick one in implementation):
  - **Option A:** Implement `jobs_backup` table matching glossary + `backed_up_at`, with explicit one-shot backup API unused by default pipelines; or
  - **Option B:** Remove **Job Backup** from `CONTEXT.md` and rely solely on external **Database Snapshot** (`VACUUM INTO`) — preferred if no product workflow needs in-DB backup.
- Enable SQLite WAL and reasonable busy timeout on connection open for dashboard/poller concurrency.
- Keep parameterized queries; dynamic column updates remain whitelist-only.
- Do not rename Kanban status values or batch tables in this PRD unless required for migration framework scaffolding.

## Testing Decisions

- Migration tests using temporary DB files: start from legacy minimal schema fixture → run init → assert columns/tables and version.
- Existing migration/status tests (`test_status_migration.py`, etc.) updated to use new framework entry point.
- **Prior art:** current init tests; status lane migration tests; db safety gate tests ensuring snapshots still trigger.
- Assert external behavior: job reads/writes, batch poller resume, outreach settings row — not internal migration class names.

## QA Validation

- [ ] Start dashboard with an existing populated `data/just_apply.db` → jobs appear on board with no data loss.
- [ ] Start dashboard on empty `data/` → app initializes and board loads empty lanes.
- [ ] Run a job search from dashboard → new **Scraped Jobs** appear and evaluation proceeds as before.

## Out of Scope

- PostgreSQL or hosted DB support.
- **Contacted Elsewhere** index (separate PRD).
- Changing job JSON column shapes or Kanban field names.
- Automatic pruning/archival logic changes.

## Further Notes

External **Database Snapshots** under `~/.just_apply/backups/` remain the primary disaster-recovery story. In-database **Job Backup** should not duplicate that unless a concrete workflow needs it.
