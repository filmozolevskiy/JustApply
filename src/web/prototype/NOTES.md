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
