# [PRD] Job Favorites

> **GitHub Issue:** [#165](https://github.com/filmozolevskiy/JustApply/issues/165)

## Problem Statement

Job seekers triaging many listings on the **Kanban Dashboard** have no lightweight way to bookmark roles they want to track without committing to **Accepted** or changing pipeline lane. **Matched**, **Scraped**, **Applied**, and even **Rejected** / **Archived** jobs can all deserve a second look, but the board offers only lane moves (heavy intent) or **Job Comment** (unstructured). There is no personal watchlist, no quick filter to surface bookmarked cards, and no consistent visual cue on the board for jobs already marked.

## Solution

Add **Favorite Job** support: a persisted `favorited` boolean on each job row, toggled from a star control in the job drawer header, with read-only favorited styling on Kanban cards and a **Favorites Filter** star toggle in **Board Controls** (top row, between **Board Search** and sort). Favoriting is orthogonal to pipeline status — it does not trigger **Enrichment**, move lanes, or imply pursuit. Favorite toggles append **Marked favorite** / **Unmarked favorite** to the **Job Activity Log**. **Favorites Filter** combines with existing **Board Controls** via AND logic and bypasses **Active** archived visibility for favorited **Archived Jobs** (same spirit as the contact-name **Board Search** bypass).

## User Stories

1. As a job seeker, I want to mark any job as a **Favorite Job** from the drawer header, so that I can bookmark it without dragging to **Accepted**.

2. As a job seeker, I want the favorite star in the drawer header beside the match score pill, so that I can toggle it in one click while reading job details.

3. As a job seeker, I want the drawer star filled when favorited and outlined when not, so that the current state is obvious.

4. As a job seeker, I want favoriting to work on **Scraped Jobs**, so that I can bookmark promising listings before **Batch Evaluation** completes.

5. As a job seeker, I want favoriting to work on **Matched Jobs**, so that I can shortlist evaluated roles I am still comparing.

6. As a job seeker, I want favoriting to work on **Accepted**, **Applied**, and **Interviewing** jobs, so that I can track active pursuits alongside new discoveries.

7. As a job seeker, I want favoriting to work on **Rejected** jobs, so that I can keep reference roles without moving them out of **Rejected**.

8. As a job seeker, I want favoriting to work on **Archived Jobs**, so that I can bookmark roles that left the active board.

9. As a job seeker, I want unfavoriting to clear only the bookmark flag, so that lane, archive state, contacts, and templates stay unchanged.

10. As a job seeker, I want favoriting never to trigger **Enrichment** or Apify spend, so that bookmarking stays free and safe.

11. As a job seeker, I want favoriting never to change pipeline lane, so that it remains lighter than dragging to **Accepted**.

12. As a job seeker, I want each favorite toggle logged in the **Job Activity Log**, so that I can see when I marked or cleared a bookmark.

13. As a job seeker, I want favorited Kanban cards to show a read-only `★ Favorite` pill in the card header beside match %, so that I can spot bookmarks while scanning lanes.

14. As a job seeker, I want favorited cards to use a full-width amber top accent bar and warm card wash (prototype variant C), so that favorites stand out without clicking the filter.

15. As a job seeker, I want the favorite pill on the card to be display-only (not clickable), so that I do not accidentally toggle while opening the drawer.

16. As a job seeker, I want a **Favorites Filter** star button in the **Board Controls** top row between search and sort, so that I can narrow the board to favorites quickly.

17. As a job seeker, I want the filter button inactive by default with an outline star on a neutral pill, so that the board starts unfiltered.

18. As a job seeker, I want the filter button active state to show a filled star with amber fill, amber border, and subtle glow (prototype variant A), so that I can see the filter is on.

19. As a job seeker, I want **Favorites Filter** to show only **Favorite Jobs** when on, so that the board becomes a personal watchlist.

20. As a job seeker, I want **Favorites Filter** to combine with **Board Search** and **Refine board** filters via AND, so that I can find favorited remote roles at a specific company.

21. As a job seeker, I want favorited **Archived Jobs** to appear when **Favorites Filter** is on even if archived visibility is **Active**, so that buried bookmarks are still reachable.

22. As a job seeker, I want favorited archived jobs to hide again when I turn **Favorites Filter** off under **Active** visibility, so that normal archived hiding still applies.

23. As a job seeker, I want **Reset filters** to turn **Favorites Filter** off along with other **Board Controls** defaults, so that one control restores the full board.

24. As a job seeker, I want **Favorites Filter** state persisted in browser local storage across reloads, so that my watchlist view survives refresh.

25. As a job seeker, I want drawer previous/next navigation to follow the filtered visible set when **Favorites Filter** is on, so that I only step through jobs I can see.

26. As a job seeker, I want the generic “no jobs match your filters” hint when the favorites filter yields zero visible cards, so that empty state stays consistent with other filters.

27. As a job seeker, I want lane drag-and-drop to preserve favorite state, so that moving a card does not clear my bookmark.

28. As a job seeker, I want automatic archival of old **Rejected** jobs to preserve `favorited`, so that a favorite flag survives the two-week **Rejected At** sweep.

29. As a job seeker, I want manual archive / un-archive to preserve `favorited`, so that archive actions and bookmarks stay independent.

30. As a job seeker, I want favorited cards to keep favorite styling when shown alongside **Archived** badge and other badges (Recruiter, Unclassified), so that combined states read clearly.

31. As a job seeker, I want the drawer star to update immediately after toggle without a full page reload, so that feedback is instant.

32. As a job seeker, I want favorite state returned on `GET /api/jobs` and `GET /api/jobs/{id}`, so that the dashboard and drawer stay in sync after refresh.

33. As a maintainer, I want a versioned DB migration adding `favorited` defaulting to false, so that existing jobs upgrade safely.

34. As a maintainer, I want favorite toggles to use the same Job model and CRUD patterns as archive and comment updates, so that schema and API stay consistent.

35. As a maintainer, I want throwaway favorite UI prototypes removed after implementation, so that prototype routes do not ship to production users.

## Implementation Decisions

### Domain model

- Add `favorited: bool` (default `false`) to the **Job** schema and **Job Tracker Database** `jobs` table via the versioned migration runner.
- **Favorite Job** is independent of `status`, `archived`, and `autoArchiveExempt`. No new Kanban lane.

### Persistence and API

- DB helper: set favorite state for a job id, append activity log entry, return updated **Job** (mirror archive / comment update patterns).
- HTTP: `POST /api/jobs/{job_id}/favorite` with JSON body `{ "favorited": true | false }`, response `Job` or 404.
- Activity log messages exactly: `Marked favorite` when setting true; `Unmarked favorite` when setting false.
- `GET /api/jobs` and `GET /api/jobs/{id}` include `favorited` on each job. No server-side favorites filter param — filtering stays client-side in **Board Controls** like remote type and recruiter filters.

### Kanban card rendering (prototype variant C)

Favorited cards add class `kanban-card--favorited` and read-only header chip:

```css
/* From prototype variant C — decision-rich excerpt */
.kanban-card--favorited {
  border-color: rgba(245, 158, 11, 0.4);
  background: linear-gradient(180deg, rgba(245, 158, 11, 0.12) 0%, rgba(245, 158, 11, 0.04) 12%, rgba(20, 26, 48, 0.8) 22%);
}
.kanban-card--favorited::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  border-radius: 10px 10px 0 0;
  background: linear-gradient(90deg, #f59e0b, #fbbf24, #f59e0b);
}
```

Header chip: `★ Favorite` pill in `kanban-card-header-actions` before match % — not interactive.

### Board Controls filter (prototype variant A)

- New mount between search and sort: circular star button, `aria-pressed`, `boardFilterFavorites` in localStorage (default off).
- Inactive: `fa-regular fa-star`, neutral pill. Active: `fa-solid fa-star`, amber fill/border/glow:

```css
/* From prototype variant A — decision-rich excerpt */
.board-favorites-filter[aria-pressed="true"] {
  border-color: rgba(245, 158, 11, 0.65);
  background: rgba(245, 158, 11, 0.22);
  color: #fcd34d;
  box-shadow: 0 0 14px rgba(245, 158, 11, 0.25);
}
```

- Extend `filterJobs` with `favoritesOnly` boolean. When true, require `job.favorited === true`.
- Archived bypass: when `favoritesOnly` and `archivedVisibility === 'active'`, include favorited jobs even if `job.archived` (parallel to contact-name search bypass in `filterJobs`).
- **Reset filters** clears favorites filter and localStorage key.

### Job drawer

- Star toggle in `drawer-header-actions`, left of match pill; `stopPropagation` not needed in drawer but must not submit forms.
- On click: `POST /api/jobs/{id}/favorite`, update in-memory job store, re-render board and drawer header, preserve open drawer.

### Cleanup

- Delete throwaway routes `/prototype/favorite-card` and `/prototype/favorites-filter` and associated static assets after production wiring lands.

## Testing Decisions

**Testing seams (highest first — preferred over new low-level seams):**

1. **HTTP API** — `POST /api/jobs/{id}/favorite` returns updated `favorited` and activity log entries; 404 for missing job. Prior art: `tests/test_unarchive.py`, `tests/test_dashboard_jobs.py`.
2. **DB layer** — migration adds column; set-favorite helper persists flag and logs. Prior art: `tests/test_archive.py`, `tests/test_activity_log.py`, `tests/test_migrations.py`.
3. **`filterJobs` (Node seam)** — favorites-only filter, AND with search/remote, archived bypass for favorited archived jobs. Prior art: `tests/test_dashboard_modules.py` (`_run_node` imports from `boardRenderer.js`).
4. **Dashboard static wiring smoke** — HTML includes favorites filter mount; drawer header star handler present. Prior art: `tests/test_dashboard_jobs.py`, `tests/test_dashboard_outreach_settings.py`.

Good tests assert **external behavior** only: API response fields, filter output job ids, activity log message strings — not CSS class names or internal function names unless stable public seams.

Modules under test: Job Tracker DB CRUD, FastAPI job endpoints, `boardRenderer.filterJobs`, board orchestration localStorage keys (optional light DOM tests if existing patterns cover similar controls).

## QA Validation

- [ ] Open any job drawer → click outline star in header → star fills, card shows `★ Favorite` pill and amber top bar → **Job Activity Log** shows `Marked favorite`
- [ ] Click filled star again → outline star, card styling clears → log shows `Unmarked favorite`
- [ ] Favorite jobs in **Matched**, **Scraped**, and **Rejected** lanes → each keeps its lane; no enrichment spinner or lane move
- [ ] Click top-row **Favorites Filter** star → button glows amber, board shows only favorited cards across lanes → click again → all jobs return
- [ ] With **Favorites Filter** on, apply **Board Search** that matches only some favorites → only matching favorites remain
- [ ] Favorite an archived **Rejected** job (visible via **Archived** or **All** visibility) → switch archived visibility to **Active** → card hides → turn **Favorites Filter** on → favorited archived card reappears
- [ ] Click **Reset filters** in **Refine board** → favorites filter off, search cleared, board shows normal active jobs
- [ ] Reload dashboard with favorites filter on → filter state and filtered board restored from browser storage

## Out of Scope

- Toggling favorite from the Kanban card (drawer only).
- Auto-unarchive or **Auto-Archive Exemption** changes when favoriting.
- Favorites-specific empty-state copy (generic “no jobs match” only).
- CLI favorite commands.
- A dedicated favorites Kanban lane.
- Sort-by-favorite option.
- Bulk favorite / unfavorite.
- Server-side `?favorited=` query on `GET /api/jobs` (client filter only for v1).
- Favorite count badge on lane headers.

## Further Notes

- Domain terms and behavior are authoritative in root `CONTEXT.md` (**Favorite Job**, **Board Controls**, **Job Activity Log**).
- Visual decisions validated in throwaway prototypes; verdicts recorded in `src/web/prototype/NOTES.md` (card: variant C; filter button: variant A).
- Implementation can be sliced into child issues: schema + API, board filter + card styling, drawer toggle, prototype cleanup.
