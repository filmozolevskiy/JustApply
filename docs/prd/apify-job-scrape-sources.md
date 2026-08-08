# [PRD] Apify Job-Scrape Sources (LinkedIn first)

> **GitHub Issue:** [#198](https://github.com/filmozolevskiy/JustApply/issues/198)  
> **Wayfinder map:** [#194](https://github.com/filmozolevskiy/JustApply/issues/194)  
> **Actor pick:** [#199](https://github.com/filmozolevskiy/JustApply/issues/199)

## Problem Statement

Job listing scrape today is **Bright Data–only** (`brightdata_linkedin` on the **Source Platform** switcher). The product already pays for **Apify** for **Enrichment** (**Contact Sample**) and **Company Research**, so LinkedIn listing scrape cannot share that bill. We also want a path to Indeed and Glassdoor listings later, without inventing a second vendor stack.

Research and grilling locked dedicated Apify Actors per board and switcher values. This PRD specifies how to plug Apify into the existing **Search & Evaluation Pipeline** scrape path — **v1 builds LinkedIn (Apify) only**. Indeed and Glassdoor are named and contracted here so a later PRD/slice can add them without re-deciding Actors.

## Solution

Add **`apify_linkedin`** to the **Source Platform** switcher beside **`brightdata_linkedin`**. When selected, the scrape phase calls [`curious_coder/linkedin-jobs-scraper`](https://apify.com/curious_coder/linkedin-jobs-scraper) (public guest LinkedIn jobs search, no cookies), normalizes rows into the same Job shape as Bright Data (`normalize_brightdata_job` contract), dedupes, saves into **Scraped**, then continues batch evaluation unchanged.

**Spend Confirmation** estimates Apify PPE for that Actor (`Search Regions × Per-Region Limit × $0.001`). Bright Data remains available and is not removed.

Indeed (`misceres/indeed-scraper`) and Glassdoor (`valig/glassdoor-jobs-scraper`) are **documented for a follow-on** — option values and Actors are reserved; **v1 must not expose or wire them**.

## User Stories

### v1 — LinkedIn (Apify)

1. As a job seeker, I want a **Source Platform** option **LinkedIn (Apify)** next to **LinkedIn (Bright Data)**, so that I can scrape listings on the Apify bill I already pay.

2. As a job seeker, I want choosing **LinkedIn (Apify)** to run the same **Search Regions**, **Per-Region Limit**, query, and refine preferences as today, so that I do not learn a second search UX.

3. As a job seeker, I want **Spend Confirmation** before an Apify LinkedIn scrape to show volume ceiling and estimated USD from that Actor’s PPE rate, so that I am not shown a fake Bright Data $/record number.

4. As a job seeker, I want Apify LinkedIn listings to land in **Scraped** like Bright Data listings, so that **Batch Evaluation** and the Kanban lanes work unchanged.

5. As a job seeker, I want Apify LinkedIn rows to carry LinkedIn **`companyUrl`** when the Actor returns `companyLinkedinUrl`, so that **Enrichment** / **Contact Sample** still works on Accepted cards.

6. As a job seeker, I want Apify LinkedIn rows missing `companyUrl` to still save and evaluate, with Enrichment skipping Apify contact fetch (today’s miss path), so that scrape success is not blocked on Enrichment.

7. As a job seeker, I want job-poster fields from the Actor mapped into preliminary contacts when present (same idea as Bright Data `job_poster`), so that Poster badges still appear when available.

8. As a job seeker, I want mock scrape mode to cover the Apify LinkedIn path (no live Actor call), so that local/dev and CI stay free.

9. As a job seeker, I want fail-fast behavior and scrape rate limiting to apply to Apify LinkedIn scrapes like Bright Data, so that runaway loops cannot burn credits.

10. As a job seeker, I want Indeed / Glassdoor **not** listed in the Source Platform switcher in v1, so that I cannot accidentally start boards we have not wired yet.

### Deferred (document only — not v1)

11. As a future job seeker, I want **Indeed (Apify)** (`apify_indeed` → `misceres/indeed-scraper`) as a Source Platform option, so that I can scrape Indeed on the same Apify subscription.

12. As a future job seeker, I want **Glassdoor (Apify)** (`apify_glassdoor` → `valig/glassdoor-jobs-scraper`) as a Source Platform option for **job listings**, so that Glassdoor openings enter **Scraped** without using the **Company Research** Actor.

13. As a future job seeker on Indeed/Glassdoor cards, I accept that Enrichment Contact Sample may skip when LinkedIn `companyUrl` is absent, so that multi-board scrape does not invent LinkedIn company resolution in this effort.

## Implementation Decisions

### Source Platform (v1 vs reserved)

| Value | Label (UI) | Vendor / Actor | v1 |
| --- | --- | --- | --- |
| `brightdata_linkedin` | LinkedIn (Bright Data) | Bright Data job scraper (existing) | **Ship** (unchanged default) |
| `apify_linkedin` | LinkedIn (Apify) | `curious_coder/linkedin-jobs-scraper` | **Ship** |
| `apify_indeed` | Indeed (Apify) | `misceres/indeed-scraper` | **Reserved — do not add to UI or pipeline** |
| `apify_glassdoor` | Glassdoor (Apify) | `valig/glassdoor-jobs-scraper` | **Reserved — do not add to UI or pipeline** |

Locked in [Grill: Pick Apify scrape Actors and Source Platform split](https://github.com/filmozolevskiy/JustApply/issues/199). Dedicated Actors → separate option values; do not fake-split a multi-board Actor.

### Apify LinkedIn scrape (v1)

- **Actor:** `curious_coder/linkedin-jobs-scraper` (public guest jobs search — **not** the logged-in “Advanced” sibling).
- **Auth:** existing `APIFY_API_TOKEN` (same as Enrichment / Company Research).
- **Trigger shape:** one Actor run per **Search Region** (or equivalent batched input that preserves per-region limits), with:
  - `keywords` ← search position query
  - `location` ← Search Region display string (free-text LinkedIn resolve)
  - `limitPerSource` ← **Per-Region Limit**
- **Documented geo gap:** Search Regions are admin divisions; LinkedIn free-text / optional `geoId` may not match Bright Data geo 1:1. v1 accepts free-text region labels; optional `geoId` table is a later hardening, not blocking MVP.
- **Normalize:** add an Apify LinkedIn → Job normalizer that targets the same fields as `normalize_brightdata_job` (`src/core/scraper.py`). Prefer shared post-normalize filters (company size, Employment Type) already used after Bright Data.

| Job field | Actor field (curious_coder) |
| --- | --- |
| `title` | `title` |
| `company` | `companyName` |
| `companyUrl` | `companyLinkedinUrl` |
| `size` | `companyEmployeesCount` (when company scrape enabled / available) |
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

### Spend Confirmation (v1 LinkedIn Apify)

```text
estimate_usd ≈ Search_Regions × Per-Region_Limit × 0.001
```

($1.00 / 1,000 results PPE; platform usage included in event price per Store pricing at research time.)

- Reuse the shared **Spend Confirmation** modal (ADR 0012).
- Subtitle / line items must say Apify LinkedIn scrape, not Bright Data.
- Bright Data path keeps its existing per-record estimate.

### Pipeline / API wiring

- Extend `platform` on search endpoints / settings from only `brightdata_linkedin` to also accept `apify_linkedin`.
- Reject or ignore `apify_indeed` / `apify_glassdoor` in v1 if somehow sent (404/400 or treat as unsupported) — do not silently no-op into Bright Data.
- Dashboard `<select id="kb-filter-platform">`: add one option for Apify LinkedIn only.
- CLI search: if platform is exposed, default remains Bright Data; document Apify LinkedIn when wired.

### Fail-fast, mocks, rate limit

- Follow ADR 0003 credit-protection patterns for Apify listing runs.
- `MOCK_SCRAPER` / `mock_scraper` forces mock listings for Apify LinkedIn as for Bright Data.
- Reuse scrape-slot / rate-limit acquisition when the chosen platform will spend real credits.

### Deferred boards (contract only)

Research notes (do not implement in this PRD’s delivery slices):

| Board | Actor | PPE (research snapshot) | Enrichment note | Research |
| --- | --- | --- | --- | --- |
| Indeed | `misceres/indeed-scraper` | ~$0.005 / job | No LinkedIn `companyUrl` → Contact Sample skip | [docs/research/apify-indeed-job-listing-actors.md](../research/apify-indeed-job-listing-actors.md) / [#196](https://github.com/filmozolevskiy/JustApply/issues/196) |
| Glassdoor jobs | `valig/glassdoor-jobs-scraper` | ~$0.00036 / job (Bronze) | No LinkedIn `companyUrl` → Contact Sample skip | [docs/research/apify-glassdoor-job-listing-actors.md](../research/apify-glassdoor-job-listing-actors.md) / [#197](https://github.com/filmozolevskiy/JustApply/issues/197) |

**Glassdoor collision:** listing scrape must **not** reuse `sian.agency/glassdoor-data-scraper` (**Company Research**). Keep Actors separate.

A follow-on PRD/issues may add switcher options + normalizers for Indeed/Glassdoor without re-picking Actors.

### Relationship to existing ADRs

- Extends hybrid architecture (ADR 0002): Apify gains a **listing** role for LinkedIn; Bright Data remains an option; Enrichment Apify Actors unchanged.
- Spend UX follows ADR 0007 / 0012 (**Spend Confirmation** only when billable).
- Does not change Gemini batch evaluation (ADR 0010 / 0011) or region-scoped search product rules (ADR 0012) beyond provider-specific estimate math.

### Suggested delivery slices (implementation — after this PRD)

1. Apify LinkedIn client + normalizer + unit tests (mocked Actor dataset fixtures).
2. Pipeline / service / API `platform=apify_linkedin` branch + Spend Confirmation estimate + rate limit / mock.
3. Dashboard Source Platform option + wiring; QA smoke with token.
4. (Later PRD) Indeed + Glassdoor options using reserved values above.

## Testing Decisions

**Good test rule:** Assert platform routing, normalize field mapping, spend estimate math, and “unsupported platform” rejection — not live Apify HTTP details.

**Preferred seams:**

1. Normalizer pure function — fixture rows from Store/output schema → Job dict matching Bright Data normalize contract (`companyUrl` from `companyLinkedinUrl`).
2. Spend estimate helper — regions × limit × 0.001.
3. Search orchestration with mocked Apify runner — `apify_linkedin` calls Apify path; `brightdata_linkedin` unchanged; `apify_indeed` / `apify_glassdoor` rejected in v1.
4. Dashboard/static — Source Platform options include Bright Data + Apify LinkedIn only.

**Not tested at browser level:** Live `curious_coder/linkedin-jobs-scraper` (manual smoke with `APIFY_API_TOKEN`).

## QA Validation

- [ ] Source Platform shows **LinkedIn (Bright Data)** and **LinkedIn (Apify)** only — no Indeed/Glassdoor options.
- [ ] Select Apify LinkedIn → set regions + limit → Spend Confirmation shows Apify estimate ≈ regions × limit × $0.001 → Proceed → jobs appear in **Scraped** → evaluation proceeds as today.
- [ ] Open an Apify-scraped **Accepted** job with `companyUrl` → **Enrich Job** can call Contact Sample (same as Bright Data path).
- [ ] Mock scraper + Apify LinkedIn → no live Apify listing call; listings still evaluate under mock_eval rules.
- [ ] Bright Data path still works with prior estimate math.
- [ ] API/platform `apify_indeed` or `apify_glassdoor` in v1 → clear unsupported error (not a Bright Data fallback).

## Out of Scope

- Implementing Indeed or Glassdoor scrape paths or switcher options in this delivery.
- Removing Bright Data or forcing Apify as the only LinkedIn provider.
- Cross-board job merge / identity resolution.
- Resolving LinkedIn `companyUrl` for Indeed/Glassdoor listings.
- Changing **Company Research** or its `sian.agency` Actor.
- Changing Enrichment Contact Sample Actor (`harvestapi/linkedin-company-employees`).
- Multi-board single Actor (`openclawai/job-board-scraper`) as the v1 design.
- Logged-in / cookie-based LinkedIn Actors.
- ADR authorship (optional follow-up after LinkedIn Apify ships).

## Further Notes

- Actor research: [docs/research/apify-linkedin-job-listing-actors.md](../research/apify-linkedin-job-listing-actors.md), Indeed/Glassdoor siblings under `docs/research/`.
- Map destination for [#194](https://github.com/filmozolevskiy/JustApply/issues/194): Actor picks + this PRD — **not** the implementation itself.
- Pricing figures are Store snapshots from research (2026-08-08); implementation should read current PPE from config/constants with a single named constant for the LinkedIn Apify estimate.
