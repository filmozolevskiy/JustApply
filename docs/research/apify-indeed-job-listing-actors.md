# Research: Apify Indeed job-listing Actors

**Ticket:** [#196](https://github.com/filmozolevskiy/JustApply/issues/196)  
**Parent map:** [#194](https://github.com/filmozolevskiy/JustApply/issues/194)  
**Date:** 2026-08-08  
**Method:** Apify MCP `search-actors` / `fetch-actor-details` (excludes rental/restricted Actors from search); Store pages + WebFetch for rentals; field compare to `normalize_brightdata_job` in `src/core/scraper.py`. No paid scrapes run.

## Question

Which Apify Store Actors can scrape Indeed job listings on a normal prepaid / Store rental plan, and how do they score against the Actor bar (title / company / location / description; keyword + location search; pricing for Spend Confirmation)?

Also: LinkedIn `companyUrl` presence; Indeed-only vs multi-board (Source Platform split); sample fields vs JustApply normalize contract; volume knobs.

## Verdict (recommended Actor)

**Recommended for an Indeed Source Platform option:** [`misceres/indeed-scraper`](https://apify.com/misceres/indeed-scraper) — *Indeed Scraper*.

| Criterion | Result |
| --- | --- |
| Plan fit | Pay-per-event on normal Store prepaid usage (no enterprise deal, no cookies) |
| Actor bar fields | title (`positionName`), company, location, full description — yes |
| Keyword + location | `position` + `location` + `country`; limit via `maxItemsPerSearch` |
| Spend Confirmation | Deterministic: **$0.005 / job listing** at BRONZE (FREE $0.006 → DIAMOND $0.001) |
| Platform scope | **Indeed-only** → expose a distinct Source Platform value (do not merge with LinkedIn/Glassdoor) |
| LinkedIn `companyUrl` | **Not present** (Indeed company page URLs only) — Enrichment Contact Sample stays on today’s miss path |

**Strong runner-up:** [`borderline/indeed-scraper`](https://apify.com/borderline/indeed-scraper) (same ~$5/1k PPE, richer company payload, higher rating).  
**Budget runner-up:** [`valig/indeed-jobs-scraper`](https://apify.com/valig/indeed-jobs-scraper) (~$0.09–$0.10 / 1k results) or [`kaix/indeed-scraper`](https://apify.com/kaix/indeed-scraper) (~$0.05 / 1k).  
**Multi-board (separate decision):** [`openclawai/job-board-scraper`](https://apify.com/openclawai/job-board-scraper) can scrape Indeed with `sites: ["indeed"]` and tags `site` on each row — only prefer if the map wants one Actor for LinkedIn + Indeed + Glassdoor.

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

Parent map [#194](https://github.com/filmozolevskiy/JustApply/issues/194): Indeed/Glassdoor scrapes are **not** expected to resolve LinkedIn `companyUrl`; missing URL → skip Apify Contact Sample (existing miss path).

---

## Actor bar scorecard

Scoring: **Pass / Partial / Fail** against map must-haves. Prices are Store-published PPE/rental rates (not live run costs).

| Rank | Actor id | Plan | Title/Co/Loc/Desc | Keyword+location | Spend estimate | Indeed-only? | LinkedIn `companyUrl` | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **1** | `misceres/indeed-scraper` | PPE | **Pass** | **Pass** (`position`,`location`,`country`,`maxItemsPerSearch`) | **Pass** $0.005/job BRONZE | Yes | No (Indeed `companyInfo.url` / `companyIndeedUrl`) | Highest adoption; Apify-adjacent maintainer |
| **2** | `borderline/indeed-scraper` | PPE | **Pass** | **Pass** (`query`,`location`,`country`,`maxRows`) | **Pass** $0.005/job | Yes | No (`companyUrl` = Indeed company page; `companyLinks.corporateWebsite` possible) | Strong rating; rental twin exists |
| **3** | `valig/indeed-jobs-scraper` | PPE | **Pass** | **Pass** (`title`,`location`,`country`,`limit`) | **Pass** ~$0.09/1k + start fee | Yes | No (`employer.companyPageUrl` Indeed; `corporateWebsite`) | Cheapest widely used simple API |
| **4** | `kaix/indeed-scraper` | PPE | **Pass** | **Pass** (`keyword`,`location`,`country`,`maxItems`) | **Pass** ~$0.05/1k + tiny start | Yes | No (`company.urls.indeed` / `website`) | Very rich schema; newer vs misceres |
| **5** | `memo23/apify-indeed-cheerio-ppr` | PPE | **Pass** | **Pass** (keyword or URL; `maxJobs`) | Partial ~$1.39/1k BRONZE | Yes | No | Feature-rich; costlier than #1–4 |
| **6** | `openclawai/job-board-scraper` | PPE | **Pass** | **Pass** (`searchTerm`,`location`,`maxResults`,`sites`) | **Pass** $0.005/job + tiny extras | **No** (multi) | LinkedIn rows may have LinkedIn company URL; **Indeed rows do not** | Use only if one multi-board Actor wins the map |
| — | `borderline/indeed-api` | Rental $34.99/mo + usage | Pass (same family) | Pass | Partial (flat rent + CU) | Yes | No | MCP search-actors **excludes** rentals; low usage |
| — | `silentflow/indeed-jobs-scraper` | Rental $18.99/mo + usage | Pass | Pass | Partial | Yes | **Partial** — field `companyLinkedIn` in output schema | Low usage; rental sunset |
| — | `runtime/indeed-job-scraper` | Rental $29/mo | Unknown | Pass inputs | Fail | Yes | Unknown | **Deprecated**; trial 0 minutes |

---

## Ranked candidates (detail)

### 1. `misceres/indeed-scraper` — recommended

- **Store:** https://apify.com/misceres/indeed-scraper  
- **Pricing:** Pay per event — Job listing FREE $0.006 / BRONZE **$0.005** / SILVER $0.004 / GOLD $0.003 / PLATINUM $0.002 / DIAMOND $0.001. Platform usage included in event price.  
- **Stats (MCP, 2026-08-08):** ~28.7k total users, ~2.4k monthly, rating ~3.8/5, 634 bookmarks.  
- **Input knobs:** `position`, `location`, `country` (60+), `maxItemsPerSearch` (volume ↔ Per-Region Limit), optional `startUrls`, `parseCompanyDetails`, `saveOnlyUniqueItems`, `followApplyRedirects`.  
- **Output → normalize map:**

| Normalize field | Actor field(s) |
| --- | --- |
| title | `positionName` |
| company | `company` |
| companyUrl | **gap** — `companyInfo.url` / `companyIndeedUrl` are Indeed pages, not LinkedIn |
| size | `companyInfo.companySize` when `parseCompanyDetails` |
| link | `url` (or `externalApplyLink` if resolved) |
| date | `postedAt` / `postingDateParsed` |
| location | `location` |
| employmentType | `jobType[]` |
| salary | `salary` |
| description | `description` / `descriptionHTML` |

- **Source Platform:** Indeed-only companion scrapers exist for Glassdoor/Upwork (README); do **not** invent a multi-board split from this Actor.

### 2. `borderline/indeed-scraper` — strong runner-up

- **Store:** https://apify.com/borderline/indeed-scraper  
- **Pricing:** PPE **$0.005 / job**.  
- **Stats:** ~20.3k users, ~2.3k monthly, rating ~4.8/5.  
- **Input:** `query`, `location`, `country`, `maxRows`, filters (`remote`, `level` US-only, `jobType`, `fromDays`, `radius`), or `urls` (mutually exclusive with search).  
- **Output highlights:** `title`, `companyName`, `location.formattedAddressShort`, `descriptionText`, `jobUrl`, `datePublished`, `salary.salaryText`, `isRemote`, `jobType`, `companyUrl` (Indeed), `companyNumEmployees`, `companyLinks.corporateWebsite`.  
- **Rental twin:** `borderline/indeed-api` at **$34.99/month + usage** (3-day trial) — same product family; prefer PPR for Spend Confirmation linearity and MCP discoverability.

### 3. `valig/indeed-jobs-scraper` — budget

- **Store:** https://apify.com/valig/indeed-jobs-scraper  
- **Pricing:** PPE result FREE $0.0001 / BRONZE **$0.00009** + Actor Start ~$0.0009/GB. Marketing: ~$0.1 / 1K jobs.  
- **Stats:** ~22.4k users, ~3.4k monthly, rating 5.0/5.  
- **Input:** `title`, `location`, `country`, `limit`, `datePosted`. Minimal — easy Search Regions mapping.  
- **Output:** `title`, `employer.name`, nested `location`, `description.text`, `jobUrl`/`url`, `datePublished`, `baseSalary`, `jobTypes`. No LinkedIn company URL.

### 4. `kaix/indeed-scraper` — budget + rich schema

- **Store:** https://apify.com/kaix/indeed-scraper  
- **Pricing:** PPE jobs ~**$0.00005** (FREE/BRONZE) + negligible start. Claims ~$0.06/1K.  
- **Stats:** ~4k users, ~1.4k monthly, rating ~4.2/5.  
- **Input:** `keyword`, `location`, `country`, `maxItems` (0 = unlimited), `searchMode` basic/detailed/rich, filters.  
- **Output:** `title.text`, `company.name`, `location.formatted`, `description.text`, `urls.indeed`, salary object, remote flags. Company website under `company.urls.website` — still not LinkedIn `/company/`.

### 5. `memo23/apify-indeed-cheerio-ppr`

- **Store:** https://apify.com/memo23/apify-indeed-cheerio-ppr  
- **Pricing:** ~$0.00139 / result BRONZE + $0.007 start/GB.  
- **Hard cap:** `maxJobs` per URL/keyword (default 20000).  
- Good for deep discovery / external apply resolution; overkill and pricier for JustApply scrape bar.  
- Rental sibling: `memo23/apify-indeed-cheerio` ($29/month + usage).

### 6. `openclawai/job-board-scraper` — multi-board

- **Store:** https://apify.com/openclawai/job-board-scraper  
- **Pricing:** **$0.005** per Job Scraped + tiny `result` / start events.  
- **Input:** `searchTerm` / `searchTerms`, `location`, `sites[]` (`indeed`, `linkedin`, `glassdoor`, …), `maxResults` **1–100 per site**, `countryIndeed`, remote/jobType/hoursOld.  
- **Output:** `title`, `company`, `location`, `description`, `job_url`, `site`, `company_url`, `company_url_direct`, salary fields.  
- **Source Platform implication:** Actor *can* separate boards via `sites` + output `site` → legitimate separate switcher options **if this Actor is chosen as the shared backend**. Do not fake splits from Indeed-only Actors.  
- **LinkedIn `companyUrl`:** plausible on LinkedIn-sourced rows (`company_url`); **not expected on Indeed-sourced rows**. Parent map: no LinkedIn-company resolution for Indeed.

### Rental / restricted (MCP search gap)

Apify MCP `search-actors` **excludes rental and restricted Actors**. Store docs confirm three pricing models (PPE, pay-per-usage, rental) and that **rental is sunsetting** (no new rental pricing after 2026-04-01; fully retired 2026-10-01 → migrate to pay-per-usage).

| Actor | Monthly rent | Trial | Notes |
| --- | --- | --- | --- |
| `borderline/indeed-api` | $34.99 | 3 days | PPR twin preferred |
| `silentflow/indeed-jobs-scraper` | $18.99 | 1 day | Optional `companyLinkedIn` enrichment field; ~9 users |
| `runtime/indeed-job-scraper` | $29 | 0 minutes | Deprecated — avoid |
| `memo23/apify-indeed-cheerio` | $29 | (Store) | Prefer PPR sibling |

After trial, rentals require an Apify **paid** plan; rent deducts from prepaid usage **plus** platform CU.

---

## LinkedIn `companyUrl` (enrichment)

| Expectation | Evidence |
| --- | --- |
| Usually **absent** on Indeed scrapers | misceres sample/output schema: Indeed company URLs only; borderline `companyUrl` is Indeed profile; valig/kaix same pattern |
| Exception | `silentflow/indeed-jobs-scraper` output includes `companyLinkedIn` (rental, low adoption — do not depend on it for the map) |
| Multi-board | `openclawai` may return LinkedIn company URLs **only for LinkedIn site rows** |

**Product implication (map):** Indeed Source Platform cards skip Contact Sample Apify path when `companyUrl` empty — already specified in #194.

---

## Source Platform split

| Choice | Implication |
| --- | --- |
| Indeed-only Actor (`misceres` / `borderline` / `valig` / `kaix`) | Add **`apify_indeed`** (name TBD) as its own Source Platform option; do not claim Glassdoor/LinkedIn coverage |
| Multi-board Actor (`openclawai`) | One backend can power `linkedin` / `indeed` / `glassdoor` options if `sites` is constrained and rows filtered by `site` |

Recommend **Indeed-only Actor** for the Indeed research ticket so LinkedIn/Glassdoor research can pick companions independently.

---

## Spend Confirmation formula (recommended Actor)

Using `misceres/indeed-scraper` BRONZE:

```text
estimate_usd ≈ Search_Regions × Per_Region_Limit × 0.005
```

Example: 3 regions × 200 jobs = 600 listings → **$3.00** (plus any Apify plan discount tier if Gold/Platinum).  
Same arithmetic for `borderline/indeed-scraper` at $0.005/job.  
For `valig`: `≈ regions × limit × 0.00009 + (start_fee × GB × runs)`.

Volume knobs map cleanly to **Per-Region Limit**: `maxItemsPerSearch` / `maxRows` / `limit` / `maxItems`.

---

## Field-gap summary vs `normalize_brightdata_job`

| Field | misceres | borderline | Notes |
| --- | --- | --- | --- |
| title | rename `positionName` | `title` | Adapter needed for misceres |
| company | `company` | `companyName` | Adapter for borderline |
| companyUrl (LinkedIn) | **missing** | **missing** | Expected |
| link | `url` | `jobUrl` | |
| description | `description` | `descriptionText` | |
| location | `location` | nested `location.*` | Flatten |
| date | `postedAt` | `datePublished` | |
| salary | `salary` | `salary.salaryText` | |
| employmentType | `jobType[]` | `jobType[]` | Join/pick first |
| size | optional company scrape | `companyNumEmployees` | |
| seniority / remoteType | derive | `isRemote` + derive | Same as Bright Data path |
| job_poster / contacts | none | none | Indeed-typical |

---

## Recommendation for parent map #194

1. **Pick `misceres/indeed-scraper`** as the Indeed job-listing Actor for the PRD.  
2. Expose a **separate Source Platform** for Indeed (not a fake mode of a LinkedIn Actor).  
3. Wire Spend Confirmation to **$0.005 × expected listings** (tier-aware if needed).  
4. Document LinkedIn `companyUrl` as **out of scope** for Indeed cards.  
5. Keep Bright Data LinkedIn path; treat Apify Indeed as additive.  
6. Revisit `openclawai/job-board-scraper` only if LinkedIn + Glassdoor research also lands on that multi-board Actor.

---

## Citations (primary sources)

1. Apify MCP `search-actors` keywords `Indeed` / `Indeed jobs` — public PPE Actors listed above (2026-08-08). Tool note: *search excludes rental and restricted Actors*.  
2. Apify MCP `fetch-actor-details` for: `misceres/indeed-scraper`, `borderline/indeed-scraper`, `valig/indeed-jobs-scraper`, `kaix/indeed-scraper`, `memo23/apify-indeed-cheerio-ppr`, `openclawai/job-board-scraper`, `borderline/indeed-api`, `silentflow/indeed-jobs-scraper`, `runtime/indeed-job-scraper` — pricing, input schemas, output schemas, stats.  
3. Store markdown: https://apify.com/misceres/indeed-scraper.md — sample output fields, PPE pricing copy.  
4. Apify docs — Actors in Store pricing models + rental sunset: https://docs.apify.com/platform/actors/running/actors-in-store  
5. Apify docs — rental model / MCP exclusion: https://docs.apify.com/actors/publishing/monetize/rental  
6. Store pages (rental discovery): https://apify.com/borderline/indeed-api , https://apify.com/silentflow/indeed-jobs-scraper , https://apify.com/runtime/indeed-job-scraper , https://apify.com/memo23/apify-indeed-cheerio  
7. JustApply code: `src/core/scraper.py` `normalize_brightdata_job` (lines ~122–191).  
8. Parent map requirements: https://github.com/filmozolevskiy/JustApply/issues/194  
9. This ticket: https://github.com/filmozolevskiy/JustApply/issues/196  
