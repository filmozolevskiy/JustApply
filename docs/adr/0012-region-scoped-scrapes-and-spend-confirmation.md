# 0012: Region-scoped scrapes and Spend Confirmation modal

> Formerly ADR 0010.

## Status

Accepted — partially supersedes ADR 0007 (the "native `confirm()` style" cost dialogs).

## Context

The dashboard scrape (`triggerScrapeRun` → `POST /api/search`) fired immediately with **no spend confirmation**, unlike the Apify-paid **Enrich Job** / **Load More Contacts** gates. Worse, the default location was the free-text value `"Remote"`, which is not a geographic place. Bright Data's discover-by-keyword dataset (`gd_lpfll7v5hcqtkxl6l`) treats `location` as a geographic string and a separate `remote` field for on-site/hybrid/remote; passing `"Remote"` as the location silently disables geo-narrowing, so a single run discovers *every* matching posting across the selected countries. Combined with the code never setting `limit_per_input`, scrape spend was effectively unbounded and could not be estimated up front.

Bright Data bills the Web Scraper API at **$1.50 / 1,000 successful records** pay-as-you-go (~`$0.0015`/record; 5,000 free records/month). The trigger payload is already an array of input items (one per country); the API supports many items, each with its own `location`, `country`, and `limit_per_input`. That makes a bounded, region-scoped scrape with an honest cost ceiling achievable without changing datasets.

Separately, the existing cost dialogs use native browser `confirm()` / `alert()`. ADR 0007 codified that "native `confirm()` style." The user wants a single app-styled modal for all spend gates.

## Decision

1. **Required, country-scoped Search Regions.** Selecting a country (US, CA, GB, DE) reveals that country's administrative divisions (US = curated major-job-market states; CA = 13 provinces/territories; DE = 16 Länder; GB = 4 nations). At least one **Search Region** is required per selected country; the Run Scraper action is disabled until satisfied, and `POST /api/search` rejects violations server-side (`422`). There is no "all of \<country\>" / whole-country scrape in this version.

2. **Per-Region Limit (configurable `limit_per_input`).** Each selected Search Region becomes one Bright Data input item (`{keyword, country, location}`) capped at the run's **Per-Region Limit** — a single global value applied to every region. The user picks it with a number stepper (range 25–1000, step 25, default 200) in Job Search Settings, and may adjust it in the scrape **Spend Confirmation**, which writes the change back to settings. The server clamps to [25, 1000]. The run's worst case is therefore `regions × Per-Region Limit` records.

3. **"Remote" is barred as a location.** Remote/hybrid/on-site stays a post-scrape job attribute, never the geographic `location` field. The free-text location box is removed.

4. **Per-record cost basis.** A configurable `COST_PER_BRIGHTDATA_RECORD = 0.0015` drives a bounded estimate `regions × 200 × COST_PER_BRIGHTDATA_RECORD`, shown in the modal as an upper bound ("actual cost depends on how many postings match").

5. **Spend Confirmation modal.** One reusable, promise-based, app-styled modal (`openConfirmModal`) replaces the native `confirm()` gates for the scrape, **Enrich Job**, and **Load More Contacts**, and replaces the blocked-reason `alert()` (single acknowledgement button, no cancel). The scrape variant uses the **"checkout receipt" split layout** (variant B from the UI prototype): scope/region chips on the left, an itemized cost ceiling on the right (`regions × Per-Region Limit × $0.0015`), with an editable **Per-Region Limit** stepper that recomputes the ceiling live. Amber spend accent; confirm/cancel labels are **Run scraper** / **Cancel**; no acknowledgement checkbox; no free-records messaging.

6. **Region list source of truth.** A single Python module (`src/core/regions.py`) is authoritative; the dashboard renders the pickers from `GET /api/regions` and the backend validates submitted regions against the same module, so UI and server cannot drift.

## Considered Options

- **Keep unbounded `discover_new`, qualitative warning only** — rejected once required regions + `limit_per_input` made an honest ceiling possible.
- **Validated multi-value free-text location + country checkboxes (cartesian)** — rejected; typos still cause over-broad scrapes and pairing a region with the wrong country is nonsensical.
- **Optional regions with a whole-country fallback** — rejected; reintroduces the over-broad, expensive run the feature exists to prevent.
- **All 50 US states** — rejected in favor of a curated major-market shortlist to discourage 50-state sweeps.
- **Per-scrape preflight endpoint for the estimate** (like `cache-status`) — rejected; the estimate is pure client-side arithmetic from the picked regions. Validation still lives server-side.
- **An "I understand" checkbox / type-to-confirm friction** — rejected; a prominent warning plus a non-default confirm button is enough and a per-run checkbox gets ignored.
- **Pushing `remote_type` into Bright Data's `remote` field** — deferred; remote filtering stays post-scrape (non-goal here).

## Consequences

- **Scrape spend is bounded and estimable** — hard ceiling `regions × Per-Region Limit × $0.0015`, with the Per-Region Limit itself clamped to 25–1000; no "Remote"/whole-country blowups.
- **Completeness is traded for predictability** — each region is capped at the Per-Region Limit per run; users widen coverage by selecting more regions or raising the limit (up to 1000), not by removing the cap.
- **`POST /api/search` gains server-side validation** (≥1 region per country, no "Remote"/unknown regions) and a new `GET /api/regions` endpoint; the scraper sets `limit_per_input` and builds one input per Search Region.
- **ADR 0007's native `confirm()` style is superseded** by the Spend Confirmation modal for all three paid actions; the Apify cost-confirmation *logic* from ADR 0007 is unchanged, only its presentation.
- **Implementation not in this ADR** — code, tests, and the region list follow separately.
