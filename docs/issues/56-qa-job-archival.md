## Parent

Parent PRD: #51

## What to build

Human QA pass for the full **Job Archival Lifecycle** feature across slices #52–#55.

Run the PRD QA Validation checklist in a running Kanban Dashboard (local `python3 -m src.web.run_dashboard`). Use test data or backdated **Rejected At** where needed to exercise auto-archive without waiting 14 days.

## Acceptance criteria

- [ ] Default board shows only non-archived jobs; Rejected lane has no **Archived** badges
- [ ] Hover archive on Rejected card → card disappears from active board
- [ ] **Archived** filter shows archived card with muted styling; un-archive restores to **Active** view
- [ ] **All** filter shows active and archived together; archived cards have badge + muted styling
- [ ] Archived visibility persists after page reload
- [ ] Drag archived card to Sourced (Archived/All view) → moves lane, stays hidden in **Active**
- [ ] Drag archived card to **Enriching** → no enrichment activity
- [ ] Job drawer **Job Activity Log** shows archive, auto-archive, and un-archive entries as applicable
- [ ] Gaps filed as separate bugs if any checklist item fails

## Blocked by

- #53
- #54
- #55
