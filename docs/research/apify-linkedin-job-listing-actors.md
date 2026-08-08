# Research: Apify LinkedIn job-listing Actors

**Ticket:** [#195](https://github.com/filmozolevskiy/JustApply/issues/195)  
**Parent map:** [#194](https://github.com/filmozolevskiy/JustApply/issues/194)  
**Date:** 2026-08-08  
**Method:** Apify MCP `search-actors` / `fetch-actor-details` (excludes rental/restricted Actors from search); Store pages + WebFetch for rentals and additional PPE Actors; field compare to `normalize_brightdata_job` in `src/core/scraper.py`. No paid scrapes run.

## Question

Which Apify Store Actors can scrape **LinkedIn job listings** (keyword + location) on a normal prepaid / Store rental plan — no enterprise LinkedIn deal, no personal LinkedIn cookies — and how do they score against the Actor bar?

### Actor bar (must-haves)

1. Normal Apify prepaid / Store rental (no enterprise LinkedIn deal, no personal cookies)
2. Returns title, company, location, description (enough for **Resume Matcher**)
3. Returns or can build LinkedIn `companyUrl` for **Contact Sample** Enrichment
4. Keyword + location search mappable to **Search Regions** + **Per-Region Limit** (or document the gap)

Also capture: pricing (CU / rental / per-result); Indeed/Glassdoor coverage; sample fields vs Bright Data normalize; reliability signals.

## Verdict (recommended Actor)

**Recommended primary LinkedIn Actor:** [`curious_coder/linkedin-jobs-scraper`](https://apify.com/curious_coder/linkedin-jobs-scraper) — *Linkedin Jobs Scraper*.

| Criterion | Result |
| --- | --- |
| Plan fit | Pay-per-event on normal Store prepaid usage; scrapes **public** LinkedIn jobs search (incognito / guest). No login, no cookies. Related “Advanced” Actor (logged-in) is a different product — do not use it. |
| Actor bar fields | title, companyName, location, descriptionText/descriptionHtml — **Pass** |
| LinkedIn `companyUrl` | **`companyLinkedinUrl`** — direct map to JustApply `companyUrl` for Contact Sample |
| Keyword + location | `keywords` + `location` (or search `urls`); volume via `limitPerSource` ↔ **Per-Region Limit** |
| Spend Confirmation | Deterministic: **$1.00 / 1,000 results** ($0.001 / result) — PPE, platform usage included in event price |
| Platform scope | **LinkedIn-only** (Indeed is a separate Actor from same author) |
| Reliability | Highest Store adoption in this niche (~123k total / ~9.3k monthly users, 4.36★, ~99.7% success, last modified 2026-08-08) |

**Strong runner-up (cheaper, multi-location native):** [`cheap_scraper/linkedin-job-scraper`](https://apify.com/cheap_scraper/linkedin-job-scraper) — ~$0.60/1k BRONZE, `keyword[]` × `locations[]`, `companyUrl`, highest monthly users (~11k).  
**Budget runner-up:** [`valig/linkedin-jobs-scraper`](https://apify.com/valig/linkedin-jobs-scraper) — ~$0.36/1k BRONZE, simple `title` + `location` + `limit`.  
**Avoid for primary:** low-adoption PPE Actors (`blackfalcondata`, `sourabhbgp`) and near-dead rentals (`minyo`); rental model is sunsetting in 2026.

---

## JustApply normalize contract (comparison baseline)

`normalize_brightdata_job` (`src/core/scraper.py` ~122–191) maps scrape rows into:

| Normalize output | Common input aliases |
| --- | --- |
| `title` | `job_title`, `title` |
| `company` | `company_name`, `company` |
| `companyUrl` | `company_url`, `companyUrl` (LinkedIn `/company/` URL for Contact Sample) |
| `size` | `company_size`, `size` |
| `link` | `url`, `apply_link`, `link` |
| `date` | `date_posted`, `date` |
| `location` | `job_location`, `location` |
| `remoteType` | derived from `is_remote` / location text |
| `seniority` | derived from title / `job_seniority_level` |
| `employmentType` | `job_employment_type`, `employmentType` |
| `salary` | `salary`, `salary_formatted` |
| `description` | `job_summary`, `description` |
| `contacts` | from `job_poster` only |

Parent map [#194](https://github.com/filmozolevskiy/JustApply/issues/194): LinkedIn scrapes **should** supply LinkedIn `companyUrl` so Enrichment Contact Sample can run.

**Search Regions / Per-Region Limit** (`CONTEXT.md`): each selected Search Region is scraped independently for up to Per-Region Limit postings (25–1000, default 200). Spend ceiling ≈ Regions × Limit × per-record cost.

---

## Actor bar scorecard

Scoring: **Pass / Partial / Fail**. Prices are Store-published PPE/rental rates (not live run costs). Stats from MCP/Store pages on 2026-08-08.

| Rank | Actor id | Plan | Cookies? | Title/Co/Loc/Desc | LinkedIn `companyUrl` | Keyword+location / regions | Spend estimate | LI-only? | Reliability |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **1** | `curious_coder/linkedin-jobs-scraper` | PPE $1/1k | No (public guest) | **Pass** | **Pass** (`companyLinkedinUrl`) | **Pass** (`keywords`+`location` or `urls`; `limitPerSource`) | **Pass** $0.001/result | Yes | ~123k users, ~9.3k mo, 4.36★ |
| **2** | `cheap_scraper/linkedin-job-scraper` | PPE ~$0.60/1k BRONZE + $0.005 start/GB | No (public) | **Pass** | **Pass** (`companyUrl`) | **Pass** (`keyword[]`×`locations[]`; `maxItems`) | **Pass** | Yes (Indeed/GD companions) | ~44k users, ~11k mo, 4.58★ |
| **3** | `valig/linkedin-jobs-scraper` | PPE ~$0.36/1k BRONZE + start | No | **Pass** | **Pass** (`companyUrl`) | **Pass** (`title`+`location`+`limit`) | **Pass** | Yes | ~16k users, ~4.2k mo, ~4.3★ |
| **4** | `worldunboxer/rapid-linkedin-scraper` | PPE ~$0.48/1k BRONZE + $0.008 start/GB | No (README) | **Pass** | **Pass** (`company_url`) | **Pass** (titles + location/cities; `jobs_entries`) | **Pass** | Yes (Indeed companion) | ~15k users, ~1.1k mo, 3.82★ |
| **5** | `blackfalcondata/linkedin-job-scraper` | PPE $0.27/1k + tiny start | No (README) | **Pass** (need `enrichDetails`) | **Pass** (`companyLinkedIn` / company page) | **Pass** (`keywords`+`location`; `regions`/`geoIds`; `maxResults`) | **Pass** | Yes | **Low** (~106 users, ~13 mo) |
| **6** | `sourabhbgp/linkedin-jobs-scraper` | PPE $0.50/1k (+ start fee from 2026-07-28) | No (README) | **Partial** without `enrichDetails` | **Pass** (`companyUrl`) | **Pass** (`keywords`+`location`+`maxResults`) | **Pass** | Yes | **Low** (~166 users, 3.0★) |
| — | `minyo/linkedin-jobs-scraper` | Rental **$20/mo** + usage (claims ~$2/1k) | No | **Pass** | **Pass** (`company_url`) | **Pass** (`search_term`+`location`+`results_wanted`) | Partial (flat rent) | Yes | **Fail** (~28 users, **0** monthly) |
| — | `scraperx/linkedin-jobs-scraper` | Was rental ~$19.99/mo (earlier Store index) | Unknown | — | — | — | — | — | **Unavailable** (Store URL 404 at research time) |
| — | `fantastic-jobs/advanced-linkedin-job-search-api` | PPE ~$0.005/job | N/A (DB API) | Likely Pass | Unknown without detail fetch | Filter API, not classic scrape | Higher unit cost | Yes | Solid usage (~3.5k mo) but different product model — out of scope for Bright Data–shaped scrape |

**MCP limitation:** `search-actors` excludes rental and restricted Actors. Rentals found via Store/WebSearch; Apify docs: rental model sunsetting (no new rental pricing after 2026-04-01; fully retired 2026-10-01 → pay-per-usage).

---

## Ranked candidates (detail)

### 1. `curious_coder/linkedin-jobs-scraper` — recommended

- **Store:** https://apify.com/curious_coder/linkedin-jobs-scraper  
- **Pricing:** Pay per event — **$1.00 / 1,000 results** ($0.001 / result). Platform usage included in event price ([pricing page](https://apify.com/curious_coder/linkedin-jobs-scraper/pricing)).  
- **Stats (MCP + Store, 2026-08-08):** ~123k total users, ~9.3k monthly, 4.36/5, ~1,186 bookmarks, ~99.7% runs succeeded; last modified 2026-08-08.  
- **Cookies / access:** Input schema documents scraping the **public** LinkedIn jobs search page (incognito). For logged-in account scraping it points to a different Actor (`curious_coder/linkedin-jobs-search-scraper`) — **out of Actor-bar scope**.  
- **Input knobs:** `keywords`, `location`, optional `geoId` / `distance` / `datePosted` / `companyIds`; or `urls[]` of public search URLs; `limitPerSource` (max jobs per search); optional `scrapeCompany`; optional `splitByLocation` + `splitCountry` to bypass ~1000/search cap.  
- **Search Regions mapping:** One Actor call per Search Region with `location` = region label (or a region-built search URL) and `limitPerSource` = Per-Region Limit. Free-text location is LinkedIn-resolved — **gap:** JustApply regions are admin divisions (US states, etc.); LinkedIn may resolve slightly differently than Bright Data geo unless `geoId` is curated.  
- **Output → normalize map:**

| Normalize field | Actor field(s) |
| --- | --- |
| title | `title` |
| company | `companyName` |
| companyUrl | `companyLinkedinUrl` |
| size | `companyEmployeesCount` (with `scrapeCompany`) |
| link | `link` |
| date | `postedAt` / `postedAtTimestamp` |
| location | `location` |
| employmentType | `employmentType` |
| salary | `salary` / `salaryInfo` |
| description | `descriptionText` (or strip `descriptionHtml`) |
| seniority | `seniorityLevel` (or derive) |
| remoteType | derive from `workplaceTypes` / location |
| contacts | `jobPosterName` / `jobPosterTitle` / `jobPosterProfileUrl` → map like Bright Data `job_poster` |

- **Indeed/Glassdoor:** LinkedIn-only. Author links a separate [Indeed scraper](https://apify.com/curious_coder/indeed-scraper).

### 2. `cheap_scraper/linkedin-job-scraper` — strong runner-up

- **Store:** https://apify.com/cheap_scraper/linkedin-job-scraper  
- **Pricing:** PPE result FREE $0.0007 / BRONZE **$0.0006** / SILVER $0.0005 / GOLD+ $0.00035 + Actor Start **$0.005**/GB. Marketing ~$0.60/1k at BRONZE.  
- **Stats:** ~44k users, ~11k monthly, 4.58/5, 200 bookmarks; last modified 2026-08-08.  
- **Input:** `keyword[]` + `locations[]` (cartesian pairs) **or** `startUrls`; `maxItems`; rich filters; `enrichCompanyData` (default off). README notes public API ~1000/search practical ~500.  
- **Output:** `jobTitle`, `companyName`, `companyUrl`, `companyId`, `location`, `jobDescription`, `jobUrl`, `publishedAt`, `contractType`, `experienceLevel`, `workType`, poster fields.  
- **Search Regions:** Excellent — pass all selected regions as `locations[]` and set `maxItems` ≈ Regions × Per-Region Limit (or one run per region for cleaner ceilings).  
- **Companions:** README links Indeed + Glassdoor Actors from same author — useful for Source Platform split, still **not** multi-board in one Actor.

### 3. `valig/linkedin-jobs-scraper` — budget

- **Store:** https://apify.com/valig/linkedin-jobs-scraper  
- **Pricing:** result FREE $0.0004 / BRONZE **$0.00036** + Actor Start ~$0.0009/GB. Marketing $0.4/1K.  
- **Stats:** ~16k users, ~4.2k monthly, ~4.3/5.  
- **Input:** `title`, `location`, `limit` (default 100), filters. Clean 1:1 with Search Regions.  
- **Output:** `title`, `companyName`, `companyUrl`, `location`, `description`, `url`, `postedDate`, `contractType`, `experienceLevel`, `workType`, recruiter fields.

### 4. `worldunboxer/rapid-linkedin-scraper`

- **Store:** https://apify.com/worldunboxer/rapid-linkedin-scraper  
- **Pricing:** Result FREE $0.0005 / BRONZE **$0.00048** + Actor Start $0.008/GB. Marketing $0.45/1K. Explicit **no cookies**.  
- **Stats:** ~15k users, ~1.1k monthly, 3.82/5 — weaker rating / lower monthly than #1–3.  
- **Input:** `jobs_titles[]`, `location`, optional `cities[]`, `jobs_entries`.  
- **Output:** `job_title`, `company_name`, `company_url`, `location`, `job_description`, `job_url`, etc.  
- **Indeed:** Separate Rapid Indeed Scraper (not this Actor).

### 5. `blackfalcondata/linkedin-job-scraper` — cheap but thin adoption

- **Store:** https://apify.com/blackfalcondata/linkedin-job-scraper  
- **Pricing:** $0.00027 / result ($0.27/1k) + $0.0005 start/GB. No cookies.  
- **Stats:** ~106 users, ~13 monthly — **reliability risk** despite 5.0★ on tiny sample.  
- **Input:** rich `keywords`/`location`/`regions`/`geoIds`/`maxResults`; `enrichDetails` / `scrapeCompany` for full description + employer.  
- **Interesting for JustApply:** `regions` ISO-2 + presets — still not identical to Search Region (state/province) model; would need region→location string mapping anyway.

### 6. `sourabhbgp/linkedin-jobs-scraper`

- **Store:** https://apify.com/sourabhbgp/linkedin-jobs-scraper  
- **Pricing:** $0.50/1k + $0.002 start (from 2026-07-28). No cookies.  
- **Caveat:** Search mode without `enrichDetails` returns title/company/location but **not** full description — must set `enrichDetails: true` for Resume Matcher. Low adoption / 3.0★.

### Rental / unavailable

| Actor | Monthly rent | Notes |
| --- | --- | --- |
| `minyo/linkedin-jobs-scraper` | $20 + usage | Zero monthly users; rental sunset; skip |
| `scraperx/linkedin-jobs-scraper` | Was ~$19.99/mo | Store page **404** at research time — do not recommend |

---

## Search Regions + Per-Region Limit mapping

| JustApply concept | Recommended wiring (`curious_coder`) | Alternative (`cheap_scraper`) |
| --- | --- | --- |
| Search Region | One run (or one `urls` entry) with `location` = region display name | One `locations[]` entry per region |
| Per-Region Limit | `limitPerSource` | Cap via `maxItems` / per-pair logic |
| Position keyword | `keywords` | `keyword[]` |
| Spend ceiling | Regions × Limit × **$0.001** | Regions × Limit × **~$0.0006** (+ start fees) |

**Documented gap:** Search Regions are country-scoped admin divisions (`CONTEXT.md`). Actors take free-text LinkedIn locations (or geoIds). Expect occasional geo mismatch vs Bright Data unless JustApply maintains LinkedIn `geoId` per region. Multi-region in **one** Actor run (cheap_scraper cartesian) complicates per-region spend attribution vs one-run-per-region.

---

## Spend Confirmation formula (recommended Actor)

Using `curious_coder/linkedin-jobs-scraper`:

```text
estimate_usd ≈ Search_Regions × Per_Region_Limit × 0.001
```

Example: 3 regions × 200 jobs = 600 listings → **$0.60**.

Runner-up BRONZE (`cheap_scraper`):

```text
estimate_usd ≈ Search_Regions × Per_Region_Limit × 0.0006 + (0.005 × memory_GB × runs)
```

---

## Field-gap summary vs `normalize_brightdata_job`

| Field | curious_coder | cheap_scraper | Notes |
| --- | --- | --- | --- |
| title | `title` | `jobTitle` | Adapter rename for cheap_scraper |
| company | `companyName` | `companyName` | Adapter (Bright Data uses `company_name`) |
| companyUrl | `companyLinkedinUrl` | `companyUrl` | Both LinkedIn company pages |
| link | `link` | `jobUrl` | |
| description | `descriptionText` | `jobDescription` | |
| location | `location` | `location` | |
| date | `postedAt` | `publishedAt` / `postedTime` | |
| salary | `salary` / `salaryInfo` | `salaryInfo` | |
| employmentType | `employmentType` | `contractType` | |
| size | `companyEmployeesCount` | `companyEmployeeCount` / range | Optional enrich |
| seniority | `seniorityLevel` | `experienceLevel` | Or derive |
| remoteType | `workplaceTypes` | `workType` | Normalize to remote/hybrid/in_office |
| contacts | jobPoster* fields | poster* fields | Map to contacts[] |

Adapter layer required for all Apify Actors (field names ≠ Bright Data). No Actor matches Bright Data field names 1:1.

---

## Indeed / Glassdoor coverage

None of the ranked LinkedIn Actors scrape Indeed or Glassdoor in the **same** Actor. Companions:

| LinkedIn Actor | Same-author / related boards |
| --- | --- |
| curious_coder | Separate Indeed scraper |
| cheap_scraper | Indeed + Glassdoor companion Actors (README) |
| worldunboxer | Rapid Indeed Scraper |
| Others | LinkedIn-only |

**Product implication:** Keep LinkedIn as its own Source Platform option; Indeed/Glassdoor stay separate research tickets (#196 / Glassdoor).

---

## Recommendation for parent map #194

1. **Pick `curious_coder/linkedin-jobs-scraper`** as the primary Apify LinkedIn job-listing Actor for the PRD.  
2. Wire Spend Confirmation to **$0.001 × expected listings** (Regions × Per-Region Limit).  
3. Map `companyLinkedinUrl` → `companyUrl` so Contact Sample Enrichment works.  
4. Prefer **one Actor run per Search Region** with `limitPerSource` = Per-Region Limit; optional later: geoId table.  
5. Keep Bright Data LinkedIn path until PRD decides replace vs dual-source.  
6. Hold `cheap_scraper/linkedin-job-scraper` as cost-optimized alternative if monthly volume makes $1/1k painful.  
7. Do **not** depend on rental Actors (sunset) or cookie/logged-in “Advanced” scrapers.

---

## Citations (primary sources)

1. Apify MCP `search-actors` keywords `LinkedIn jobs` — public PPE Actors listed above (2026-08-08). Tool note: *search excludes rental and restricted Actors*.  
2. Apify MCP `fetch-actor-details` for: `curious_coder/linkedin-jobs-scraper`, `cheap_scraper/linkedin-job-scraper`, `valig/linkedin-jobs-scraper`, `worldunboxer/rapid-linkedin-scraper`, `blackfalcondata/linkedin-job-scraper` — pricing, input schemas, output schemas, stats, README summaries.  
3. Store markdown / pricing: https://apify.com/curious_coder/linkedin-jobs-scraper/pricing — $1/1k PPE; public guest scrape docs; field table; sample JSON with `companyLinkedinUrl`.  
4. Store: https://apify.com/cheap_scraper/linkedin-job-scraper — PPE tiers, companion Indeed/Glassdoor links, input/output.  
5. Store: https://apify.com/valig/linkedin-jobs-scraper , https://apify.com/worldunboxer/rapid-linkedin-scraper , https://apify.com/blackfalcondata/linkedin-job-scraper , https://apify.com/sourabhbgp/linkedin-jobs-scraper — PPE / no-cookie claims, fields.  
6. Store (rental): https://apify.com/minyo/linkedin-jobs-scraper — $20/mo + usage; 0 monthly users; sample `company_url`.  
7. Apify docs — Actors in Store pricing models + rental sunset: https://docs.apify.com/platform/actors/running/actors-in-store  
8. JustApply code: `src/core/scraper.py` `normalize_brightdata_job` (lines ~122–191).  
9. Domain terms: `CONTEXT.md` — Search Region, Per-Region Limit, Spend Confirmation.  
10. Parent map: https://github.com/filmozolevskiy/JustApply/issues/194  
11. This ticket: https://github.com/filmozolevskiy/JustApply/issues/195  
