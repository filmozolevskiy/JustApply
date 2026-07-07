# [PRD] Company Research (Glassdoor)

> **GitHub Issue:** [#138](https://github.com/filmozolevskiy/JustApply/issues/138)

## Problem Statement

Before accepting or applying to a role, a job seeker needs employer context that LinkedIn listings do not provide: company size, employee ratings, recommend-to-friend percentage, salary bands for the role, and interview-process notes. Today this requires leaving the **Kanban Dashboard** and manually searching Glassdoor, with no way to reuse results across multiple cards at the same employer. Paid Apify calls must stay gated and predictable — the feature must not bundle into **Enrichment** or run automatically on lane moves.

## Solution

Add **Company Research**: a manual drawer action on **Matched Jobs** and later lanes that fetches Glassdoor employer intelligence via Apify, caches employer-wide data in a **Company Research Cache**, denormalizes title-specific slices onto each job's **`companyResearch`** JSON field, and renders results in a dedicated **Glassdoor Company Research** drawer section (Metrics grid layout). **Spend Confirmation** appears only when at least one billable Apify operation will run; the modal shows cached vs billable slices, an editable **Glassdoor job title**, and estimated run count. Wrong matches are corrected via **Wrong company?** without manual cache surgery.

## User Stories

1. As a job seeker on a **Matched Job**, I want a **Research company** action in the job drawer, so that I can evaluate employer reputation before dragging to **Accepted**.

2. As a job seeker on an **Accepted Job**, I want **Company Research** available alongside enrichment actions, so that I can check Glassdoor data while preparing outreach.

3. As a job seeker on **Applied** or **Interviewing** jobs, I want **Company Research** still available, so that I can refresh employer context during later pipeline stages.

4. As a job seeker, I want **Company Research** never to run automatically when I move a card between lanes, so that Apify spend stays deliberate.

5. As a job seeker, I want **Company Research** separate from **Enrich Job**, so that contact sourcing and employer research do not multiply Apify runs in one action.

6. As a job seeker, I want Glassdoor lookup to use the job's company name, so that research works even when Bright Data omits `companyUrl`.

7. As a job seeker, I want the system to auto-select the best Glassdoor employer match on first fetch, so that research is one click in the common case.

8. As a job seeker, I want the drawer to show the matched Glassdoor employer name, so that I can spot a wrong company without comparing silently cached data.

9. As a job seeker, I want **LinkedIn Company Slug** from `companyUrl` to break ties among similar Glassdoor search results, so that employers like FlightHub match the LinkedIn page when names are ambiguous.

10. As a job seeker, I want a **Wrong company?** action after research, so that I can pick a different Glassdoor profile when auto-match fails (e.g. QualiTest vs global Qualitest).

11. As a job seeker, I want **Wrong company?** to clear the employer's **Company Research Cache** and show top Glassdoor search results to pick from, so that a bad match does not stick for every job at that company name.

12. As a job seeker, I want employer-wide Glassdoor data fetched once per normalized company name, so that researching a second job at the same employer does not re-bill overview operations.

13. As a job seeker, I want salary and interview data keyed by **Glassdoor job title**, so that different roles at the same employer can have distinct slices without overwriting each other.

14. As a job seeker, I want a full cache hit to run with no **Spend Confirmation** modal, so that revisiting researched employers stays friction-free.

15. As a job seeker, I want **Spend Confirmation** only when at least one Apify operation will execute, so that I am not prompted when everything is already cached.

16. As a job seeker, I want the spend modal to list which slices are cached vs billable (search, overview, salaries, interviews), so that I understand exactly what I am paying for.

17. As a job seeker, I want an editable **Glassdoor job title** in **Spend Confirmation** defaulting to the listing title, so that I can shorten noisy titles (e.g. "Senior QA Engineer (Hybrid)" → "QA Engineer") before salary/interview lookup.

18. As a job seeker, I want the submitted **Glassdoor job title** to drive salary and interview cache keys and drawer labels, so that results match what I searched for on Glassdoor.

19. As a job seeker, I want the spend modal to show estimated Apify run count and cost before **Proceed**, so that spend aligns with existing **Enrich Job** / **Load More Contacts** patterns.

20. As a job seeker, I want a **Refresh** action after research, so that I can update stale Glassdoor data without using **Wrong company?**.

21. As a job seeker, I want **Refresh** to skip cached slices and fetch only missing or explicitly refreshed billable operations, so that refresh is cheaper than a full re-fetch when possible.

22. As a job seeker, I want a dedicated **Glassdoor Company Research** section below **Job Info** in the drawer, so that employer intel is visually separate from listing fields and outreach.

23. As a job seeker, I want the researched layout to show three metric tiles — company size, overall rating with review count, and recommend % — so that headline employer stats scan quickly.

24. As a job seeker, I want a salary row labeled with the **Glassdoor job title** used for lookup, so that I know which role the median base pay refers to.

25. As a job seeker, I want up to three interview snippet cards (difficulty, outcome, summary), so that I get a short interview-process picture without a long prose block.

26. As a job seeker, I want missing Glassdoor fields to display as `n/a`, so that sparse employers (e.g. no salary submissions) still show useful partial data.

27. As a job seeker, I want the section header to include a green Glassdoor badge link to the matched employer overview when research exists, so that I can open the full Glassdoor page in one click.

28. As a job seeker, I want the empty state to show a brief explainer and **Research company** CTA, so that I understand what the action does before spending credits.

29. As a job seeker, I want a loading state with spinner and "Researching employer on Glassdoor…" while the run is in progress, so that I know the action is working.

30. As a job seeker, I want **Company Research** to show Glassdoor employer size only — not the listing's Bright Data `size` field — so that this section stays a single authoritative Glassdoor view.

31. As a job seeker, I want **Company Research** not to change my job's pipeline status or lane, so that research is informational only.

32. As a job seeker, I want progress messages in **Task Logs** during a research run, so that I can audit Apify activity in real time.

33. As a job seeker, I want completion, failure, and **Wrong company?** outcomes in the job's **Job Activity Log**, so that research history is visible per card.

34. As a job seeker, I want infrastructure failures (Apify errors, timeouts, missing token) not cached, so that a retry after fixing credentials can succeed.

35. As a job seeker, I want successful empty salary or interview responses cached for a title, so that repeat lookups for the same title do not re-bill.

36. As a job seeker researching two jobs at the same company with different titles, I want each job's drawer to show its own denormalized **`companyResearch`** snapshot, so that cards reflect the title-specific slices fetched for that role.

37. As a job seeker, I want **Company Research** unavailable or hidden on **Scraped** and **Rejected** lanes (per product scope), so that research targets triage-and-later stages only.

38. As a job seeker, I want no Kanban card badge summarizing research in v1, so that the board stays uncluttered until a later polish pass.

## Implementation Decisions

### Apify integration

- Actor: `sian.agency~glassdoor-data-scraper` (distinct from LinkedIn **Contact Sample** actor).
- Operations (each operation = one Apify actor run unless cache skips it):
  - `companySearch` — resolve Glassdoor company ID from job company name.
  - `companyOverview` — size, overall rating, review count, recommend %.
  - `companySalaries` — median base pay for submitted **Glassdoor job title**.
  - `companyInterviews` — popular interview reports for submitted title (cap pages in v1 consistent with prototype, e.g. 2 pages, up to 3 summarized snippets).
- Reuse existing Apify run/poll patterns from **Contact Sample**; extract shared actor runner only if it reduces duplication without scope creep.
- Promote prototype logic from the standalone Glassdoor script into a core module; keep the script as a thin CLI wrapper for manual probes.
- Cost estimate uses the same per-run constant as other Apify gates (~$0.05/run); full miss ≈ 4 runs (~$0.20); partial cache hits reduce runs proportionally.

### Company matching

- On first fetch for a normalized company name with no cached Glassdoor company ID: run `companySearch`, auto-pick best match by name similarity (exact → substring → first result).
- Tie-break among similar candidates using **LinkedIn Company Slug** when `companyUrl` is present (compare slug tokens to Glassdoor employer identifiers/names where available).
- Store chosen `glassdoorCompanyId` and `matchedName` in **Company Research Cache**; show `matchedName` in drawer so mismatches are visible.
- **Wrong company?**: clear cache row for that employer key; run `companySearch`; present top ~3 results in a picker; user selection persists new ID/name then runs remaining billable slices.

### Hybrid storage

**Company Research Cache** (employer-wide, keyed by normalized company name):

- Fields: `glassdoorCompanyId`, `matchedName`, `companySize`, `rating`, `reviewCount`, `recommendPercent`, `fetchedAt`.
- Title-keyed maps: `salariesByTitle`, `interviewsByTitle` (keys = normalized submitted **Glassdoor job title**).
- Cache hit on employer-wide fields skips `companySearch` + `companyOverview` when ID and overview are present.
- Cache hit on title maps skips `companySalaries` / `companyInterviews` for that title.
- Do not cache infrastructure failures; do cache successful empty salary/interview responses for a title.

**Job row denormalization** — single JSON column `companyResearch` on `jobs` (Pydantic field on **Job** model):

```json
{
  "glassdoorCompanyId": "882104",
  "matchedName": "FlightHub",
  "companySize": "51 to 200 Employees",
  "rating": 2.8,
  "reviewCount": 246,
  "recommendPercent": 40,
  "glassdoorJobTitle": "QA Engineer",
  "salary": { "medianBaseSalary": 85000, "currency": "USD", "sampleSize": 42 },
  "interviews": [
    {
      "jobTitle": "QA Engineer",
      "difficulty": "Average",
      "outcome": "Accepted offer",
      "processSummary": "…"
    }
  ],
  "fetchedAt": "2026-07-06T12:00:00Z"
}
```

(Shape trimmed from UI prototype — omit internal `sources` debug fields in persisted snapshot.)

### API and orchestration

- **Preflight** `GET /api/jobs/{job_id}/company-research-preflight`:
  - Accept optional `glassdoorJobTitle` query (default listing title).
  - Return: `will_call_apify`, `estimated_runs`, `estimated_cost`, `cached_slices[]`, `billable_slices[]`, `default_glassdoor_job_title`, cached preview when job already has `companyResearch` or cache row exists.
- **Run** `POST /api/jobs/{job_id}/company-research`:
  - Body: `{ "glassdoorJobTitle": "…" }`.
  - Lane guard: **Matched** and later only.
  - Executes only billable operations; updates cache + job `companyResearch`; streams progress to **Task Logs**; appends **Job Activity Log** on terminal outcome.
- **Repick** `POST /api/jobs/{job_id}/company-research/repick`:
  - Body: `{ "glassdoorCompanyId": "…", "matchedName": "…", "glassdoorJobTitle": "…" }`.
  - Clears employer cache, sets new match, fetches billable slices, updates job snapshot.
- **Search candidates** (optional sub-endpoint or embedded in repick preflight): return top Glassdoor search rows for picker UI after cache clear.
- Background execution mirrors enrich/reclassify task pattern (SSE or existing task log streaming) — implementation follows current dashboard conventions.

### Kanban UI (Variant A — Metrics grid, chosen 2026-07-06)

- New drawer section below **Job Info**: header **Glassdoor Company Research** + green **G** badge link (inline SVG) to Glassdoor overview when researched; actions **Research company** (empty) / **Refresh** + **Wrong company?** (researched).
- Layout: three metric tiles; salary row; up to three interview cards; no separate "Interview process" heading; no Bright Data listing size row.
- **Spend Confirmation**: reuse shared modal; body lists cached vs billable slices, editable **Glassdoor job title**, run count, estimated cost; subtitle "Glassdoor via Apify".
- Lane gate: show section/actions on **Matched**, **Accepted**, **Applied**, **Interviewing**; hide on **Scraped** / **Rejected** / **Archived** (align with glossary).
- Remove throwaway prototype route and assets after production drawer ships.

### Logging

- **Task Logs**: step-level lines during run (operation name, cache hit/skip, employer matched).
- **Job Activity Log** examples:
  - Success: `Company research · 2.8★ · 40% recommend · QA Engineer salary n/a`
  - Failure: `Company research failed · Apify timeout`
  - Repick: `Company research · employer changed to QualiTest Group`

### Relationship to existing ADRs

- Follows ADR 0007 paid-action confirmation philosophy (confirm only when billable; no auto-trigger on lane drag).
- Distinct actor, cache table, and cache key from **Contact Sample Cache** (ADR 0006/0007) — no shared cache row.
- Uses app-styled **Spend Confirmation** modal per ADR 0012 (not native `confirm()`).

### Suggested delivery slices

1. Core module + **Company Research Cache** table + `companyResearch` column migration + preflight/run API + tests (mocked Apify).
2. Drawer UI + spend modal wiring + task log streaming + activity log.
3. **Wrong company?** picker flow + repick endpoint.
4. Delete prototype route/files; optional ADR for Glassdoor via Apify.

## Testing Decisions

**Good test rule:** Assert external behavior — cache skip counts, billable run lists, lane guards, persisted `companyResearch` shape, activity log messages — not internal Apify poll loop details.

**Preferred seams (highest first):**

1. **HTTP preflight + run + repick endpoints** — JSON contracts drive spend gating and slice math; mirror `test_load_more_stream_aware.py` preflight patterns.
2. **Core Glassdoor intel module with mocked Apify** — fixtures from Qualitest / FlightHub prototype runs; assert normalized report shape and interview summarization cap (3 snippets).
3. **Company Research Cache module** — employer-wide hit, title-level hit/miss, repick clears row, infrastructure error not cached; mirror `test_contact_sample_cache.py`.
4. **Pipeline/service orchestration** — partial cache (overview hit, salary miss) executes only billable operations; job row snapshot updated.
5. **Dashboard static assertions** — drawer section strings, lane gates, spend modal includes `glassdoorJobTitle` field; mirror `test_cost_confirmations.py` and `test_load_more_contacts.py` drawer tests.

**Prior art:** `test_load_more_stream_aware.py`, `test_cost_confirmations.py`, `test_contact_sample_cache.py`, `test_activity_log.py`, prototype script manual runs on Qualitest and FlightHub.

**Not tested at browser level:** Live Apify Glassdoor actor (manual smoke with `APIFY_API_TOKEN`); pytest mocks actor boundary.

## QA Validation

- [ ] Open a **Matched** job with no prior research → **Glassdoor Company Research** shows empty state with **Research company** → click → if billable, **Spend Confirmation** lists slices + editable **Glassdoor job title** → **Proceed** → section shows metric tiles, salary row, and/or `n/a` where sparse → green **G** link opens Glassdoor overview for matched employer.
- [ ] Open a second **Matched** job at the same company with the same **Glassdoor job title** after first job researched → click **Research company** → no spend modal → drawer populates immediately from cache.
- [ ] Research a job with a long listing title → in spend modal shorten title to e.g. "QA Engineer" → proceed → salary row label shows submitted title → different title on another card at same company triggers billable salary/interview slices only.
- [ ] Complete research on a **Matched** job → drag to **Accepted** → research section still shows prior data → **Refresh** available.
- [ ] On researched job click **Wrong company?** → picker shows alternative Glassdoor employers → select one → confirm if billable → drawer updates **matchedName** and metrics → **Job Activity Log** records employer change.
- [ ] Open **Scraped** or **Rejected** job drawer → **Company Research** section not offered.
- [ ] Simulate missing `APIFY_API_TOKEN` (or cancel run) → drawer shows failure state or task log error → retry after token restored succeeds without requiring manual cache clear.
- [ ] During research run → **Task Logs** show progressing Glassdoor steps → on completion **Job Activity Log** on that card shows research outcome.

## Out of Scope

- Kanban card badges summarizing rating/recommend % (v1).
- Auto-fetch on scrape, **Enrich Job**, **Load More Contacts**, or lane moves.
- Bundling Glassdoor fetch into **Enrichment** pipeline.
- Bright Data Glassdoor scraper integration.
- Showing or comparing Bright Data listing `size` inside **Glassdoor Company Research** section.
- Bulk **Company Research** on multi-select cards.
- Filtering or sorting the board by Glassdoor rating (JSON column not indexed for SQL filters in v1).
- CLI `--promote` or search pipeline changes.
- Separate Applications table or non-`jobs` persistence.
- ADR document authorship (recommended follow-up, not blocking MVP).

## Further Notes

- Prototype UI validated at `/prototype/company-research` — **Variant A (Metrics grid)** chosen; reference markup in prototype JS/CSS until production drawer lands.
- Live prototype runs: Qualitest highlighted wrong-company risk (small entity vs global firm); FlightHub matched correctly but sparse QA salary/interview data — motivates editable **Glassdoor job title** and **Wrong company?**.
- Glossary terms **Company Research**, **Company Research Cache**, and **LinkedIn Company Slug** are already defined in `CONTEXT.md` from the design grill session.
- Recommended follow-up ADR: Glassdoor via Apify, separate from LinkedIn contact sourcing, hybrid cache + job snapshot model.
