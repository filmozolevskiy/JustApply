# 0006: Contact Sample Cache and Pre-Evaluation Filters

## Status

Accepted — partially supersedes the "every enrichment costs one Apify run" consequence in ADR 0005.

## Context

ADR 0005 required a full Apify fetch on every enrichment so Job Poster contacts were audience-classified and Outreach Settings changes could take effect. That fixed correctness problems but increased Apify spend when multiple jobs targeted the same company. Separately, the Search & Evaluation Pipeline called the Resume Matcher (Gemini) for every new scraped job — including duplicates already on the board (already skipped) and remote-type mismatches that the scraper could reject cheaply.

## Decision

### Contact Sample Cache

1. **Cache the raw Contact Sample** — store up to 100 raw Apify employee profiles per company, not post-classification contacts. Outreach Audience classification runs on every enrichment regardless of cache hit.

2. **Key by LinkedIn company slug** — same normalization `source_contacts` uses for Apify lookup (lowercase, trimmed, spaces/underscores → hyphens). Stored in a `contact_sample_cache` table in the Job Tracker Database.

3. **No TTL** — entries persist until explicitly busted. Empty or failed Apify fetches are never cached.

4. **Refresh Contacts** — the sole re-run action on enriched jobs (Outreach Contacts section header). Busts the company cache, fetches fresh profiles via Apify, re-classifies, regenerates templates. Sourced jobs use Enrich Job for first fetch. There is no cache-preserving re-enrich in the Kanban Dashboard.

5. **Observability** — cache hits log to Task Logs and the job's Job Activity Log.

### Search & Evaluation Pipeline

6. **Two-phase ordering** — scrape → deduplicate against existing cards → Pre-Evaluation Filters → Resume Matcher only on survivors.

7. **Pre-Evaluation Filters (v1)** — remote-type check using scraper-derived `remoteType` against the search run's allowed preferences. Rejected jobs are dropped (not saved) and logged to Task Logs. Recruiting Company detection stays in the Resume Matcher — agency postings are still saved with penalty, per existing behavior.

## Considered Options

- **Cache classified contacts** — rejected because Outreach Settings are global toggles; caching post-classification results would serve stale audience selections.
- **TTL-based expiry (e.g. 30 days)** — rejected; staleness is opt-in via Refresh Contacts.
- **Re-enrich + Refresh Contacts** — rejected in favor of a single Refresh Contacts button on enriched jobs to keep the UI simple.
- **Drop recruiting agencies in Pre-Evaluation Filters** — rejected; keep current save-with-penalty behavior for agency postings.

## Consequences

- **Apify cost drops for multi-job companies** — enriching five roles at Stripe costs one Apify run until Refresh Contacts busts the cache.
- **Outreach Settings changes on enriched jobs cost Apify** — without a cache-preserving re-enrich action, toggling audience settings requires Refresh Contacts.
- **Stale employee rosters until manual refresh** — acceptable trade-off given "people rarely change jobs"; no automatic expiry.
- **LLM cost drops on search** — remote-type mismatches no longer reach the Resume Matcher; duplicates were already skipped.
- **Search runs emit an aggregate cost summary** to Task Logs (scraped, duplicates skipped, pre-filtered, evaluated, saved).
- **ADR 0005 poster/classification rules unchanged** — Job Poster merge, audience gating, and `contacted` preservation still apply on every enrichment.
