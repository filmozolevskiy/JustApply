# Research: Apify Glassdoor job-listing Actors

**Ticket:** [Research: Apify Glassdoor job-listing Actors](https://github.com/filmozolevskiy/JustApply/issues/197)  
**Map:** [Wayfinder: Apify job-scrape sources (LinkedIn / Indeed / Glassdoor)](https://github.com/filmozolevskiy/JustApply/issues/194)  
**Date:** 2026-08-08  
**Method:** Apify Store MCP `search-actors` + `fetch-actor-details` (primary); Store web pages for cross-check. No paid Actor runs.

## Scope reminder

This note covers **Glassdoor job-listing scrape** into **Scraped** only.

JustApply **Company Research** already uses `sian.agency/glassdoor-data-scraper` (`src/core/company_research/glassdoor_intel.py`) for employer intelligence (overview / salaries / interviews). That path is **out of scope** here except as a **collision** note.

## Actor bar (from map Notes)

| # | Must-have | Pass criteria |
|---|-----------|---------------|
| 1 | Normal Apify prepaid / Store PPR or rental | No enterprise deal, no personal Glassdoor/LinkedIn cookies |
| 2 | Listing text for **Resume Matcher** | title, company, location, description |
| 3 | LinkedIn `companyUrl` for **Contact Sample** | Prefer yes; missing → Enrichment skips (locked map preference) |
| 4 | Keyword + location + volume limit | Mappable to **Search Regions** + **Per-Region Limit**, or gap documented |

## Recommendation

**Primary Glassdoor job-listing Actor: [`valig/glassdoor-jobs-scraper`](https://apify.com/valig/glassdoor-jobs-scraper)**

Why it wins:

1. **Job-search shaped inputs** — required `keywords` + `location`, optional `limit` (default 100), plus remote / rating / radius / company-size filters. Maps cleanly to one run per Search Region with Per-Region Limit ≈ `limit`.
2. **Store traction** — ~6,574 total users, ~1,296 monthly (highest among dedicated Glassdoor job Actors sampled); rating 5.00; last modified 2026-07-17.
3. **Normal PPR pricing** — Result ~$0.00036 (Bronze) / ~$0.4 per 1K jobs; Actor Start ~$0.0009 per GB. Fits **Spend Confirmation** as `regions × limit × $/result + start`.
4. **Matcher fields present** — inferred output includes `title`, `employer.name`, `location.name`, `description`, `url` / `seoUrl`, plus pay band fields.
5. **Glassdoor-only** — Source Platform can expose a dedicated `apify_glassdoor` option without inventing a fake split.

**LinkedIn `companyUrl`:** not returned. `employer.url` is a Glassdoor employer page. Enrichment Contact Sample stays skipped unless a later effort resolves LinkedIn company identity (map: out of scope).

## Collision with Company Research

| Actor | Role today | Job-listing use? |
|-------|------------|------------------|
| [`sian.agency/glassdoor-data-scraper`](https://apify.com/sian.agency/glassdoor-data-scraper) | **Company Research** (`ACTOR_ID` in `glassdoor_intel.py`) | Has a `jobSearch` operation and a **Job Search Row** PPR event, but mixing listing scrape with employer-intel ops would couple caches, Spend Confirmation, and failure modes. **Do not reuse for the scrape switcher** unless the grill ticket deliberately consolidates Glassdoor vendors. |

Company Research stays on `sian.agency`; listing scrape should use a **separate** Actor (`valig` recommended).

## Ranked candidates (job-listing focused)

| Rank | Actor | Bar 1 (plan) | Bar 2 (fields) | Bar 3 (`companyUrl`) | Bar 4 (geo/limit) | Notes |
|------|-------|--------------|----------------|----------------------|-------------------|-------|
| **1** | `valig/glassdoor-jobs-scraper` | PPR ✓ | title / employer / location / description ✓ | Glassdoor employer URL only ✗ | keywords + location + limit ✓ | Best dedicated pick |
| 2 | `cheap_scraper/glassdoor-jobs-scraper-remove-duplicate-jobs` | PPR ✓ (~$0.0009/job; $0.05 start) | Rich HTML/text description + company block ✓ | `company.companyPageUrl` is Glassdoor ✗ | keywords[] + country + location + maxItems ✓ | Strong runner-up; higher start fee |
| 3 | `agentx/glassdoor-jobs-scraper` | PPR ✓ (~$0.003/result) | Full description ✓ | May expose `social_links.linkedIns` (occasional) ~ | keyword + country + max_results + location ✓ | Costlier; possible rare LinkedIn links |
| 4 | `openclawai/job-board-scraper` | PPR ✓ (~$0.005/job) | title / company / location / description ✓ | `company_url` not reliably LinkedIn company page ✗ | `sites` includes `glassdoor`; maxResults per site ✓ | **Multi-board** — relevant to Source Platform split if LinkedIn/Indeed research lands here |
| 5 | `khadinakbar/jobs-scraper` | PPR ✓ (~$0.003/job) | title/company/location/salary/apply URL (description thinner in Store blurb) | Unlikely ✗ | `platforms` array can isolate glassdoor ✓ | Multi-board companion option |
| — | `sian.agency/glassdoor-data-scraper` | PPR ✓ (Job Search Row) | Job Search rows: title, company, location, link, salary (description depth TBD) | No LinkedIn company URL expected ✗ | query + location + limit / maxPages ✓ | **Keep for Company Research only** |
| — | Reviews / salaries-only Actors (`getdataforme/glassdoor-reviews-scraper`, etc.) | — | Wrong data shape | — | — | Out of scope |

MCP `search-actors` notes it excludes some rental/restricted Actors; Store web cross-check still surfaced the same PPR job-listing cluster (no stronger rental-only Glassdoor job Actor required for this bar).

## Field mapping vs `normalize_brightdata_job`

Bright Data normalize contract (`src/core/scraper.py`): `title`, `company`, `companyUrl`, `size`, `link`, `date`, `location`, `remoteType`, `seniority`, `employmentType`, `salary`, `description`, optional job poster contacts.

### `valig/glassdoor-jobs-scraper` → Job fields

| JustApply field | Valig output (inferred schema) | Gap |
|-----------------|--------------------------------|-----|
| `title` | `title` | — |
| `company` | `employer.name` | — |
| `companyUrl` | — (Glassdoor `employer.url`) | No LinkedIn company page → Enrichment skip |
| `size` | — | Missing; board size filter weak until matcher/other |
| `link` | `url` or `seoUrl` | Prefer stable listing URL for dedup |
| `date` | `ageInDays` only | Not a calendar date — derive approx or leave blank |
| `location` | `location.name` | — |
| `remoteType` | via filters / text heuristics | No explicit enum in output schema |
| `seniority` | — | Title heuristics (same as Bright Data fallback) |
| `employmentType` | — | May need description heuristics |
| `salary` | `pay.min` / `pay.max` / `pay.period` / `pay.currency` | Format into listing salary string |
| `description` | `description` | — |
| job poster | — | None |

### `cheap_scraper/...` extras

Has `description_text` / `description_html`, `jobTypes`, `remoteWorkTypes`, `company.companySizeCategory`, `datePublished` — closer on size/date/employment, still no LinkedIn `companyUrl`.

## Spend Confirmation sketch (valig)

Ceiling estimate per scrape run:

`Actor Start` + (`# Search Regions` × `Per-Region Limit` × Result price)

Example (Bronze): 4 regions × 200 jobs × $0.00036 ≈ $0.288 + start ≈ **~$0.29** upper bound if every region fills the limit.

## Source Platform implication

- Dedicated Actor → expose **`apify_glassdoor`** separately from LinkedIn/Indeed when those also use dedicated Actors.
- If the grill later picks `openclawai/job-board-scraper` (or similar) as a multi-board primary, Glassdoor is one value in `sites[]` — still separable on our side per map preference.

## Sources

- Apify MCP `search-actors` keywords `Glassdoor`, `Glassdoor jobs` (2026-08-08)
- Apify MCP `fetch-actor-details` for:
  - `valig/glassdoor-jobs-scraper`
  - `cheap_scraper/glassdoor-jobs-scraper-remove-duplicate-jobs`
  - `agentx/glassdoor-jobs-scraper`
  - `openclawai/job-board-scraper`
  - `sian.agency/glassdoor-data-scraper`
- Store URLs linked above
- Repo: `src/core/company_research/glassdoor_intel.py` (`ACTOR_ID = "sian.agency~glassdoor-data-scraper"`)
- Repo: `src/core/scraper.py` `normalize_brightdata_job`
