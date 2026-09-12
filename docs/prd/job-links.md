# [PRD] Job Links

> **GitHub Issue:** [#206](https://github.com/filmozolevskiy/JustApply/issues/206)

## Problem Statement

Opening a job on the **Kanban Dashboard** only updates in-memory drawer state. The browser address bar stays on `/` (or `/dashboard`), so a job seeker cannot bookmark, reload, or paste a URL that reopens the same job's drawer. Sharing a specific role with themselves across sessions requires finding the card again on the board.

## Solution

Introduce **Job Links**: paths of the form `/jobs/{id}` that mean that job's drawer is open. Opening a job updates the URL; closing returns to `/`. Reloading or pasting a **Job Link** reopens that drawer on the same board without changing **Board Controls**. Browser Back / Forward walks recently opened jobs and the closed board. Dirty **Drawer Draft**s keep the existing **Unsaved Draft Warning** when URL navigation would leave or switch jobs.

## User Stories

1. As a job seeker, I want the address bar to show `/jobs/{id}` when a job drawer is open, so that I can see which job I am viewing from the URL alone.

2. As a job seeker, I want clicking a Kanban card to set a **Job Link**, so that the open drawer and the URL stay in sync.

3. As a job seeker, I want closing the drawer to return the URL to `/`, so that a closed board has a clear board-root path.

4. As a job seeker, I want reloading a **Job Link** to reopen that job's drawer, so that a refresh does not lose my place.

5. As a job seeker, I want pasting a **Job Link** into the browser to open that drawer on load, so that bookmarks and copied links work.

6. As a job seeker, I want drawer previous/next to update the **Job Link**, so that keyboard-style triage keeps the URL accurate.

7. As a job seeker, I want **Contacted Elsewhere** navigation to update the **Job Link**, so that jumping to another job's drawer is shareable and reloadable.

8. As a job seeker, I want each open or switch of a job to add a browser history step, so that Back and Forward move through recently opened jobs.

9. As a job seeker, I want closing the drawer to add a history step to `/`, so that Back from the closed board reopens the last job and Forward closes it again.

10. As a job seeker, I want Back from an open **Job Link** to open the previous history entry (another job or the board root), so that history behaves like normal browsing.

11. As a job seeker, I want Forward after going Back to restore the next **Job Link** or closed board, so that history is symmetric.

12. As a job seeker, I want a **Job Link** for a job hidden by **Board Controls** to still open the drawer, so that shared or bookmarked links are not blocked by my current filters.

13. As a job seeker, I want opening a **Job Link** for an **Archived Job** while archived visibility is **Active** to open the drawer without changing archived visibility, so that my triage filters stay intact.

14. As a job seeker, I want opening a **Job Link** when the job is not already in the loaded board set to fetch that job by id and open the drawer, so that Contacted Elsewhere–style jumps and cold links still work.

15. As a job seeker, I want a **Job Link** for a missing or deleted id to leave the drawer closed and return the path to `/`, so that bad links fail safely.

16. As a job seeker, I want a short error signal (Task Logs or equivalent existing feedback) when a **Job Link** id is not found, so that I know why the drawer did not open.

17. As a job seeker with a dirty **Drawer Draft**, I want Back / Forward / a new **Job Link** that would leave or switch jobs to show the **Unsaved Draft Warning**, so that I do not lose unposted edits by accident.

18. As a job seeker, I want **Cancel** on that warning to keep my drafts and restore the current **Job Link** in the URL, so that refusing discard does not leave the URL out of sync.

19. As a job seeker, I want **Discard** on that warning to clear dirty drafts and complete the pending URL navigation, so that I can still leave when I mean to.

20. As a job seeker, I want `/dashboard` to keep loading the same board as `/`, so that old bookmarks still work.

21. As a job seeker, I want closing a drawer (or clearing a bad **Job Link**) to normalize to `/` rather than `/dashboard`, so that the canonical board root is consistent.

22. As a job seeker, I want **Board Controls** (search, refine, favorites, archived visibility) to stay browser-local and out of the **Job Link**, so that URLs stay short and filters are not rewritten by a pasted link.

23. As a job seeker, I want the browser tab title to stay the normal **Kanban Dashboard** title when a **Job Link** is open, so that tab chrome does not churn during triage.

24. As a job seeker, I want `/api/*` and `/static/*` routes to keep working unchanged when **Job Links** exist, so that APIs and assets are not shadowed by job paths.

25. As a maintainer, I want `GET /jobs/{id}` to serve the same dashboard HTML as `/`, so that a hard navigation to a **Job Link** boots the SPA instead of 404ing.

26. As a maintainer, I want non-numeric `/jobs/...` paths to not be treated as valid **Job Links**, so that reserved or garbage paths do not open drawers.

27. As a maintainer, I want bare `/jobs` (no id) to resolve to the board root behavior, so that incomplete paths do not strand the UI.

28. As a job seeker, I want opening the same job again while its drawer is already open to keep a coherent URL (still `/jobs/{id}`), so that redundant opens do not break history expectations.

29. As a job seeker, I want lane moves, enrichment, and other drawer actions while a **Job Link** is open to leave the path as `/jobs/{id}` until I close or navigate away, so that the URL keeps meaning “this drawer is open.”

30. As a maintainer, I want no new Job Tracker Database schema for **Job Links**, so that this remains a presentation/routing feature only.

31. As a maintainer, I want existing `GET /api/jobs/{id}` to remain the fetch path for cold **Job Links**, so that we reuse the single-job API already used by **Contacted Elsewhere**.

32. As a contributor, I want pure path parse/build helpers for **Job Links**, so that URL rules can be unit-tested without a browser.

33. As a maintainer, I want dashboard module wiring tests to assert open/close/nav/boot/`popstate` sync and draft guards, so that regressions match existing Kanban JS test style.

## Implementation Decisions

- **Path shape:** `/jobs/{id}` only (numeric job id). Board root when the drawer is closed: `/`. `/dashboard` remains a synonym that loads the board; close and bad-link recovery normalize to `/`.
- **Meaning:** A **Job Link** means the job drawer is open for that id. It is not a sticky “selected job” when the drawer is closed.
- **Server:** Serve the dashboard HTML for `GET /jobs/{job_id}` the same way as `/` and `/dashboard`. Do not add authentication or change localhost binding. Do not let job routes shadow `/api` or `/static`.
- **Client sync:** On card open, drawer prev/next, **Contacted Elsewhere**, and close: push a browser history entry (`/jobs/{id}` or `/`). On first load and `popstate`: parse the path and open or close the drawer to match.
- **Cold open:** If the job is not in the in-memory board set, fetch via existing single-job API, upsert into the store, then open the drawer — same spirit as **Contacted Elsewhere**. Do not change **Board Controls**.
- **Missing id:** Drawer stays closed; path returns to `/`; surface a short existing-style error to the user.
- **History:** Push on every open/switch and on close. Back from closed `/` reopens the last job; Forward closes again.
- **Drafts:** URL-driven leave/switch goes through the same **Unsaved Draft Warning** path as close / prev-next. **Cancel** keeps drafts and restores the current **Job Link**; **Discard** proceeds.
- **Helpers:** Introduce a small pure parse/build helper for **Job Link** paths (board root vs job id). Drawer/boot code calls it; keep history/`popstate` wiring thin.
- **No schema / no new job API:** No database migration; reuse existing single-job GET.
- **Tab title:** Unchanged in this PRD.
- **Filters:** Not encoded in path or query.

## Testing Decisions

Good tests assert external behavior: HTTP responses for dashboard routes, pure path helper inputs/outputs, and source wiring that open/close/nav/boot/`popstate` sync URLs and draft guards — not private drawer variable names.

- **HTTP seam (existing):** FastAPI TestClient asserts `GET /jobs/{id}` returns the dashboard HTML (same family as `/`); `/api` and `/static` remain unaffected. Prior art: dashboard module static/asset route tests.
- **Pure Job Link helpers (approved new seam):** Unit-test path parse/build — `/jobs/42` ↔ id `42`, board root `/`, reject non-numeric segments, bare `/jobs` → board-root behavior.
- **Wiring checks (prior art, not a new seam):** Same style as drawer-draft tests — assert open / close / prev-next / **Contacted Elsewhere** / boot / `popstate` sync the URL and invoke **Unsaved Draft Warning** on URL leave.
- **No browser E2E / Playwright** for this PRD.
- Full `pytest` quality gate remains required for the implementing PR.

## Out of Scope

- Encoding **Board Controls** (search, refine, favorites, archived visibility, sort) in the URL.
- Changing the browser tab title based on the open job.
- Root-style paths like `/{id}` or hash/query-only job links.
- Authentication, HTTPS, or exposing the dashboard beyond localhost.
- New Job Tracker Database fields or tables for links.
- Playwright / browser E2E suites.
- Visual redesign of the drawer or board.

## Further Notes

Domain term **Job Link** is defined in `CONTEXT.md`. Behavior was grilled to: open-drawer-only URL, `/jobs/{id}` shape, push history including close, open-anyway without filter changes, draft warning on URL leave, canonical close path `/`, unchanged tab title, filters out of URL for v1. Implementation is frontend URL sync plus a thin dashboard HTML route — no pipeline or matcher changes.
