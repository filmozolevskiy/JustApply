# Prototype verdict — Profile Manager modal

**Question:** What should the Profile Manager modal (PRD #85) look like?

**Variants** (`?variant=` on `dashboard_profile_manager.prototype.html`):

- **A — Master / detail (two-pane):** left list of profiles + right editor. IDE/file-manager shape. Best for power use and many profiles; editor always visible.
- **B — Card gallery + editor overlay:** profiles as cards with preview snippets + a dashed "Upload PDF" dropzone card; Edit slides into a full editor. Most visual; import is the hero affordance.
- **C — Single-column accordion:** vertical list, each row expands inline to edit; radio buttons set active; import strip pinned at top. Narrowest footprint, simplest mental model.

## Verdict

- **Winner: A — Master / detail (two-pane).** Chosen by user on 2026-06-26.
- Why: profile list always visible alongside an always-open editor; scales to many profiles; matches an IDE/file-manager mental model. Import and New sit at the top of the list pane; Set active / Delete / Save live in the detail header.
- Bits to steal from others: none requested. (B's dropzone and C's inline-active radio were available but A's "Import PDF" button + per-row active chip cover it.)

The prototype file has been trimmed to Variant A only (B, C, and the switcher removed) and now serves as the visual spec for implementing PRD #85.

When PRD #85 is implemented: fold Variant A into `dashboard.html` (rewritten properly, not copy-pasted), then delete both this file and `dashboard_profile_manager.prototype.html`.
