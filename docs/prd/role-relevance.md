# [PRD] Role Relevance

> **GitHub Issue:** [#207](https://github.com/filmozolevskiy/JustApply/issues/207)

## Problem Statement

A job seeker searches for a role such as QA and still sees many listings that are a different job family (for example a product software engineer / developer). Those listings survive scrape post-filters, land in **Scraped**, then often reach **Matched** because the **Resume Matcher** scores resume fit and the attribute gate only checks remote type, seniority, **Employment Type**, and **Salary Min**. The seeker wastes triage time on cards that were never the searched role.

## Solution

After the **Resume Matcher** returns JSON, apply **Role Relevance**: is this listing the same kind of role as the search run's query (including adjacent titles in that family)? A clear no moves the job to **Rejected** as a **Role-filtered Job**. Unsure, missing, or **Unclassified** passes. Task Logs count role-filtered separately from attribute-filtered and fallback-rejected. Rejected cards show a `Role-filtered` pill and a Job Info row in the drawer.

## User Stories

1. As a job seeker searching for QA, I want developer / product-engineer listings rejected after evaluation, so that **Matched** is not full of the wrong job family.

2. As a job seeker searching for QA, I want SDET and Software Engineer in Test listings to pass **Role Relevance**, so that adjacent titles in the QA family are not thrown out.

3. As a job seeker, I want other adjacent titles in the same family as my query to pass, so that the gate is not a brittle exact-title match.

4. As a job seeker, I want **Role Relevance** to use my search query as the target, so that I do not maintain a separate Target Role field.

5. As a job seeker, I want **Role Relevance** to ignore resume fit, so that a strong developer match against a QA-shaped resume still fails when the listing is not a QA-family role.

6. As a job seeker, I want listings to stay in **Scraped** until the **Resume Matcher** and **Role Relevance** run, so that I can still see incoming cards before evaluation finishes.

7. As a job seeker, I want a listing that is clearly the wrong role to move to **Rejected**, so that it does not sit in **Matched**.

8. As a job seeker, I want a listing that is too thin or mixed to classify to pass **Role Relevance**, so that unclear jobs are not silently discarded.

9. As a job seeker, I want a matcher JSON object that omits `roleRelevant` to pass, so that parse gaps do not fail closed.

10. As a job seeker, I want `roleRelevant: null` to pass, so that the model can say “unsure” without rejecting.

11. As a job seeker, I want **Unclassified** poison-fallback jobs to skip **Role Relevance**, so that scraper fallback still follows today’s Unclassified path.

12. As a job seeker, I want French or bilingual titles classified after the matcher reads and translates the listing, so that Québec / bilingual posts are not rejected for language.

13. As a job seeker, I want no hardcoded French keyword list, so that new titles do not depend on a dictionary we maintain.

14. As a job seeker running search, I want the query snapshotted on that **Batch Evaluation Job**, so that evaluation uses the query I searched with, not a later edit.

15. As a job seeker running backfill, I want **Role Relevance** to use the query stored on that backfill **Batch Evaluation Job**, so that in-flight batches stay consistent.

16. As a job seeker on auto-retry, I want retry batches to reuse the finished round’s stored query, so that poison retries do not pick up a different query mid-round.

17. As a job seeker running **Reassess** or **Reassess all**, I want **Role Relevance** to use the current Job Search Settings query, so that a changed search query can re-filter existing cards.

18. As a job seeker, I want **Reassess** to demote **Scraped** and **Matched** jobs that fail **Role Relevance** into **Rejected**, matching how the attribute gate already demotes those lanes.

19. As a job seeker, I want **Accepted** and later lanes to keep their lane on **Reassess** even if **Role Relevance** fails, so that roles I already chose to pursue are not yanked.

20. As a job seeker using `mock_eval`, I want **Role Relevance** skipped, so that local dashboard tests do not need Gemini role verdicts.

21. As a job seeker, I want **Task Logs** chunk summaries to include a role-filtered count, so that I can see how many listings failed the role check per batch.

22. As a job seeker, I want the **Evaluation Round Summary** to include role-filtered totals, so that the round footer matches chunk math.

23. As a job seeker, I want role-filtered counts separate from attribute-filtered counts, so that I can tell wrong-role rejects from preference rejects.

24. As a job seeker, I want role-filtered counts separate from fallback-rejected counts, so that Unclassified poison rejects stay distinct.

25. As a job seeker, I want CLI `--collect` footers to print the same role-filtered count, so that terminal and dashboard stay aligned.

26. As a job seeker, I want no new per-job **Task Logs** lines for each **Role-filtered Job**, so that large searches stay readable.

27. As a job seeker, I want no new **Job Activity Log** entries for pipeline **Role Relevance** rejects, so that drawer history stays about actions I took.

28. As a job seeker looking at **Rejected**, I want a `Role-filtered` pill on the Kanban card in the badge row (same place as Unclassified / Recruiter), so that I can spot why the card was rejected without opening it.

29. As a job seeker, I want hover text on that pill to be allowed, so that a short explanation can appear without extra always-visible chrome.

30. As a job seeker opening the drawer on a **Role-filtered Job**, I want an extra Job Info row `Role Relevance: Role-filtered` plus a short reason (searched role vs listing), so that I can confirm the query and the listing.

31. As a job seeker, I want no title strip and no recruiter-style banner for **Role-filtered Jobs**, so that Rejected cards stay visually consistent with other filter rejects.

32. As a job seeker, I want attribute-gate failures that passed **Role Relevance** to still show as today (Rejected, attribute-filtered count, no Role-filtered pill), so that preference mismatches are not relabeled as wrong role.

33. As a job seeker, I want a job that fails both **Role Relevance** and the attribute gate counted only as role-filtered, so that the more specific “wrong role” reason wins.

34. As a job seeker, I want company-size and Employment Type scrape post-filters unchanged, so that Role Relevance does not replace early vendor filters.

35. As a job seeker, I want **Board Controls** unchanged by this spec, so that client-side refine is not a second role gate.

36. As a maintainer, I want `roleRelevant` on the existing **Resume Matcher** JSON (boolean, nullable), so that we do not add a second Gemini call.

37. As a maintainer, I want the matcher prompt to include the search query and **Role Relevance** rules, so that batch JSONL and live **Reassess** share one contract.

38. As a maintainer, I want batch JSONL built with that same query snapshot, so that the model and the poller gate agree.

39. As a maintainer, I want a persisted query column on **Batch Evaluation Job** rows, next to existing gate preference snapshots, so that poller, retry, and backfill can read it after restart.

40. As a maintainer, I want empty or missing stored query to skip **Role Relevance** (pass), so that old in-flight batches and incomplete snapshots do not fail closed.

41. As a maintainer, I want a persisted flag on the job so the Kanban can render the pill after reload, so that Role-filtered is not only an in-memory poller fact.

42. As a maintainer, I want the short drawer reason stored or composed from searched query vs listing title at write-back, so that the UI does not need a new matcher `roleLabel` field in v1.

43. As a maintainer, I want `write_back_job_evaluation` to apply **Role Relevance** then the attribute gate, so that lane moves stay in one write-back.

44. As a maintainer, I want **CollectResult** to carry `role_filtered` beside existing counters, so that aggregation, SSE, and CLI stay one shape.

45. As a maintainer, I want glossary terms in **CONTEXT.md** to stay the source of names (**Role Relevance**, **Role-filtered Job**), so that logs and UI copy match the domain.

46. As a maintainer, I want the existing `reject_unrelated.py` helper left out of the product pipeline, so that we do not mix union-regex career families with query **Role Relevance**.

47. As a contributor, I want the throwaway `/prototype/role-reject-copy` page not shipped as product UI, so that production follows variant A on the real board only.

48. As a contributor, I want unit tests of parse-and-pass behavior without Gemini, so that true / false / null / omitted / junk JSON are locked.

## Implementation Decisions

- **Placement:** **Role Relevance** runs after a successful **Resume Matcher** result, inside the same evaluation write-back that already applies the attribute gate. Do not drop listings before save. Do not add a pre-scrape or vendor job-function filter for this spec.

- **Target:** The search query string (Job Search Settings position / CLI `--search` argument). Not the **Active Resume Profile**. No new Target Role field.

- **Matcher JSON:** One extra field on the existing matcher object:

  ```json
  "roleRelevant": true | false | null
  ```

  From the verdict prototype: `true` / omitted key / `null` / unexpected type → pass; only JSON `false` is a **Role-filtered Job**. No role enum for gating. No `roleLabel` in v1.

- **Parse/pass helper (from prototype):** Reject only on a clear JSON `false`:

  ```python
  def parse_role_relevant(payload: dict) -> tuple[bool | None, str]:
      if not isinstance(payload, dict):
          return None, "not an object"
      if "roleRelevant" not in payload:
          return None, "omitted"
      value = payload["roleRelevant"]
      if value is True or value is False or value is None:
          return value, "ok"
      return None, f"unexpected {value!r} (treated as unsure)"

  def passes_role_relevance(role_relevant: bool | None) -> bool:
      return role_relevant is not False
  ```

- **Prompt:** Fold query + rules into the existing matcher prompt (batch JSONL and `evaluate_job`). Rules: same role family as the query, including adjacent titles (example: query QA includes QA Engineer, SDET, Software Engineer in Test, test-automation); `false` only when clearly a different role (example: product/feature developer vs QA); `null` when too thin or mixed; do not use resume fit; read the listing in its written language (including French / bilingual) and translate as needed before setting `roleRelevant`.

- **Query snapshot:** Persist the query on each **Batch Evaluation Job** at submit, same pattern as remote type / seniority / Employment Type / Salary Min snapshots. Search, backfill, and retry read that stored query. **Reassess** / **Reassess all** use the current Job Search Settings query. No per-job original query in v1. Missing or blank query → skip **Role Relevance** (pass).

- **Gate order:** On matcher success: **Role Relevance** first. If it fails → **Rejected**, increment role-filtered, persist the Role-filtered flag and short reason, do not also count as attribute-filtered. If it passes → existing attribute gate (matched vs attribute-filtered). **Unclassified** fallback does not run **Role Relevance**.

- **Reassess:** Same order. Demote only **Scraped** / **Matched** on failure (same lane set as the attribute gate). Later lanes keep status; matcher fields may still update. Persist Role-filtered flag only when the job is actually a **Role-filtered Job** in **Rejected** (or clear the flag when a later reassess passes).

- **mock_eval:** Skip **Role Relevance**, same as the attribute gate.

- **Persistence:**
  - **Batch Evaluation Job:** query snapshot field.
  - **Job:** boolean (or equivalent) so the board can show the pill after reload; short reason text for the drawer Job Info row, composed at write-back from searched query vs listing title (not a second LLM field).
  - Expose those fields on the existing jobs API used by the Kanban.

- **Task Logs:** Extend chunk and **Evaluation Round Summary** lines with `N role-filtered` next to attribute-filtered. Extend **CollectResult** and CLI `--collect` footer. Counts only.

- **UI (prototype variant A):** `Role-filtered` pill in the card badge row beside Unclassified / Recruiter. Drawer: extra Job Info row, not a banner or title strip. Hover on the pill allowed. Do not ship the standalone prototype page as the product surface.

- **Out of the pipeline:** `reject_unrelated.py` / reject-unrelated-jobs skill stay a manual helper. Matcher `matchScore` still never auto-Rejects.

- **Glossary:** Keep **CONTEXT.md** as the name source. Implementation should also update the **Matched Job** definition so it includes passing **Role Relevance**, not only the attribute gate. **Batch Poller** glossary should mention Role Relevance rejects alongside the attribute gate.

## Testing Decisions

Good tests assert external behavior: lane (`Matched` vs `Rejected`), counters, log line text, persisted flags/reason, prompt containing the query and `roleRelevant`, and visible card/drawer copy wiring — not private poller accumulator names or Gemini live calls.

**Preferred seams (highest first):**

1. **Parse/pass helper** — table of JSON payloads → pass/reject. Prior art: `tests/test_attribute_gating.py`.

2. **`write_back_job_evaluation` / `collect_batch_results`** — mock matcher JSONL; assert **Role-filtered Job** vs attribute-filtered vs matched; dual-fail counts only as role-filtered; Unclassified fallback does not role-filter. Prior art: `tests/test_batch_poller.py`.

3. **Chunk and round log lines + CLI footer** — `role-filtered` in the same summary strings as today. Prior art: `tests/test_batch_poller.py`, `tests/test_collect_cli.py`, `tests/test_log_stream.py`.

4. **Reassess pipeline** — current settings query; demote Scraped/Matched; leave Accepted+ in lane. Prior art: existing reassess tests around `src/pipelines.py`.

5. **Batch submit snapshot** — created **Batch Evaluation Job** stores the query; batch JSONL / prompt builder receives that query. Prior art: batch evaluation submit tests.

6. **Kanban wiring** — API job payload with Role-filtered flag renders badge-row pill and drawer Job Info row; no banner. Prior art: `tests/test_dashboard_modules.py` / `tests/kanban_js.py`.

**New cases:**

- `roleRelevant: false` → **Rejected**, role-filtered +1, pill flag set.
- `true` / `null` / omitted / junk → attribute gate runs as today.
- Empty stored query → pass Role Relevance.
- `mock_eval` does not role-filter.
- Prompt includes search query and translation/family rules (string contract test, not a live model).

No Playwright/browser E2E required for this spec. Manual QA below is enough for the pill and drawer.

## Out of Scope

- Drop-before-save title, keyword, or vendor job-function filters.
- A Target Role field in Job Search Settings.
- Auto-**Reject** on low **Resume Matcher** score.
- Using the **Active Resume Profile** as the role target.
- Per-job original-query history across mixed searches.
- Shipping or productizing `/prototype/role-reject-copy`.
- Changing scrape post-filters (company size, Employment Type) or **Board Controls**.
- Wiring `reject_unrelated.py` into search / poller.
- A second Gemini call only for Role Relevance.
- Recruiter-style banners, title strips, or Job Activity Log heroes for Role-filtered.
- Per-job Task Log lines for Role Relevance rejects.

## Further Notes

- Wayfinder map: `.scratch/role-relevance/MAP.md`. Verdict prototype (query `QA`): developer `false`/reject; QA and SDET `true`/pass; thin `null`/pass.
- UI prototype verdict (2026-09-05): variant A — badge-row pill + drawer Job Info row.
- Extends ADR 0008 / ADR 0010: still one matcher JSON object; gating stays post-matcher in the **Batch Poller** write-back.
- Example Task Log shape after this spec:

  ```
  Batch chunk completed: 90 matched, 3 attribute-filtered, 5 role-filtered, 1 fallback-rejected, 0 failed, 1 unclassified
  Evaluation round complete (search): 90 matched, 3 attribute-filtered, 5 role-filtered, 1 fallback-rejected, 0 failed, 1 unclassified
  ```
