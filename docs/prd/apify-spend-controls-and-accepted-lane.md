# [PRD] Apify Spend Controls and Accepted Lane

> **ADR:** [0007-apify-spend-controls-and-accepted-lane.md](../adr/0007-apify-spend-controls-and-accepted-lane.md)
>
> **GitHub Issue:** _(link added when published)_

## Problem Statement

Apify spend on Contact Sample enrichment was far higher than the number of companies actually enriched. Dragging a job card to the **Enriching** lane triggered paid Apify runs accidentally. Slug fallback issued multiple Apify calls per enrichment when the Bright Data `companyUrl` did not match. **Refresh Contacts** busted the Contact Sample Cache and re-scraped page 1, re-billing for profiles already fetched. Empty Apify responses were not cached, so retries on barren company pages billed again. The Kanban workflow also split enrichment across three lanes (**Sourced**, **Enriching**, **Enriched**), which encouraged accidental spend and obscured that enrichment is an in-place action on a job the user has already accepted.

## Solution

Redesign the Kanban pipeline and enrichment controls so Apify runs happen only when the user explicitly clicks a paid action, with cost confirmation before each paid fetch. Rename **Sourced** to **Found** and collapse **Enriching** / **Enriched** into a single **Accepted** lane. Enrichment runs in place on **Accepted Jobs** — the card never leaves Accepted; an on-card spinner shows progress. Apify fetches use `companyUrl` only (no name-based slug guessing), 25 profiles per page, append-only Contact Sample Cache with page tracking, cached empty results, and **Load More Contacts** instead of **Refresh Contacts**. **Re-classify** re-runs LLM classification on cached profiles for free after **Outreach Settings** changes. Existing `sourced`, `enriching`, and `enriched` statuses migrate to `found` and `accepted` on upgrade.

## User Stories

1. As a job seeker, I want the first Kanban lane labeled **Found**, so that I understand these are newly discovered listings I have not yet decided to pursue.

2. As a job seeker, I want jobs I decide to pursue in a single **Accepted** lane, so that I do not confuse “accepted for outreach” with “currently enriching” or “already enriched.”

3. As a job seeker, I want dragging a card from **Found** to **Accepted** to move the lane only, so that I never trigger a paid Apify call by accident.

4. As a job seeker, I want dragging a card between any lanes to never start enrichment, so that lane moves are always free and predictable.

5. As a job seeker, I want **Enrich Job** to move a **Found Job** to **Accepted** if needed and then run enrichment in place, so that one button handles both acceptance and first Contact Sample fetch.

6. As a job seeker, I want my **Accepted Job** card to stay in **Accepted** while enrichment runs, so that the board layout does not shift mid-task.

7. As a job seeker, I want a spinner badge on my **Accepted** card while enrichment is in progress, so that I can see work is running without a separate **Enriching** lane.

8. As a job seeker, I want the pipeline status to remain **Accepted** during enrichment, so that status reflects my decision to pursue the role, not the technical sub-step.

9. As a job seeker, I want **Enrich Job** to confirm cost only when an Apify fetch will run (Contact Sample Cache miss), so that I am not nagged when the cache already has profiles.

10. As a job seeker, I want **Enrich Job** on a cache hit to re-classify without a cost dialog, so that repeated enrichment on the same company is free when profiles are already cached.

11. As a job seeker, I want Apify to be called only with the job’s Bright Data `companyUrl`, so that the system does not guess LinkedIn slugs and multiply charges.

12. As a job seeker, I want enrichment to fail fast with an **Enrichment Note** when `companyUrl` is missing, so that I understand why no contacts appeared and no Apify credits were spent.

13. As a job seeker, I want zero-profile Apify responses cached, so that retrying enrichment on a company with no employees does not bill me again.

14. As a job seeker, I want infrastructure failures (Apify trigger error, timeout, missing credentials) not cached, so that a transient error can succeed on retry.

15. As a job seeker, I want the Contact Sample Cache to never be busted, so that previously fetched profiles are never discarded and re-billed.

16. As a job seeker, I want **Load More Contacts** to append the next page of up to 25 profiles, so that I can expand the Contact Sample when the first page lacks enough **Outreach Audience** matches.

17. As a job seeker, I want **Load More Contacts** to confirm estimated Apify cost before every page fetch, so that each additional page is a deliberate paid action.

18. As a job seeker, I want no cap on how many pages I can load, so that I can keep fetching until Apify returns no further pages or I stop manually.

19. As a job seeker, I want **Load More Contacts** only on **Accepted Jobs**, so that the first employee sample always comes from **Enrich Job**.

20. As a job seeker, I want **Re-classify** on an **Accepted Job**, so that I can apply new **Outreach Settings** toggles without calling Apify.

21. As a job seeker, I want **Re-classify** to skip cost confirmation, so that I know LLM re-classification is free.

22. As a job seeker, I want **Re-classify** to regenerate Outreach Message Templates from the cached Contact Sample, so that my drafts reflect the new audience selection.

23. As a job seeker, I want **Refresh Contacts** removed and replaced by **Load More Contacts**, so that I am never offered an action that throws away cached pages and re-scrapes page 1.

24. As a job seeker, I want existing jobs in `sourced` migrated to `found`, so that my board matches the new naming after upgrade.

25. As a job seeker, I want existing jobs in `enriching` and `enriched` migrated to `accepted`, so that I do not lose jobs in obsolete lanes.

26. As a job seeker, I want the final lane order to be Found → Accepted → Contacted → Interviewing → Rejected, so that the pipeline reads left-to-right as my decision flow.

27. As a job seeker, I want **Enrichment Failure** jobs to remain in **Accepted** with an **Enrichment Note**, so that I can fix upstream data or try **Load More Contacts** without the card jumping lanes.

28. As a job seeker, I want **Enrichment Failure** to still produce both Recruiter and Russian Speaker Outreach Message Templates, so that I can cold-connect manually even with zero classified contacts.

29. As a job seeker, I want Contact Sample Cache hits logged in Task Logs and **Job Activity Log**, so that I can audit when Apify was skipped.

30. As a job seeker, I want the local dashboard to use real Apify when `APIFY_API_TOKEN` is set, so that enrichment during local job hunting behaves like production.

31. As a job seeker, I want archived cards draggable to non-enrichment lanes without triggering Apify, so that archive management stays consistent with the no-drag-enrich rule.

32. As a job seeker, I want **Enrich Job** available from **Found** and **Accepted**, so that I can start enrichment from either stage without dragging first.

33. As a job seeker, I want the drawer to show **Load More Contacts** only when enrichment has already run (Accepted with cached sample), so that button placement matches the append-only workflow.

34. As a job seeker, I want Task Logs to report “Fetching up to 25 employees…” on first fetch, so that log output matches the reduced Contact Sample size.

35. As a job seeker, I want the CLI `--promote` flow updated to use `found` / `accepted` statuses, so that automated promotion aligns with the new Kanban model.

## Implementation Decisions

### Kanban lanes and job status

- Replace DB status `sourced` with `found`; rename the first lane **Found**.
- Replace DB statuses `enriching` and `enriched` with `accepted`; remove **Enriching** and **Enriched** lanes.
- Final lane order: **Found** → **Accepted** → **Contacted** → **Interviewing** → **Rejected**.
- One-time DB migration on init/upgrade: `sourced` → `found`; `enriching` and `enriched` → `accepted`.
- Lane drag updates status only; never calls enrichment endpoints.

### Enrichment lifecycle

- **Enrich Job** (Found or Accepted): ensure status is `accepted`, then start enrichment background task. Card stays in **Accepted** throughout.
- In-progress signal: client-side spinner badge on the card (e.g. “Enriching…”); optional server flag or task-id correlation for SSE refresh. DB status remains `accepted`.
- Remove coordinator transitions to `enriching` / `enriched`. Coordinator (or successor) owns “enrichment in flight” without changing pipeline lane.
- On enrichment completion: persist contacts, templates, **Enrichment Note** (cleared on success); status stays `accepted`.
- On **Enrichment Failure**: status stays `accepted`; set **Enrichment Note**; still generate both audience templates.

### Apify fetch policy

- `CONTACT_SAMPLE_SIZE` = 25 (`maxItems: 25`).
- Single Apify attempt per fetch using normalized Bright Data `companyUrl` only.
- Remove slug fallback (`company_slug_candidates` loop after URL miss).
- Missing or unusable `companyUrl`: skip Apify; return **Enrichment Failure** with explanatory **Enrichment Note**; zero Apify spend.
- No `MOCK_APIFY` environment flag — local dashboard uses real Apify when token is present; tests continue to mock Apify at the actor boundary.

### Contact Sample Cache

- Key remains LinkedIn company slug derived from `companyUrl` (not display name).
- Append-only: never delete/bust cache on user action. Remove `bust_cache` parameter from enrichment API and pipeline.
- Cache successful empty lists (zero profiles) to prevent repeat billing on barren companies.
- Do not cache infrastructure failures.
- Add page tracking column(s): e.g. `pages_fetched` count. Next Apify call passes `startPage = pages_fetched + 1` and `takePages = 1`.
- On cache hit for **Enrich Job**: use cached profiles; skip Apify; still run classification and template generation.
- On **Load More Contacts**: fetch next page, append profiles to cache (dedupe by normalized profile URL), increment page count, re-classify combined sample.

### API and UI actions

- Keep `POST /api/jobs/{id}/enrich` for **Enrich Job** (no bust).
- Replace `POST /api/jobs/{id}/refresh-contacts` with `POST /api/jobs/{id}/load-more-contacts` (append page; no status change to enriching).
- Add `POST /api/jobs/{id}/reclassify` — runs classification + template generation on cached sample only; no Apify.
- Drawer buttons: **Enrich Job** (Found/Accepted per rules), **Load More Contacts** (Accepted after prior enrichment/cache), **Re-classify** (Accepted with cache).
- Remove **Refresh Contacts** button and all bust-cache UI.

### Cost confirmations (client-side)

- **Enrich Job**: show confirmation dialog only when server indicates cache miss / Apify required (e.g. preflight endpoint or cache metadata in job payload). Dialog shows estimated cost (~$0.22 per first page).
- **Load More Contacts**: always confirm before POST; show estimated cost per page.
- **Re-classify**: no confirmation.

### Status PUT endpoint

- `PUT /api/jobs/{id}/status` accepts `found`, `accepted`, `contacted`, `interviewing`, `rejected` only.
- Reject drag-to-`enriching` / auto-enrich on status change.

### Documentation alignment

- ADR 0007 is canonical for this feature.
- CONTEXT.md glossary already defines **Found Job**, **Accepted Job**, **Load More Contacts**, **Re-classify**, and updated **Contact Sample Cache** behavior.

## Testing Decisions

Tests assert **external behavior** at the highest practical seams — HTTP API responses, DB state after operations, Task Log messages, and static/UI wiring — not internal private helpers.

### Seam 1 — Contact Sample sourcing (`source_contacts`)

- **What:** Cache hit/miss, empty-result caching, append-on-load-more, no slug fallback, missing `companyUrl` short-circuit, infrastructure errors not cached.
- **How:** Mock `_run_apify_actor` / Apify HTTP (existing pattern in `test_contact_sample_cache.py`, `test_enrichment_pipeline.py`).
- **Prior art:** `tests/test_contact_sample_cache.py`, `tests/test_enrichment_pipeline.py`.

### Seam 2 — Enrichment pipeline (`run_enrichment_pipeline`)

- **What:** Outcomes set **Enrichment Note** correctly; job ends in `accepted` (not `enriched`); templates generated on failure; classification runs on cache hit.
- **How:** Mock `source_contacts` and LLM generators; use temp DB fixture.
- **Prior art:** `tests/test_enrichment_pipeline.py`, `tests/test_enrichment_coordinator.py` (update for new status model).

### Seam 3 — HTTP API (`FastAPI TestClient`)

- **What:** `POST /enrich`, `POST /load-more-contacts`, `POST /reclassify`, status PUT with new enum; no enriching status on begin; migration maps old statuses.
- **How:** `TestClient` against `app` with patched background tasks and mocked `complete_enrichment`.
- **Prior art:** `tests/test_refresh_contacts.py` (rename/refocus), `tests/test_dashboard_jobs.py`.

### Seam 4 — DB migration

- **What:** After `init_db` on a DB seeded with old statuses, rows read as `found` / `accepted`.
- **How:** Insert legacy rows, run migration, assert via `get_job` / `GET /api/jobs`.
- **Prior art:** Similar migration tests elsewhere in `tests/` for schema upgrades.

### Seam 5 — Dashboard UI wiring (static / Node subprocess)

- **What:** Lanes `found` and `accepted` present; enriching/enriched lanes absent; no drag-to-enrich; confirmation hooks for paid actions; spinner badge markup; **Load More Contacts** / **Re-classify** buttons; no **Refresh Contacts**.
- **How:** HTML/JS string assertions and Node module tests (`tests/test_dashboard_dnd.py`, `tests/test_dashboard_modules.py`, `kanban_js.py`).
- **Prior art:** `tests/test_dashboard_dnd.py`, `tests/test_dashboard_modules.py`.

### Seam 6 — Coordinator / service layer

- **What:** Idempotent begin while in-flight; abort/revert behavior updated for `accepted`-only model (no revert to `sourced`/`enriched`).
- **Prior art:** `tests/test_enrichment_coordinator.py`, `tests/test_job_hunter_service.py`.

**Good test rule:** Each test names one user-visible or API-contract outcome. Avoid asserting call order of internal helpers unless it maps to a billed Apify call count.

## QA Validation

- [ ] Open Kanban Dashboard → lanes read **Found**, **Accepted**, **Contacted**, **Interviewing**, **Rejected** (no Enriching/Enriched/Sourced)
- [ ] Drag a **Found** card to **Accepted** → card moves; no cost confirmation; Task Logs show no Apify fetch
- [ ] Click **Enrich Job** on a **Found** card with no cached Contact Sample → cost confirmation appears → confirm → card in **Accepted** with spinner → enrichment completes; card stays **Accepted**
- [ ] Click **Enrich Job** on an **Accepted** job whose company is already cached → no cost confirmation → contacts/templates update; Task Logs show cache hit
- [ ] Click **Enrich Job** on a job missing company URL → no confirmation; **Enrichment Note** explains missing URL; no Apify charge
- [ ] Open drawer on enriched **Accepted** job → **Load More Contacts** visible; **Refresh Contacts** absent
- [ ] Click **Load More Contacts** → cost confirmation → confirm → new contacts may appear; running again shows another confirmation
- [ ] Change **Outreach Settings** → click **Re-classify** on one job → contacts/templates update with no cost confirmation
- [ ] Drag any card to any lane → never shows enrichment confirmation or starts spinner unless **Enrich Job** / **Load More Contacts** clicked
- [ ] Reject a job via hover control or drag to **Rejected** → works as before; no enrichment triggered

## Out of Scope

- `MOCK_APIFY` flag for local development.
- Automatic re-classify of all **Accepted** jobs when **Outreach Settings** save.
- Page cap on **Load More Contacts**.
- Switch to Apify “Short” profile mode ($4/1k) — deferred; keep full profiles at 25/page.
- Slug fallback for companies without `companyUrl`.
- Changes to Bright Data job scraping or Resume Matcher pipeline.
- CLI `--search` behavior beyond status enum alignment for `--promote`.

## Further Notes

- Estimated Apify cost: ~$0.22 per page (25 full profiles + actor start), per ADR 0007 investigation.
- ADR 0006 **Refresh Contacts** and empty-cache rejection are superseded.
- ADR 0005 lane-triggered enrichment transitions are partially superseded.
- Implementation slices can follow `docs/issues/` pattern (parent PRD + child tickets) once this issue is published.
- **Testing seams (for implementer):** highest seams are HTTP API + `source_contacts` + static UI wiring; confirm these match your expectations before slicing work.
