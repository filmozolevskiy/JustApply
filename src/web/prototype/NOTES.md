# Job Comments — prototype notes

**Question:** How should Job Comments appear on the Kanban card (and how should the two-layer Comment Thread read in the drawer)?

**Status:** Production (PRD #185 / #193). Runnable `/prototype/job-comments` pages removed.

## Variants

| Key | Name | Card signal | Drawer |
|-----|------|-------------|--------|
| A | Mix: chip + bubbles *(chosen)* | Header pill with root count (from B) | Comments hero + bubbles (from C) |
| B | Count chip only (ref) | Header pill with root count | Accordion roots |
| C | Drawer-first (ref) | No comment chrome | Comments hero + bubbles |

## Verdict — job comments

**Mix: B card + C drawer** (2026-07-26 / grilled through 2026-07-27).

- Card: count chip of root **Job Comments** in the header (no text preview).
- Drawer: C’s bubble thread styling in the existing **Notes / Comments** slot (after Strengths/Gaps).
- Show-more: reveal all older roots at once; show-fewer collapses to the newest three.
- Always confirm deletes; empty/whitespace Post rejected; 2,000 character cap; inline bubble edit.

---

# Favorite Kanban Card — prototype notes

**Question:** How should a favorited Kanban card look (badge + styling) beside normal cards?

**Status:** Production (PRD #165 / #166). Runnable `/prototype/favorite-card` pages removed.

## Variants

| Key | Name | Badge | Styling |
|-----|------|-------|---------|
| A | Left rail + badge row | `★ Favorite` in badge row (like Archived / Recruiter) | 3px amber left border + warm gradient wash |
| B | Corner bookmark + glow | Top-right ribbon star only — no text badge | Amber outer glow + ribbon bookmark |
| C | Top bar + header chip | `★ Favorite` pill in header beside match % | Full-width amber top bar + warm card wash |

## Verdict — favorite card

**C — Top bar + header chip** (2026-07-11).

- Badge: read-only `★ Favorite` pill in `kanban-card-header-actions`, beside match %.
- Styling: full-width amber top accent bar (`::before`), warm gradient card wash, amber-tinted border.
- Shipped in `boardRenderer.js` + `dashboard.css`.

---

# Favorites Filter button — prototype notes

**Question:** How should the top-row **Favorites Filter** star toggle look when inactive vs active?

**Status:** Production (PRD #165 / #167). Runnable `/prototype/favorites-filter` pages removed.

## Variants

| Key | Name | Inactive | Active |
|-----|------|----------|--------|
| A | Amber filled icon button | Outline star, neutral pill | Filled star, amber fill + glow |
| B | Icon → labeled pill | Icon-only ghost button | Expands to `★ Favorites` amber pill |
| C | Recessed track slot | Star in neutral track | Track highlights; star on amber gradient knob |

## Verdict — favorites filter

**A — Amber filled icon button** (2026-07-11).

- Inactive: outline star (`fa-regular fa-star`), neutral circular pill.
- Active: filled star (`fa-solid fa-star`), amber background tint, amber border, subtle glow.
- Shipped in `dashboard.html` + `boardOrchestration.js` + `dashboard.css`.

---

# Role-filtered Job copy — prototype notes

**Question:** How should a Role-filtered Job look on the Rejected Kanban card and in the job drawer?

**Status:** Production (PRD #207 / #213). Runnable `/prototype/role-reject-copy` page was never shipped.

## Variants

| Key | Name | Card | Drawer |
|-----|------|------|--------|
| A | Badge row + Job Info line *(chosen)* | `Role-filtered` pill in the badge row | Extra Job Info row |
| B | Title strip + banner | Title chrome | Recruiter-style banner |
| C | Header chip + activity-log hero | Header chip | Activity log hero |

## Verdict — Role-filtered copy

**A — Badge row + Job Info line** (2026-09-05).

- Card: `Role-filtered` pill in `kanban-card-badges`, same row as Unclassified / Recruiter. Hover may show the stored reason.
- Drawer: extra Job Info row `Role Relevance: Role-filtered` plus the short reason. No title strip and no recruiter-style banner.
- Shipped in `boardRenderer.js` + `drawerController.js`.
