# 0007: Apify Spend Controls, Accepted Lane, and Found Status

## Status

Accepted — supersedes lane-triggered enrichment, Refresh Contacts cache busting, slug fallback, and empty-cache policy from ADR 0006. Partially supersedes ADR 0005 enrichment lane transitions.

## Context

Apify spend on contact enrichment was far higher than the number of companies enriched. Root causes: drag-to-**Enriching** triggered paid runs accidentally; slug fallback issued multiple Apify calls per enrichment; **Refresh Contacts** re-scraped page 1; empty fetches were not cached so retries re-billed; and dev testing on the local dashboard used real credits.

Investigation showed pytest does not call Apify (tests mock `_run_apify_actor` / `source_contacts`). The app is intended to run locally with real Apify — no `MOCK_APIFY` flag.

## Decision

### Kanban lanes and status renames

1. **Replace `sourced` with `found`** — the first lane is **Found**; DB status value becomes `found`. Migrate existing `sourced` rows on upgrade.

2. **Replace `enriching` and `enriched` with `accepted`** — single **Accepted** lane. Migrate existing `enriching` and `enriched` rows to `accepted` on upgrade.

3. **Final lane order:** Found → Accepted → Contacted → Interviewing → Rejected.

4. **Enrichment never triggered by lane drag** — moving a card never starts Apify. Only explicit buttons do.

5. **Entering Accepted:**
   - Drag Found → Accepted: lane move only, no Apify.
   - **Enrich Job** (from Found or Accepted): move to Accepted if needed, then run enrichment in place. Card never leaves Accepted.

6. **In-progress UI:** spinner badge on the Accepted card (e.g. “Enriching…”); pipeline status stays `accepted`.

### Apify fetch policy

7. **`companyUrl` only** — no name-based LinkedIn slug guessing. One Apify attempt per fetch using the Bright Data company page URL.

8. **Missing `companyUrl`:** skip Apify; **Enrichment Failure** with an explanatory **Enrichment Note**. Job stays in Accepted.

9. **Contact Sample size:** 25 profiles per Apify page (`maxItems: 25`).

10. **No `MOCK_APIFY`** — local dashboard uses real Apify when `APIFY_API_TOKEN` is set.

### Contact Sample Cache (replaces Refresh Contacts bust)

11. **Append-only cache** — never bust. Key by LinkedIn company slug from `companyUrl`.

12. **Cache successful empty results** — zero-profile Apify responses are stored like non-empty samples to prevent repeat billing on retry.

13. **Do not cache infrastructure failures** — trigger errors, timeouts, missing credentials.

14. **Track fetched pages** — store how many LinkedIn search pages have been loaded so the next fetch uses Apify `startPage` to append page 2, 3, …

15. **No page cap** — user may keep loading until Apify returns no further pages or they stop.

16. **Load More Contacts** replaces **Refresh Contacts** — appends the next page (~25 profiles), re-classifies the combined sample, confirms with estimated cost before every run.

17. **Re-classify** — per-job drawer action; re-runs LLM classification and template generation on the cached sample without Apify. Used after **Outreach Settings** change.

### Cost confirmations

18. **Enrich Job:** confirm only when an Apify fetch will run (cache miss). Cache hits re-classify without a cost dialog.

19. **Load More Contacts:** always confirm before each paid page fetch.

## Considered Options

- **Slug fallback (try `trane`, `trane-technologies`, …)** — rejected; caused ~17 paid runs for one company (Trane).
- **`MOCK_APIFY` for local dev** — rejected; app purpose is real local job hunting with real Apify.
- **Refresh Contacts (bust cache, re-scrape page 1)** — rejected in favor of append-only **Load More Contacts**.
- **Separate Enriching / Enriched lanes** — rejected; drag-to-enrich caused accidental spend; enrichment runs in place on Accepted.
- **Automatic re-classify on Outreach Settings save** — rejected; per-job **Re-classify** button is explicit and avoids LLM churn across all Accepted cards.
- **Page cap (e.g. 4 pages / 100 profiles)** — rejected; user may load until Apify is exhausted.
- **Short Apify profile mode ($4/1k)** — deferred; keep full profiles at 25/page for Russian Speaker `languages` field quality.

## Consequences

- **Apify runs ≈ paid button clicks** — no multiplier from slug loops or lane drops.
- **Typical first fetch ~$0.22** (25 full profiles + actor start); each **Load More** adds ~$0.22.
- **Jobs without `companyUrl` cannot enrich** until re-scraped or fixed upstream — fail fast, zero spend.
- **Outreach Settings changes are free** via **Re-classify**; no Apify required.
- **ADR 0006 Refresh Contacts and empty-cache rules are obsolete** — implementation must migrate cache schema for page tracking and rename the API/UI endpoint.
- **Implementation not in this ADR** — code, tests, and DB migrations follow separately.
