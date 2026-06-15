## Parent

Parent PRD: #51

## What to build

Drag-and-drop rules for **Archived Jobs** on the Kanban Dashboard.

End-to-end behavior:

- Archived cards (visible in **Archived** or **All** Board Controls mode) can be dragged to lanes other than **Enriching**; lane status updates normally but `archived` stays true.
- Dropping an archived card on **Enriching** is a silent no-op — no status change, no enrichment trigger, no error toast.
- Un-archive hover toggle remains available on archived cards in any lane when archived visibility is enabled.

## Acceptance criteria

- [ ] Drag archived card to Sourced (or other non-Enriching lane) updates status; card stays archived and hidden in **Active** view
- [ ] Drag archived card onto **Enriching** does nothing (no API enrich call, no lane change)
- [ ] Un-archive toggle still works on archived card after it was moved out of Rejected
- [ ] Non-archived cards retain existing drag behavior unchanged
- [ ] Dashboard wiring tests or manual QA steps documented; `pytest tests/` passes

## Blocked by

- #52
- #54
