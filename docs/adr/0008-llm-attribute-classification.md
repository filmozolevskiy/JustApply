# 0008: LLM Attribute Classification for Remote Type and Seniority

## Status

Accepted — partially supersedes Pre-Evaluation Filters (remote type) and scraper seniority gating from ADR 0006.

## Context

ADR 0006 introduced **Pre-Evaluation Filters** so remote-type mismatches were dropped before the Resume Matcher, using scraper-derived `remoteType` from Bright Data (`is_remote` flag and location-string heuristics). Seniority was gated in the scraper post-filter using the same unreliable Bright Data fields and title keywords.

In practice, Bright Data often mislabels remote/hybrid roles (e.g. marking an in-office role when the description says hybrid). Jobs that would match search preferences never reached the Resume Matcher, which already reads title and description and returns `remoteType` — but that value was ignored for gating and not persisted over scraper values.

## Decision

### Resume Matcher as attribute classifier

1. **Extend the Resume Matcher JSON** with `seniority` (`junior` | `mid` | `senior`) alongside existing `remoteType`. One Gemini call per job — no separate extraction pass.

2. **Move attribute gating after evaluation** — no separate pipeline stage name. Flow: scrape → deduplicate → Resume Matcher → attribute check → save. Remote type and seniority on saved jobs come from LLM output when present.

3. **Per-field Bright Data fallback** — when the matcher returns a field, use it; when a field is missing, fall back to the scraper value for that field only. Gate on the merged result.

4. **Full matcher failure** — when the matcher returns nothing (`{}`: no API key, timeout, parse error), fall back to scraper values for both `remoteType` and `seniority`, gate on those, and save with empty/zero match fields if the attribute gate passes.

5. **Hard gate on mismatch** — jobs whose merged `remoteType` or `seniority` do not match the search run's allowed preferences are not saved. Log each rejection to Task Logs: `Attribute mismatch: '{title}' at '{company}' — …`.

6. **Remove scraper seniority filter** — all non-duplicate jobs reach the Resume Matcher. Company size stays as a scraper post-filter only.

7. **Remove Pre-Evaluation Filters for remote type** — the `pre_evaluation` remote-type gate before the matcher is deleted.

### mock_eval

8. **Bypass attribute gating in mock_eval** — save non-duplicate jobs without checking remote/seniority preferences. Scraper values remain for display. Log that gating was skipped. mock_eval jobs do not get the Unclassified badge.

### Unclassified badge

9. **Badge on full matcher failure only** — when the matcher returned `{}` and both attributes came from the scraper, mark the saved job as **Unclassified**. Show an **Unclassified** badge on the Kanban card and in the job drawer. Explanatory text appears on hover only (tooltip), not as always-visible copy. No badge when only one field fell back (per-field partial success).

### Task Logs

10. **Rename aggregate counter** — `Pre-filtered` becomes `Attribute-filtered` in the pipeline summary.

11. **Summary line uses a `summary` log level** — distinct styling (bold, green, subtle top border) so the footer stands out from other log lines. Other success messages (`Scraper process complete`, etc.) keep the existing `success` level.

## Considered Options

- **Separate lightweight extraction call before matching** — rejected; duplicates prompt infrastructure for marginal cost savings at current search volumes.
- **Fail closed when LLM unavailable** — rejected; user wants Bright Data fallback so search still works without Gemini.
- **All-or-nothing fallback on partial JSON** — rejected; per-field fallback preserves good LLM output when only one field is missing.
- **Badge on any scraper fallback** — rejected; badge signals full classification failure, not partial.
- **Badge on mock_eval jobs** — rejected; mock mode is intentional, not a production failure.
- **Post-Evaluation Filters as a named stage** — rejected; attribute gating is folded into the Resume Matcher contract, not a separate glossary term.
- **Move company size to LLM** — rejected; Bright Data company size is reliable enough for coarse filtering.

## Consequences

- **Higher Gemini spend on search** — jobs that ultimately fail remote/seniority checks are now evaluated before being dropped (reverses ADR 0006's LLM cost savings for remote mismatches).
- **More accurate remote/seniority on saved jobs** — LLM reads description, not location heuristics alone.
- **Unclassified jobs are visible** — user can spot cards where attributes may be wrong because Gemini did not run.
- **Pre-Evaluation Filters glossary term becomes obsolete** — remote type was the only v1 gate; company size remains scraper-only.
- **Job Activity Log still excludes attribute rejections** — they remain pipeline internals in Task Logs only.
- **Board Controls remote-type filter** — filters on stored `remoteType`, which will be LLM-derived (or scraper on Unclassified jobs).

## Implementation checklist

- [x] Add `seniority` to Resume Matcher prompt and response handling
- [x] Pipeline: evaluate → merge attributes → gate → persist LLM values
- [x] Remove `passes_remote_type_filter` pre-eval call; remove scraper seniority filter
- [x] Add `unclassified` (or equivalent) flag on job schema and DB
- [x] Kanban card + drawer: Unclassified badge with hover tooltip
- [x] Task Logs: `summary` level CSS; `Attribute-filtered` counter; `Attribute mismatch` per-job lines
- [x] Update tests (`test_search_pipeline`, `test_pre_evaluation_remote_type`, `test_scraper`, etc.)
- [x] Update CONTEXT.md (done in this change)
