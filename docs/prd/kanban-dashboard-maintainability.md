# [PRD] Kanban Dashboard Maintainability

> **GitHub Issue:** [#114](https://github.com/filmozolevskiy/JustApply/issues/114)

## Problem Statement

The **Kanban Dashboard** is difficult to maintain and safely refactor. Most of the UI still lives in one HTML document: roughly 2,400 lines of inline CSS and 2,000 lines of inline module JavaScript, on top of four smaller static modules that were already extracted. Backend bootstrap is inconsistent — the **Batch Poller** starts on FastAPI startup, but **Job Tracker Database** initialization runs at module import, `sys.path` hacks remain in web entrypoints, and in-memory SSE task state is never pruned. Long local sessions can accumulate dead task entries while tests that import the server module may touch the real database unintentionally.

## Solution

Refactor dashboard assets and server bootstrap for maintainability without changing user-visible Kanban behavior. Extract remaining inline CSS and orchestration JavaScript into static assets, defer database initialization to explicit application startup, prune completed SSE task state, remove import-path hacks, and consolidate duplicate scrape APIs — while preserving all lanes, **Board Controls**, **Profile Manager**, **Spend Confirmation**, **Evaluation Lock**, and **Batch Poller** behavior.

## User Stories

1. As a maintainer, I want dashboard CSS in a dedicated static stylesheet, so that styling changes do not require editing a 4k-line HTML file.

2. As a maintainer, I want remaining inline JavaScript moved into focused static modules, so that board orchestration, search settings, and modal logic are reviewable in isolation.

3. As a job seeker, I want the dashboard to look and behave exactly as before the refactor, so that my daily triage workflow is unchanged.

4. As a maintainer, I want the HTML shell to only bootstrap modules and render structure, so that the entry document stays small and readable.

5. As a maintainer, I want completed SSE background tasks removed from server memory after a reconnect window, so that all-day dashboard sessions stay stable.

6. As a maintainer, I want **Job Tracker Database** initialization at application startup (not module import), so that test imports of the FastAPI app do not side-effect production DB paths unintentionally.

7. As a contributor, I want to run the dashboard without `sys.path.insert` hacks, so that imports match normal package layout when launched via `python -m src.web.run_dashboard`.

8. As a maintainer, I want existing dashboard HTML/JS tests updated to reference extracted assets, so that regressions in module wiring are caught automatically.

9. As a job seeker, I want **Enrich Job**, **Re-classify**, and job search Task Logs to stream over SSE identically, so that long-running actions remain observable.

10. As a job seeker, I want **Load More Contacts** to update the drawer immediately after confirmation, so that synchronous load-more behavior is preserved.

11. As a maintainer, I want **Batch Poller** startup and shutdown unchanged from a user perspective, so that **Scraped → Matched** transitions still occur after batch evaluation completes.

12. As a job seeker, I want the **Evaluation Lock** indicator and **Cancel** control to keep working during in-flight **Batch Evaluation Jobs**, so that search/backfill gating is unchanged.

13. As a job seeker, I want **Spend Confirmation** before Bright Data scrapes and paid Apify actions, so that cost gates still protect credits.

14. As a job seeker, I want **Profile Manager** (list, edit, import, active **Resume Profile** selection) to work unchanged, so that resume targeting for search and matching is unaffected.

15. As a job seeker, I want **Board Controls** (**Board Search**, **Refine board**, archived visibility, remote type filters) to behave identically, so that triage shortcuts are preserved.

16. As a job seeker, I want drag-and-drop lane moves across **Scraped**, **Matched**, **Accepted**, **Applied**, **Interviewing**, and **Rejected** to work as today, so that pipeline status updates are unchanged.

17. As a maintainer, I want `/api/health` to remain available for local ops checks, so that smoke tests and monitoring stay simple.

18. As a contributor, I want `python3 -m src.web.run_dashboard` to remain the documented entry command, so that README onboarding stays valid.

19. As a maintainer, I want duplicate scrape endpoints (`/api/search` and `/api/scrape`) consolidated internally with one deprecated alias preserved, so that the HTTP surface is clearer without breaking existing dashboard clients.

20. As a maintainer, I want **Batch Poller** log SSE (`/api/batch-poller/logs`) to continue streaming evaluation progress, so that assessing indicators stay accurate after refactors.

21. As a maintainer, I want static asset mounting under `/static` unchanged from the browser’s perspective, so that module import URLs keep working.

22. As a contributor, I want server startup to follow one lifespan pattern (startup/shutdown hooks), so that DB init, **Batch Poller**, and future background work share the same lifecycle model.

23. As a maintainer, I want a smoke test for `/api/health`, so that packaging and import refactors do not break the local server entrypoint.

24. As a maintainer, I want pytest imports of the FastAPI app to skip or isolate long-running background loops as they do today for **Batch Poller**, so that the test suite stays fast and deterministic after moving `init_db`.

## Implementation Decisions

### Frontend asset split

- Extract inline CSS (design tokens, lane layout, drawer, modals, **Profile Manager**, **Spend Confirmation**) into one or more stylesheets under the existing static mount.
- Extract remaining inline module script into static modules grouped by concern, for example: app bootstrap, search/**Job Search Settings**, **Spend Confirmation** controller, **Profile Manager**, evaluation-lock UI, batch-poller log client, and board orchestration glue.
- Keep existing extracted modules (`jobStore`, `boardRenderer`, `taskLogClient`, `drawerController`) as the core boundaries; move orchestration code that still lives inline into new modules rather than growing existing files without structure.
- HTML shell retains DOM structure, script tags with `type="module"`, and minimal boot wiring only.
- No visual redesign — class names and DOM hooks should remain stable enough that existing HTML/JS tests need only path/reference updates, not behavior rewrites.

### Backend bootstrap and packaging

- Move **Job Tracker Database** `init_db()` from module import time into FastAPI startup (alongside existing **Batch Poller** startup), guarded for pytest the same way background loops are skipped today.
- Remove `sys.path.insert` from web server and dashboard runner modules; rely on `python -m` execution from repo root.
- Preserve localhost-only binding in the dashboard runner; no authentication layer added.

### SSE task lifecycle

- Prune `active_tasks` entries after the SSE log stream completes and a short TTL expires, so reconnecting clients can still replay terminal logs during the window.
- Do not change Task Log event shape or task id generation.

### HTTP API surface

- Preserve all existing routes and Pydantic response models (`/api/jobs`, enrichment, reclassify, load-more, outreach settings, resumes, evaluation lock, batch poller logs).
- Implement `/api/search` and `/api/scrape` through one internal handler; mark the duplicate route deprecated in OpenAPI metadata while keeping response compatibility for the dashboard.

### Explicit non-goals inside implementation

- Do not change **Load More Contacts** from synchronous to background in this PRD.
- Do not alter Kanban lane names, **Enrichment** rules, or **Contact Sample Cache** semantics.

## Testing Decisions

Good tests assert externally observable behavior: HTTP responses, HTML asset references, SSE stream contents, and job board mutations — not private module layout.

- **Server lifecycle:** TestClient or lifespan context verifies `init_db` runs on startup, not on bare module import; `/api/health` returns 200.
- **SSE tasks:** Extend log-stream tests to confirm completed tasks are pruned after TTL without breaking replay for clients still connected.
- **Frontend wiring:** Update dashboard module tests and kanban JS helpers to assert new static CSS/JS paths are linked from the HTML shell.
- **Regression:** Full `pytest tests/` must pass; prioritize existing suites: dashboard modules, log stream, SSE refresh, DnD, profile manager, cost confirmations, evaluation lock, batch poller.
- **Seams:** highest useful seams are HTTP TestClient for API + file-content tests for asset wiring; no browser E2E required.

## QA Validation

- [ ] Run `python3 -m src.web.run_dashboard` → board loads at http://127.0.0.1:8000 with all lanes visible.
- [ ] Drag a **Matched Job** to **Accepted** → card moves lane and stays on the board.
- [ ] Click **Enrich Job** on an **Accepted Job** → spinner appears, Task Log streams, drawer shows contacts or **Enrichment Note**.
- [ ] Click **Load More Contacts** after **Spend Confirmation** → drawer updates with appended contacts or explanatory note.
- [ ] Start a job search from the dashboard → **Spend Confirmation** appears before scrape; new **Scraped Jobs** appear and later move to **Matched** when batch evaluation completes.
- [ ] While jobs are assessing → search/backfill controls disabled and **Cancel** on the evaluation lock releases the lock.
- [ ] Open **Manage Profiles** → list, edit, and active **Resume Profile** selection still work.
- [ ] Leave the dashboard open through several enrichments and searches → UI remains responsive with no obvious slowdown.

## Out of Scope

- Authentication, HTTPS, or exposing the dashboard beyond localhost.
- Visual redesign, new Kanban features, or lane model changes.
- Playwright/browser E2E replacing current HTTP/HTML string tests.
- Making **Load More Contacts** asynchronous.
- **Contacted Elsewhere** performance work (separate PRD).
- Pre-commit hooks or CI asset pipelines (see Developer Tooling PRD #111).

## Further Notes

Current scale (approximate): ~4,500 lines in the HTML shell, ~2,400 lines inline CSS, ~2,000 lines inline module JS, plus ~1,470 lines across four existing static JS modules. **Batch Poller** already uses FastAPI startup/shutdown; this PRD extends that lifecycle pattern to database initialization and task cleanup. Pair with PRD #111 for CI coverage when static assets move.
