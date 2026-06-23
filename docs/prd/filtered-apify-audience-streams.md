# [PRD] Filtered Apify Audience Streams

> **Supersedes (partially):** ADR 0002 two-stage unfiltered fetch; ADR 0007 unfiltered 25-profile Contact Sample pages.
>
> **GitHub Issue:** [#68](https://github.com/filmozolevskiy/just-apply/issues/68)

## Problem Statement

Contact enrichment fetches up to 25 unfiltered company employees via Apify, then asks the LLM to find Russian Speakers and Recruiters in that random slice. At large companies the first page is mostly senior leadership with no Russian-language signals and no HR roles — so enrichment often returns zero useful contacts despite many matching employees existing at the company. Users pay for irrelevant profiles and must repeatedly click **Load More Contacts** with low odds of hitting the right audience. Contact Search Settings toggles control which audiences to keep after classification, but they do not yet control what Apify searches for.

## Solution

Drive Apify with audience-targeted filters aligned to **Contact Search Settings**. Issue one Apify run per active audience toggle (one run when only Russian Speakers or only Recruiters is on; two runs when both are on). Cache raw profiles per company **and** per audience stream. Classify each stream with the LLM, apply asymmetric contact caps, and confirm cost with stream-level detail before any paid fetch. Add a section-level tooltip on **Contact Search Settings** explaining the panel purpose.

## User Stories

1. As a job seeker, I want Apify to search for Russian Speakers using a targeted filter when that toggle is on, so that enrichment finds referral contacts instead of random executives.

2. As a job seeker, I want Apify to search for HR/recruiting employees using a targeted filter when the Recruiters toggle is on, so that enrichment surfaces hiring contacts directly.

3. As a job seeker, I want only one Apify run when a single Contact Search Settings audience toggle is active, so that I am not charged twice when I only want one audience type.

4. As a job seeker, I want two Apify runs when both audience toggles are active, so that each audience gets its own targeted search.

5. As a job seeker, I want up to **5** Russian Speakers who are **not** Recruiters when the Russian Speakers toggle is on, so that my referral pool excludes HR roles.

6. As a job seeker, I want up to **3** Recruiters when the Recruiters toggle is on, so that my HR contact list stays focused even when Russian Speakers is off.

7. As a job seeker, I want up to **5** Russian (non-HR) **plus** **3** Recruiters when both toggles are on, so that I get both outreach paths without one audience consuming the entire quota.

8. As a job seeker, I want dual-classified contacts (both Russian Speaker and Recruiter) to count toward the Recruiter cap only, so that Russian Speaker slots are reserved for non-HR referral targets.

9. As a job seeker, I want dual-classified contacts grouped under **Recruiters** with both **HR** and **RU** badges, so that UI behavior stays consistent with today.

10. As a job seeker, I want the LLM to validate both Apify streams after fetch, so that audience labels still reflect cultural-background and role nuance beyond LinkedIn filters alone.

11. As a job seeker, I want the Contact Sample Cache stored separately per audience stream (`russian`, `recruiters`), so that pagination and cache hits are correct for each filter.

12. As a job seeker, I want each stream to track its own fetched page count, so that **Load More Contacts** appends the next page for that filter only.

13. As a job seeker, I want legacy unfiltered cache entries treated as a miss, so that old cached data does not mix with new filtered streams after upgrade.

14. As a job seeker, I want **Enrich Job** to skip Apify for streams already cached, so that re-enriching the same company does not re-bill cached audience data.

15. As a job seeker, I want **Enrich Job** to show no cost dialog when all active streams are cache hits, so that cache reuse stays friction-free.

16. As a job seeker, I want **Enrich Job** to show a native confirmation listing each billable stream, profile count, total Apify runs, and estimated cost, so that I know exactly what I am paying for before proceeding.

17. As a job seeker, I want **Load More Contacts** to fetch only streams that are still below their cap after classification, so that I do not pay for audiences already full.

18. As a job seeker, I want **Load More Contacts** to consider only audience toggles currently on in Contact Search Settings, so that disabled audiences are never fetched.

19. As a job seeker, I want **Load More Contacts** to use the same native confirmation style as **Enrich Job** with per-stream page and cost detail, so that paid actions feel consistent.

20. As a job seeker, I want **Load More** to fetch both streams in one confirmation when both active streams are short, so that I can fill both quotas in one deliberate action.

21. As a job seeker, I want **Load More** to fetch only the short stream when the other is at cap, so that I am not charged for unnecessary runs.

22. As a job seeker, I want partial enrichment success when one audience fills and the other finds zero matches, so that useful contacts are not treated as a total failure.

23. As a job seeker, I want an **Enrichment Note** warning when an active audience finds no matches but other contacts exist, so that I know to try **Load More Contacts**.

24. As a job seeker, I want **Enrichment Failure** only when zero contacts are kept for any **active** audience toggle, so that failure reflects my current Contact Search Settings.

25. As a job seeker, I want **Re-classify** to reuse cached stream data without Apify, so that Outreach Settings changes remain free.

26. As a job seeker, I want **Re-classify** to merge cached streams for active toggles plus the Job Poster, so that classification behavior matches enrichment on cache hit.

27. As a job seeker, I want Apify fetches to use `companyUrl` only with no slug guessing, so that spend stays predictable per ADR 0007.

28. As a job seeker, I want empty successful Apify responses cached per stream, so that retrying a barren filter does not re-bill.

29. As a job seeker, I want infrastructure failures not cached, so that transient Apify errors can succeed on retry.

30. As a job seeker, I want the Job Poster included in the same LLM classification pass as cached stream profiles, so that poster outreach still respects audience toggles.

31. As a job seeker, I want contacted flags preserved by LinkedIn URL on re-enrichment, so that my outreach progress is not lost.

32. As a job seeker, I want hovering **Contact Search Settings** to explain that the panel controls audiences and outreach message format, so that I understand the section before toggling individual options.

33. As a job seeker, I want existing per-toggle tooltips to remain, so that each option still explains its specific purpose.

34. As a job seeker, I want estimated Apify cost in confirmations to reflect the smaller per-stream fetch size, so that cost expectations match the new model (lower than the old ~$0.22 / 25-profile page when only 3–5 profiles are fetched).

35. As a job seeker, I want Task Logs to name which audience stream is being fetched, so that I can audit Apify usage per filter.

## Implementation Decisions

### Apify actor and filters

- Actor remains `harvestapi~linkedin-company-employees`.
- **Recruiter stream** (when `target_recruiters` is on): `functionIds: ["12"]` (LinkedIn Human Resources), `maxItems: 3`, paginate with `startPage`.
- **Russian Speaker stream** (when `target_russian_speakers` is on): `searchQuery: "Russian"`, `excludeFunctionIds: ["12"]`, `maxItems: 5`, paginate with `startPage`.
- `companies` input always uses normalized Bright Data `companyUrl`.
- One orchestration call per stream per paid action; parallel or sequential execution is an implementation detail — total billed runs must match user-facing confirmation count.
- Keep full profile scraper mode (not short mode) for `languages` field quality on Russian Speaker classification.

### Run count vs Contact Search Settings

| `target_russian_speakers` | `target_recruiters` | Apify runs on cache miss |
| --- | --- | --- |
| on | off | 1 (Russian stream) |
| off | on | 1 (Recruiter stream) |
| on | on | 2 |
| off | off | 0 (no audience fetch; templates-only path if applicable) |

### Contact caps after LLM classification

- Recruiter cap: **3** always when Recruiters toggle is on.
- Russian Speaker cap: **5** when Russian Speakers toggle is on; only contacts with `russian_speaker` and **not** `is_recruiter`.
- Dual-classified: kept once, counts toward Recruiter cap only; appears under **Recruiters** contact group.
- Job Poster: classified in merged batch; kept only if matching an active audience toggle (existing ADR 0005 behavior).

### LLM classification

- Run LLM separately or in one merged batch per stream input — implementation choice; behavior must match caps above.
- Both streams validated by LLM even when Apify filters are strong (live CGI tests showed filters work but fuzzy matches still need LLM cleanup).

### Contact Sample Cache schema

- Replace single-blob-per-company model with **per-stream rows**: composite key `(company_slug, stream)` where `stream ∈ {russian, recruiters}`.
- Each row stores: raw profile JSON list, `pages_fetched`, `fetched_at`, `display_name`.
- Append-only per stream; dedupe profiles by normalized `/in/{slug}` URL on append.
- Migration: existing rows without `stream` are ignored (treated as cache miss for all streams); optional cleanup migration may delete legacy rows.
- Cache hits/misses logged per stream in Task Logs and Job Activity Log.

### Enrichment orchestration

- `source_contacts` resolves which streams are active from **Outreach Settings**, loads cached profiles per stream, fetches missing streams via Apify, merges for classification, applies caps, preserves contacted flags and Job Poster merge.
- Partial success: if any active stream yields zero kept contacts but another yields contacts → success with warning **Enrichment Note** naming the empty stream(s).
- Failure: zero kept contacts across all active streams, or infrastructure error, or missing `companyUrl`.

### API: cache status for cost confirmation

- Extend job cache-status endpoint to return which streams will trigger Apify on **Enrich Job** (replacing boolean-only `will_call_apify`), e.g. list of `{stream, maxItems, page}` and `estimated_runs` / `estimated_cost`.
- **Load More** endpoint (or preflight) returns which short streams will load next page and at what page number.
- Client shows native `confirm()` only when `estimated_runs > 0`.

### Kanban confirmation copy (native `confirm()`)

Same structure for **Enrich Job** and **Load More Contacts**:

```
<Action> will fetch from LinkedIn via Apify:

• Russian Speakers — 5 profiles
• Recruiters — 3 profiles

2 Apify runs · estimated ~$0.10

Proceed?
```

- List only billable streams.
- **Load More** variant includes page number: `next 5 profiles (page 2)`.
- No dialog when zero runs.

### Contact Search Settings UI

- Add delayed floating tooltip on **Contact Search Settings** section heading (same mechanism as toggle tooltips): *“Control which audiences to enrich and how outreach messages are written.”*
- Do not remove existing per-toggle tooltips.

### Superseded behavior

- Remove unfiltered `maxItems: 25` single-fetch as default enrichment path.
- ADR 0002 staged `searchQuery: "Russian"` then fallback `jobTitles` flow is replaced by parallel filtered streams + LLM.
- Typical first-fetch cost drops vs 25-profile page but doubles when both audiences run (~2 actor starts + 8 profiles max).

## Testing Decisions

**Good test rule:** Assert user-visible outcomes and API contracts — billed run count, caps, cache skip, confirmation gates — not internal call order unless it maps directly to Apify spend.

**Preferred seams (highest first):**

1. **HTTP API + dashboard strings** — cache-status payload drives `confirm()` content; tests in existing cost-confirmation and outreach-settings test modules read rendered HTML/JS and JSON responses.
2. **Enrichment pipeline with mocked Apify actor** — inject return profiles per stream; assert kept contact counts, dual-classified bucketing, partial-success notes, zero re-fetch on cache hit (pattern from contact sample cache and enrichment pipeline tests).
3. **Cache module** — per-stream get/set/append, legacy row treated as miss, independent `pages_fetched` (pattern from load-more-contacts tests).
4. **Classifier caps** — merged profile list respects 5/3 caps and dual-classified recruiter-only counting (pattern from outreach classifier tests).

**Prior art:** `test_contact_sample_cache.py`, `test_load_more_contacts.py`, `test_cost_confirmations.py`, `test_outreach.py`, `test_enrichment_pipeline.py`, `test_dashboard_outreach_settings.py`.

**Not tested at UI browser level:** Apify live integration (validated manually on CGI); pytest continues to mock actor boundary.

## QA Validation

- [ ] Open **Contact Search Settings** → hover the section title for ~1 second → tooltip explains audiences and outreach message format.
- [ ] Turn on **Russian Speakers** only → **Enrich Job** on an Accepted job with `companyUrl` and no cache → confirmation lists one Russian stream (5 profiles) → confirm → drawer shows up to 5 Russian Speaker contacts (non-HR grouped separately from Recruiters).
- [ ] Turn on **Recruiters** only → **Enrich Job** on a fresh company → confirmation lists one Recruiter stream (3 profiles) → confirm → drawer shows up to 3 Recruiter contacts.
- [ ] Turn on **both** toggles → **Enrich Job** on a fresh company → confirmation lists **two** streams (5 Russian + 3 Recruiters) → confirm → drawer can show both groups within caps.
- [ ] After enrichment with both toggles where only Recruiters filled → card is **not** marked failure → **Enrichment Note** warns Russian Speakers empty → **Load More** offered.
- [ ] **Enrich Job** again on same company with both streams cached → no cost confirmation → contacts refresh without new Apify charge.
- [ ] With one audience at cap and the other short → **Load More Contacts** confirmation lists **only** the short stream → after confirm, cap can increase for that audience only.
- [ ] **Re-classify** after toggling an audience setting → no cost confirmation → contacts update from cache without Apify.
- [ ] Job missing `companyUrl` → **Enrich Job** shows no Apify confirmation → **Enrichment Note** explains missing URL.

## Out of Scope

- ADR document authoring (recommended follow-up: ADR 0008).
- Changing Outreach Message Format generation logic beyond template audience selection.
- `profileScraperMode: short` cost optimization.
- Per-job Contact Search Settings (remains global).
- Automatic re-classify all Accepted jobs when settings change.
- Custom modal dialogs (stay with native `confirm()`).
- LinkedIn language filter API (use `searchQuery` + LLM only).
- CLI `--promote` changes unless required by status/contact schema migration.

## Further Notes

- Live Apify smoke tests on CGI validated: `searchQuery: "Russian"` surfaces Russian-speaking employees; `functionIds: ["12"]` returns HR/TA roles; `excludeFunctionIds: ["12"]` removes recruiter from Russian search (e.g. Vytautė Tanev excluded vs baseline).
- Unfiltered first page at CGI returned zero Russian-language profiles; filtered search returned 19/25 with Russian in languages — motivates this PRD.
- Estimated cost per run: actor start (~$0.015–0.02) + full profile fee × `maxItems` (5 or 3) — update confirmation strings from legacy “~$0.22 per page”.
- Implementation should follow glossary terms in `CONTEXT.md` (already updated during design grill).
