# [PRD] Apify Job-Scrape Sources (LinkedIn first)

> **GitHub Issue:** [#200](https://github.com/filmozolevskiy/JustApply/issues/200)  
> **Wayfinder map:** [#194](https://github.com/filmozolevskiy/JustApply/issues/194)  
> **Actor pick:** [#199](https://github.com/filmozolevskiy/JustApply/issues/199)  
> **Prior draft ticket:** [#198](https://github.com/filmozolevskiy/JustApply/issues/198)

## Problem Statement

Job listing scrape today is Bright Data–only via the **Source Platform** switcher (`brightdata_linkedin`). The product already pays for **Apify** for **Enrichment** (**Contact Sample**) and **Company Research**, so LinkedIn listing scrape cannot share that bill. We want a second LinkedIn scrape option on Apify, and a documented path to Indeed and Glassdoor listings later, without inventing a second vendor stack or removing Bright Data.

## Solution

Add **`apify_linkedin`** to the **Source Platform** switcher beside **`brightdata_linkedin`**. When selected, the scrape phase of the **Search & Evaluation Pipeline** calls Apify Actor `curious_coder/linkedin-jobs-scraper` (public guest LinkedIn jobs search, no cookies), normalizes rows into the same Job shape used after Bright Data, dedupes, saves into **Scraped**, then continues **Batch Evaluation** unchanged.

**Spend Confirmation** estimates Apify PPE for that Actor (`Search Regions × Per-Region Limit × $0.001`). Bright Data remains available and is not removed.

Indeed (`misceres/indeed-scraper` → `apify_indeed`) and Glassdoor listings (`valig/glassdoor-jobs-scraper` → `apify_glassdoor`) are **reserved and documented only** — v1 must not expose or wire them.

## User Stories

1. As a job seeker, I want a **Source Platform** option **LinkedIn (Apify)** next to **LinkedIn (Bright Data)**, so that I can scrape listings on the Apify bill I already pay.

2. As a job seeker, I want **LinkedIn (Bright Data)** to remain the default **Source Platform**, so that existing workflows do not change until I opt in.

3. As a job seeker, I want choosing **LinkedIn (Apify)** to use the same **Search Regions**, **Per-Region Limit**, query, and refine preferences as today, so that I do not learn a second search UX.

4. As a job seeker, I want **Spend Confirmation** before an Apify LinkedIn scrape to show volume ceiling and estimated USD from that Actor’s PPE rate, so that I am not shown a fake Bright Data $/record number.

5. As a job seeker, I want the Apify spend modal subtitle and line items to name Apify LinkedIn scrape explicitly, so that I know which vendor I am about to pay.

6. As a job seeker, I want Bright Data scrapes to keep their existing per-record spend estimate, so that switching platforms does not break Bright Data cost UX.

7. As a job seeker, I want Apify LinkedIn listings to land in **Scraped** like Bright Data listings, so that **Batch Evaluation Jobs** and the Kanban lanes work unchanged.

8. As a job seeker, I want Apify LinkedIn rows to carry LinkedIn **`companyUrl`** when the Actor returns `companyLinkedinUrl`, so that **Enrichment** / **Contact Sample** still works on **Accepted** cards.

9. As a job seeker, I want Apify LinkedIn rows missing `companyUrl` to still save and evaluate, with Enrichment skipping Apify contact fetch (today’s miss path), so that scrape success is not blocked on Enrichment.

10. As a job seeker, I want job-poster fields from the Actor mapped into preliminary contacts when present (same idea as Bright Data job poster), so that Poster badges still appear when available.

11. As a job seeker, I want title, company, link, location, date, description, employment type, salary, seniority, remote type, and company size mapped from the Actor when available, so that the drawer and **Resume Matcher** see complete enough jobs.

12. As a job seeker, I want existing URL / stable listing-id dedup to apply to Apify LinkedIn scrapes, so that re-running search does not flood **Scraped** with duplicates.

13. As a job seeker, I want company-size and **Employment Type** post-normalize filters already used after Bright Data to apply after Apify normalize, so that refine preferences stay consistent across vendors.

14. As a job seeker, I want mock scrape mode to cover the Apify LinkedIn path (no live Actor call), so that local/dev and CI stay free.

15. As a job seeker, I want a mock-evaluation run to still avoid billable Apify LinkedIn scrape when mock scrape rules say so, so that I cannot accidentally burn credits during mock eval.

16. As a job seeker, I want fail-fast credit-protection behavior to apply to Apify LinkedIn scrapes like Bright Data, so that runaway loops cannot burn credits.

17. As a job seeker, I want scrape-slot / rate-limit acquisition to apply when the chosen platform will spend real credits, so that rapid re-triggers are throttled.

18. As a job seeker, I want Indeed / Glassdoor **not** listed in the **Source Platform** switcher in v1, so that I cannot accidentally start boards we have not wired yet.

19. As a job seeker (or API client), I want `apify_indeed` or `apify_glassdoor` rejected with a clear unsupported error in v1, so that reserved values do not silently fall back to Bright Data.

20. As a job seeker, I want search API / settings to accept `apify_linkedin` alongside `brightdata_linkedin`, so that the dashboard switcher and backend agree.

21. As a job seeker using CLI search, I want the default platform to remain Bright Data, with Apify LinkedIn documented when wired, so that CLI does not surprise me with a vendor change.

22. As a job seeker, I want Apify LinkedIn scrape to use the existing `APIFY_API_TOKEN`, so that I do not manage a second Apify credential.

23. As a job seeker, I want one Actor run per **Search Region** (or equivalent batched input that preserves per-region limits), so that **Per-Region Limit** still caps each region.

24. As a job seeker, I want free-text **Search Region** labels passed as Actor `location` in v1, so that geography works without a blocking `geoId` table first.

25. As a job seeker, I accept that LinkedIn free-text / optional `geoId` may not match Bright Data geo 1:1, so that MVP is not blocked on perfect geo parity.

26. As a job seeker, I want Task Logs to show that an Apify LinkedIn scrape started and finished (or failed), so that I can audit vendor activity.

27. As a job seeker on an Apify-scraped **Accepted** job with `companyUrl`, I want **Enrich Job** to call **Contact Sample** the same as Bright Data path, so that Enrichment is vendor-agnostic downstream.

28. As a future job seeker, I want **Indeed (Apify)** (`apify_indeed` → `misceres/indeed-scraper`) documented as a reserved Source Platform option, so that a later slice can add it without re-picking the Actor.

29. As a future job seeker, I want **Glassdoor (Apify)** (`apify_glassdoor` → `valig/glassdoor-jobs-scraper`) documented for **job listings**, so that Glassdoor openings can enter **Scraped** later without using the **Company Research** Actor.

30. As a future job seeker on Indeed/Glassdoor cards, I accept that Enrichment Contact Sample may skip when LinkedIn `companyUrl` is absent, so that multi-board scrape does not invent LinkedIn company resolution in this effort.

## Implementation Decisions

### Source Platform (v1 vs reserved)

| Value | Label (UI) | Vendor / Actor | v1 |
| --- | --- | --- | --- |
| `brightdata_linkedin` | LinkedIn (Bright Data) | Bright Data job scraper (existing) | **Ship** (unchanged default) |
| `apify_linkedin` | LinkedIn (Apify) | `curious_coder/linkedin-jobs-scraper` | **Ship** |
| `apify_indeed` | Indeed (Apify) | `misceres/indeed-scraper` | **Reserved — do not add to UI or pipeline** |
| `apify_glassdoor` | Glassdoor (Apify) | `valig/glassdoor-jobs-scraper` | **Reserved — do not add to UI or pipeline** |

Dedicated Actors → separate option values. Do not fake-split a multi-board Actor. Locked in [#199](https://github.com/filmozolevskiy/JustApply/issues/199).

### Apify LinkedIn scrape (v1)

- **Actor:** `curious_coder/linkedin-jobs-scraper` (public guest jobs search — **not** the logged-in “Advanced” sibling).
- **Auth:** existing `APIFY_API_TOKEN` (same as Enrichment / Company Research).
- **Trigger shape:** one Actor run per **Search Region** (or equivalent batched input that preserves per-region limits), with:
  - `keywords` ← search position query
  - `location` ← Search Region display string (free-text LinkedIn resolve)
  - `limitPerSource` ← **Per-Region Limit**
- **Documented geo gap:** Search Regions are admin divisions; LinkedIn free-text / optional `geoId` may not match Bright Data geo 1:1. v1 accepts free-text region labels; optional `geoId` table is later hardening, not blocking MVP.
- **Normalize:** add an Apify LinkedIn → Job normalizer that targets the same fields as the existing Bright Data normalizer. Prefer shared post-normalize filters (company size, Employment Type) already used after Bright Data.

| Job field | Actor field (curious_coder) |
| --- | --- |
| `title` | `title` |
| `company` | `companyName` |
| `companyUrl` | `companyLinkedinUrl` |
| `size` | `companyEmployeesCount` (when available) |
| `link` | `link` |
| `date` | `postedAt` / `postedAtTimestamp` |
| `location` | `location` |
| `employmentType` | `employmentType` |
| `salary` | `salary` / `salaryInfo` |
| `description` | `descriptionText` (or strip `descriptionHtml`) |
| `seniority` | `seniorityLevel` or title heuristics |
| `remoteType` | derive from `workplaceTypes` / location text |
| poster contacts | `jobPosterName` / `jobPosterTitle` / `jobPosterProfileUrl` |

- **Dedup:** existing URL / stable listing-id rules only (no cross-board merge — N/A in v1).
- **Downstream:** unchanged — save **Scraped** → submit **Batch Evaluation Jobs** → **Batch Poller** → **Matched** / attribute gate / Enrichment.
- **Platform plumbing:** today the dashboard and search request already carry `platform`, but the search pipeline always scrapes via the Bright Data LinkedIn path. Wire `platform` through so `apify_linkedin` selects the Apify scrape path.

### Spend Confirmation (v1 LinkedIn Apify)

```text
estimate_usd ≈ Search_Regions × Per-Region_Limit × 0.001
```

($1.00 / 1,000 results PPE; platform usage included in event price per Store pricing at research time.)

- Reuse the shared **Spend Confirmation** modal (ADR 0012).
- Subtitle / line items must say Apify LinkedIn scrape, not Bright Data.
- Bright Data path keeps its existing per-record estimate.
- Keep the PPE rate as a single named constant / config value so Store price updates are one edit.

### Pipeline / API wiring

- Extend `platform` on search endpoints / settings from only `brightdata_linkedin` to also accept `apify_linkedin`.
- Reject `apify_indeed` / `apify_glassdoor` in v1 with a clear unsupported error (400/422) — do not silently no-op into Bright Data.
- Dashboard Source Platform select: add one option for Apify LinkedIn only.
- CLI search: if platform is exposed, default remains Bright Data; document Apify LinkedIn when wired.

### Fail-fast, mocks, rate limit

- Follow ADR 0003 credit-protection patterns for Apify listing runs.
- Mock scraper mode forces mock listings for Apify LinkedIn as for Bright Data.
- Reuse scrape-slot / rate-limit acquisition when the chosen platform will spend real credits.

### Deferred boards (contract only)

| Board | Actor | PPE (research snapshot) | Enrichment note |
| --- | --- | --- | --- |
| Indeed | `misceres/indeed-scraper` | ~$0.005 / job | No LinkedIn `companyUrl` → Contact Sample skip |
| Glassdoor jobs | `valig/glassdoor-jobs-scraper` | ~$0.00036 / job (Bronze) | No LinkedIn `companyUrl` → Contact Sample skip |

**Glassdoor collision:** listing scrape must **not** reuse the **Company Research** Actor (`sian.agency/glassdoor-data-scraper`). Keep Actors separate.

### Relationship to existing ADRs

- Extends hybrid architecture (ADR 0002): Apify gains a **listing** role for LinkedIn; Bright Data remains an option; Enrichment Apify Actors unchanged.
- Spend UX follows ADR 0007 / 0012 (**Spend Confirmation** only when billable).
- Does not change Gemini batch evaluation (ADR 0010 / 0011) or region-scoped search product rules (ADR 0012) beyond provider-specific estimate math.

### Suggested delivery slices

1. Apify LinkedIn client + normalizer + unit tests (mocked Actor dataset fixtures).
2. Pipeline / service / API `platform=apify_linkedin` branch + Spend Confirmation estimate + rate limit / mock.
3. Dashboard Source Platform option + wiring; QA smoke with token.
4. (Later PRD) Indeed + Glassdoor options using reserved values above.

## Testing Decisions

**Good test rule:** Assert external behavior only — platform routing, normalize field mapping, spend estimate math, unsupported-platform rejection, and Source Platform options. Do not assert live Apify HTTP details or Actor internals.

**Primary seam (approved):** Search orchestration (search pipeline / search trigger path) with mocked scrape providers.

Assert:
- `apify_linkedin` → Apify LinkedIn path → jobs land in **Scraped** with the Bright Data–equivalent Job shape
- `brightdata_linkedin` → existing path unchanged
- `apify_indeed` / `apify_glassdoor` → clear unsupported error (no Bright Data fallback)
- `mock_scraper` on Apify LinkedIn → no live Actor call
- Apify spend estimate ≈ regions × limit × `$0.001`

**Thin supporting seams (approved):**

1. Pure Apify LinkedIn normalizer — fixture Actor rows → Job fields (`companyUrl` from `companyLinkedinUrl`, poster contacts). Prior art: Bright Data normalize tests in the scraper test module.
2. Dashboard Source Platform options — Bright Data + Apify LinkedIn only. Prior art: scrape spend confirmation / dashboard static tests.

**Not a seam:** live `curious_coder/linkedin-jobs-scraper` (manual QA with `APIFY_API_TOKEN`).

**Modules under test:** search orchestration / pipeline routing, Apify LinkedIn normalizer, Spend Confirmation estimate for Apify PPE, dashboard Source Platform select.

## Out of Scope

- Implementing Indeed or Glassdoor scrape paths or switcher options in this delivery.
- Removing Bright Data or forcing Apify as the only LinkedIn provider.
- Cross-board job merge / identity resolution.
- Resolving LinkedIn `companyUrl` for Indeed/Glassdoor listings.
- Changing **Company Research** or its `sian.agency` Actor.
- Changing Enrichment Contact Sample Actor (`harvestapi/linkedin-company-employees`).
- Multi-board single Actor (`openclawai/job-board-scraper`) as the v1 design.
- Logged-in / cookie-based LinkedIn Actors.
- Perfect Bright Data ↔ LinkedIn free-text geo parity / `geoId` table (later hardening).
- ADR authorship (optional follow-up after LinkedIn Apify ships).

## Further Notes

- Actor research: `docs/research/apify-linkedin-job-listing-actors.md`, Indeed/Glassdoor siblings under `docs/research/`.
- Map destination for [#194](https://github.com/filmozolevskiy/JustApply/issues/194): Actor picks + PRD — **not** the implementation itself. This issue is the implementation-ready spec from `/to-spec`.
- Pricing figures are Store snapshots from research (2026-08-08); implementation should read current PPE from a single named constant for the LinkedIn Apify estimate.
