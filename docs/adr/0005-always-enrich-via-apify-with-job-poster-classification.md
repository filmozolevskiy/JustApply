# 0005: Always Enrich via Apify with Job Poster Classification

## Status

Accepted — supersedes the "poster → skip Apify" shortcut described in ADR 0002.

## Context

ADR 0002 established a hybrid scraping architecture where, if a job listing included a `job_poster` contact from Bright Data (~11% of listings), enrichment skipped the Apify run entirely and used that contact as-is. This was a pragmatic shortcut but created two problems:

1. The Job Poster was stored without an Outreach Audience classification — they appeared in the contact list regardless of which toggles (Russian Speakers, Recruiters) were active in Outreach Settings.
2. Re-enrichment never refreshed contacts; the poster survived unchanged even if Outreach Settings changed.

Additionally, the poster identity was only set at enrichment time, making the Kanban drawer unavailable for sourced-but-not-enriched jobs.

## Decision

Every enrichment trigger always runs the full Apify fetch-and-classify flow:

1. **Job Poster at scrape time** — when Bright Data returns `job_poster`, store the contact in the job immediately with `is_job_poster: True`. Visible on the Kanban at `sourced`.

2. **Apify on every enrich** — `source_contacts` removes the early return that skipped Apify when contacts already existed. Re-enrichment always re-fetches the Contact Sample.

3. **Poster in classification batch** — the Job Poster (if present) is extracted from existing contacts and included in the same LLM classification pass as the Apify sample:
   - **URL match** — poster URL is normalized to `/in/{slug}` (stripping country subdomain, `www`, trailing slash, query params) and compared against Apify results. When matched, the Apify profile is used for classification.
   - **Not in sample** — poster is injected as a synthetic extra at the end of the batch.
   - **Apify failure** — if Apify returns zero profiles, classify the poster alone.

4. **Audience flags control inclusion** — `is_job_poster` is an identity-only flag. The poster is kept only if the LLM classifies them into an active Outreach Audience with the corresponding toggle on.

5. **`contacted` preservation** — on re-enrichment, contacts whose normalized URL matches a previous contact preserve their `contacted: True` status.

## Consequences

- **Every enrichment costs one Apify run**, even for jobs that already had a Job Poster. This increases Apify credit consumption for the ~11% of jobs with a poster.
- **Poster is audience-gated** — a Job Poster who is neither a Russian Speaker nor a Recruiter is excluded from the final contact list, consistent with Outreach Settings.
- **Company-level Apify caching** is out of scope and noted as future work to reduce repeated calls for jobs from the same company.
