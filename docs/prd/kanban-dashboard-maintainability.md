# [PRD] Kanban Dashboard Maintainability

> **GitHub Issue:** [#114](https://github.com/filmozolevskiy/JustApply/issues/114)

## Problem Statement

The **Kanban Dashboard** frontend lives primarily in a single enormous HTML document with inline scripts, while backend server setup runs database initialization at import time, accumulates background task state forever, and relies on path hacks to import the package. These choices slow UI iteration, leak memory on long-running local servers, and complicate testing and packaging.

## Solution

Refactor dashboard assets and server bootstrap for maintainability: extract client code into static modules/CSS, prune completed background tasks, defer DB init to explicit startup, and make the Python package importable without manipulating `sys.path` — without changing Kanban behavior, lanes, or API contracts.

## User Stories

1. As a maintainer, I want dashboard JavaScript in focused static modules, so that drawer and board changes are reviewable.

2. As a maintainer, I want CSS separated from HTML, so that styling changes do not require editing a 4k-line file.

3. As a job seeker, I want the dashboard to look and behave exactly as before refactor, so that my workflow is unchanged.

4. As a maintainer, I want completed SSE background tasks removed from server memory, so that all-day dashboard sessions stay stable.

5. As a maintainer, I want database initialization at server startup (not import), so that test imports do not side-effect production DB paths unintentionally.

6. As a contributor, I want to run the dashboard without `sys.path.insert` hacks, so that imports match normal package layout.

7. As a maintainer, I want existing dashboard HTML/JS tests updated to reference extracted assets, so that regressions are caught.

8. As a job seeker, I want **Enrich Job**, **Load More Contacts**, and search SSE logs to work identically, so that task streaming is unaffected.

9. As a maintainer, I want **Batch Poller** startup unchanged from a user perspective, so that **Scraped → Matched** transitions still occur.

10. As a maintainer, I want `/api/health` to remain available for local ops checks, so that smoke tests can use it.

11. As a contributor, I want `run_dashboard.py` to remain the documented entry command, so that README stays valid.

12. As a maintainer, I want duplicate scrape endpoints (`/api/search` vs `/api/scrape`) consolidated or one deprecated with logged warning, so that API surface is clearer — behavior preserved for existing clients.

13. As a job seeker, I want **Spend Confirmation** modals unchanged, so that cost gates still protect Apify and Bright Data spend.

14. As a maintainer, I want load-more remain synchronous if product requires immediate drawer update, but document blocking behavior — moving to background is out of scope unless UX spec changes.

## Implementation Decisions

- Split `dashboard.html` into HTML shell + existing/static JS modules (`boardRenderer`, `drawerController`, `taskLogClient`, `jobStore`) + new CSS under static assets; keep inline script only for bootstrapping if needed.
- Preserve all current API routes and response models; no auth added (localhost tool).
- Move `init_db()` call to FastAPI lifespan/startup handler in server runner, not module import.
- Prune `active_tasks` entries after SSE stream completes or task reaches terminal state; retain brief TTL if clients reconnect.
- Remove `sys.path.insert` from web entry modules; ensure repo-root execution documented (`python -m src.web.run_dashboard`).
- Optionally mark duplicate scrape route deprecated in OpenAPI description; single implementation internally.
- Do not rewrite Kanban UX (lanes, **Board Controls**, Profile Manager) in this PRD.

## Testing Decisions

- Update existing dashboard module tests that read HTML/JS file contents to assert extracted asset references.
- SSE/log stream tests verify task cleanup does not break replay for completed tasks during reconnect window.
- Test server startup calls init once when app boots via TestClient lifespan pattern.
- **Prior art:** `test_dashboard_modules.py`, `test_log_stream.py`, `test_dashboard_sse_refresh.py`, kanban JS string tests.
- Add smoke test for `/api/health` returning 200.

## QA Validation

- [ ] Run `python3 -m src.web.run_dashboard` → board loads at http://127.0.0.1:8000 with all lanes visible.
- [ ] Drag a **Matched Job** to **Accepted** → status updates and card moves lane.
- [ ] Click **Enrich Job** on an **Accepted Job** → spinner appears, Task Log streams, drawer shows contacts or **Enrichment Note**.
- [ ] Trigger job search from dashboard → **Spend Confirmation** appears before scrape; **Scraped Jobs** arrive after batch evaluation completes.
- [ ] Leave dashboard open, run several enrichments → UI remains responsive (no obvious slowdown from memory growth).

## Out of Scope

- Authentication, HTTPS, or exposing dashboard beyond localhost.
- Visual redesign or new Kanban features.
- Replacing inline tests with browser E2E (Playwright).
- Making **Load More Contacts** asynchronous (unless explicitly specified later).

## Further Notes

Dashboard HTML grew substantially since the original audit (~4.5k lines). This PRD targets maintainability only; pair with **Developer Tooling** PRD for CI coverage on static asset moves.
