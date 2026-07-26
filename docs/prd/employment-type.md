# [PRD] Employment Type

> **GitHub Issue:** [#170](https://github.com/filmozolevskiy/JustApply/issues/170)

## Problem Statement

Job seekers cannot filter LinkedIn listings by hiring arrangement (Full-time, Contract, Part-time, Temporary, Volunteer). The **Kanban Dashboard** has no **Employment Type** on cards or in **Board Controls**, Job Search Settings cannot prefer types at scrape time, and the **Resume Matcher** / attribute gate ignore Employment Type even though Bright Data returns `job_employment_type` and accepts a `job_type` scrape input. Contract and Full-time roles mix in the same lanes with no refine or Reject path.

## Solution

Add **Employment Type** end-to-end: store the scrape-time value from the **LinkedIn Scraper API**, let Job Search Settings select one or more types (default none = “any”), pass Bright Data `job_type` only when exactly one type is selected, post-filter raw results when any preference is active, have the **Resume Matcher** own the stored value after evaluation (matcher wins, scraper fallback / **Unclassified**), attribute-gate search/backfill/**Reassess** when prefs are set, multi-select refine in **Board Controls**, and show the type in drawer Job Info. Dashboard-only preferences in v1; CLI treats Employment Type as “any”. See ADR 0013 and `CONTEXT.md`.

## User Stories

1. As a job seeker, I want Job Search Settings checkboxes for Full-time, Contract, Part-time, Temporary, and Volunteer, so that I can prefer hiring arrangements before a scrape.

2. As a job seeker, I want Employment Type defaults to none checked (“any”), so that a new scrape is not narrowed until I choose.

3. As a job seeker, I want selecting exactly one Employment Type to send that value to Bright Data as `job_type`, so that discovery prefers that arrangement and saves credits when the filter hits.

4. As a job seeker, I want selecting more than one Employment Type to omit Bright Data `job_type` and post-filter results to my selected set, so that multi-select works without fan-out credit multiplication.

5. As a job seeker, I want “any” (none checked) to omit Bright Data `job_type` and not post-filter by Employment Type, so that all arrangements can be saved.

6. As a job seeker, I want scrape post-filter to drop Bright Data mismatch/error rows and unknown/blank Employment Types when any preference is active, so that unclassifiable listings do not enter **Scraped**.

7. As a job seeker, I want every saved job to store Employment Type from scrape when present, so that the board and drawer can use it before evaluation finishes.

8. As a job seeker, I want the **Resume Matcher** to classify Employment Type and overwrite the stored value, so that listing text can correct scrape mistakes (same matcher-wins pattern as remote type and seniority).

9. As a job seeker, I want Unclassified poison fallback to keep scraper Employment Type when the matcher never returns a valid result, so that the gate and drawer still have a value.

10. As a job seeker, I want jobs whose matcher Employment Type is outside the run’s selected types to become **Attribute-filtered Jobs** and move to **Rejected**, so that soft scrape prefs are enforced after evaluation.

11. As a job seeker, I want “any” Employment Type prefs to skip Employment Type in the attribute gate, so that only remote/seniority (and other gates) apply.

12. As a job seeker, I want search-run Employment Type prefs persisted on the **Batch Evaluation Job**, so that the **Batch Poller** gates with the prefs from submit time.

13. As a job seeker, I want backfill on the dashboard to use current Job Search Settings Employment Type prefs for the attribute gate, so that unevaluated **Scraped Jobs** respect my current preferences.

14. As a job seeker, I want **Reassess** to refresh Employment Type via the Resume Matcher using current Job Search Settings, so that I can correct classifications later.

15. As a job seeker, I want **Reassess** gate failure to Reject only from **Scraped** or **Matched**, so that **Accepted**, **Applied**, **Interviewing**, and **Rejected** jobs keep their lane while fields still update.

16. As a job seeker, I want **Board Controls** multi-select Employment Type refine (checkboxes), so that I can show any of several arrangements on the board.

17. As a job seeker, I want none checked on board Employment Type refine to mean no type filter, so that unknowns and all types remain visible.

18. As a job seeker, I want an active Employment Type refine to hide unknowns and jobs whose type is not checked, so that the board matches my triage focus.

19. As a job seeker, I want Employment Type refine to AND with search, favorites, remote, size, recruiter, and archived visibility, so that combined filters work like today.

20. As a job seeker, I want **Reset filters** to clear Employment Type refine (none checked) with other Board Controls defaults, so that one control restores the full board.

21. As a job seeker, I want Employment Type refine persisted in browser local storage across reloads, so that my board view survives refresh.

22. As a job seeker, I want drawer Job Info to show Employment Type beside seniority and remote policy when known, so that I can verify arrangement while reading a card.

23. As a job seeker, I want blank/unknown Employment Type shown as unknown (or omitted) in the drawer, so that missing data is not faked.

24. As a job seeker, I want no Employment Type badge on the Kanban card, so that card chrome stays uncluttered.

25. As a job seeker, I want drawer previous/next to follow the Employment Type–filtered visible set, so that navigation matches what I see.

26. As a job seeker, I want the generic empty-filters hint when Employment Type refine yields zero cards, so that empty state stays consistent.

27. As a job seeker, I want CLI `--search`, `--backfill`, and `--reassess` to treat Employment Type as “any” in v1, so that dashboard is the preference surface without new CLI flags.

28. As a maintainer, I want a versioned DB migration for Employment Type on jobs and search prefs on batch jobs, so that existing databases upgrade safely.

29. As a maintainer, I want mock scrape/eval paths to supply Employment Type where needed, so that local dashboard demos still exercise filters.

30. As a maintainer, I want domain language to say **Employment Type** (not “job type”), so that docs and UI match `CONTEXT.md` and ADR 0013.

31. As a job seeker, I want Job Search Settings Reset to restore Employment Type to none checked, so that scraper panel reset matches the “any” default.

32. As a job seeker, I want Spend Confirmation / scrape summary behavior unchanged except that filtered-out Employment Types never appear as saved cards, so that credit confirmation stays familiar.

33. As a job seeker, I want existing jobs without Employment Type to behave as unknown on the board until reassessed or left under “all” refine, so that rollout does not hide the whole board.

34. As a job seeker, I want attribute-gate Employment Type failures counted with other attribute-filtered totals in evaluation summaries, so that Task Logs stay coherent.

35. As a developer, I want Bright Data trigger payloads to include `job_type` only for the single-select case, so that multi-select and any stay credit-safe.

## Implementation Decisions

- Follow ADR 0013 and the **Employment Type** / **Reassess** / **Board Controls** / **Attribute-filtered Job** entries in `CONTEXT.md`.
- Persist Employment Type on the Job row; persist search-run Employment Type preferences on the Batch Evaluation Job alongside remote/seniority prefs.
- Scraper normalize maps Bright Data `job_employment_type` into the Job field; skip error/mismatch snapshot rows; post-filter when any preference is active; set Bright Data input `job_type` only when exactly one type is selected.
- Allowed values for UI and gate: Full-time, Contract, Part-time, Temporary, Volunteer (Bright Data–confirmed). Reject Internship/Other as scrape inputs.
- Extend Resume Matcher JSON with Employment Type; merge via existing attribute merge (matcher wins, per-field scraper fallback); extend `passes_attribute_gate` so Employment Type applies only when prefs are not “any”.
- Batch Poller reads persisted Employment Type prefs and Rejects attribute mismatches to **Rejected** (same family as remote/seniority).
- Dashboard Job Search Settings: multi checkbox group, default none; include in search/backfill submit payload.
- Board Controls Refine board: multi-select Employment Type; none = no refine; persist in local storage; include in Reset filters.
- Drawer Job Info: display Employment Type; no card badge.
- Reassess: apply Job Search Settings gate; demote to Rejected only from Scraped/Matched; Accepted+ keep lane, update fields.
- CLI v1: no Employment Type flags; always “any” for that dimension.
- Unknown: empty/missing field; drop on scrape post-filter when prefs active; hide on board when any refine checkbox is active.

## Testing Decisions

- Prefer external behavior: saved jobs, lane outcomes, filter visibility, API/drawer fields, Bright Data payload shape — not private helpers unless they are the established seam.
- Seams (confirmed):
  1. Scraper normalize / post-filter / trigger payload (`tests/test_scraper.py`)
  2. Attribute merge and gate (`tests/test_attribute_gating.py`)
  3. Batch poller write-back and Reject (`tests/test_batch_poller.py`)
  4. Reassess lane rules (`tests/test_reassess.py`)
  5. Board `filterJobs` multi-select (`tests/test_dashboard_modules.py`)
  6. Dashboard chrome + Job Search Settings payload (`tests/test_dashboard_panel_chrome.py` and settings tests)
  7. Job schema / API round-trip (existing job CRUD / dashboard jobs tests)
- Prior art: remote/seniority attribute gating, company-size post-filter, Board Controls filterJobs tests, batch poller attribute reject tests, reassess pipeline tests.
- Good tests assert user-visible or API-contract outcomes (Employment Type on job, Matched vs Rejected, board filter pass/fail, `job_type` present/absent on trigger). Avoid brittle LLM prompt string snapshots unless necessary for matcher schema.

## QA Validation

- [ ] Open Job Search Settings → Employment Type checkboxes exist; all unchecked by default → scrape with “any” still saves jobs and stores Employment Type when Bright Data returns it.
- [ ] Check only Full-time → run a small scrape → new cards are Full-time (or fewer cards if mismatches dropped); drawer Job Info shows Full-time when present.
- [ ] Check Full-time and Contract → run scrape → no single-type-only surprise empty board solely from API fan-out; saved jobs are only those two types when post-filter applies.
- [ ] After evaluation with Full-time-only prefs, a job the matcher classifies as Contract moves to **Rejected** (attribute-filtered), not **Matched**.
- [ ] With Employment Type prefs none (“any”), evaluation does not Reject solely for Employment Type.
- [ ] Board Controls: check Contract only → only Contract cards visible; unknowns hidden; uncheck all → unknowns and all types visible again.
- [ ] Reset filters clears Employment Type refine with other Board Controls defaults.
- [ ] Drawer shows Employment Type in Job Info; Kanban card has no Employment Type badge.
- [ ] Reassess a **Matched** job that fails current Employment Type prefs → moves to **Rejected**.
- [ ] Reassess an **Accepted** job that fails current Employment Type prefs → stays **Accepted**; drawer Employment Type updates if matcher changed it.
- [ ] CLI `--backfill` / `--reassess` without dashboard prefs still runs (Employment Type treated as any); no new required CLI flags.

## Out of Scope

- CLI flags or shared persisted settings file for Employment Type (v1 dashboard-only prefs).
- Fan-out of one Bright Data input item per selected Employment Type.
- Kanban card Employment Type badge.
- Treating Internship / Other as valid Bright Data `job_type` inputs.
- Backfilling Employment Type for old jobs via a dedicated re-scrape job.
- Changing Spend Confirmation math beyond existing region × limit ceilings.
- Attribute gating changes unrelated to Employment Type (except Reassess adopting the gate for remote/seniority/Employment Type together from Job Search Settings).

## Further Notes

- Live Bright Data probes (Ontario) informed allowed values and discover-then-validate mismatch errors; keep skipping error rows in normalize/post-filter.
- Domain term is **Employment Type** — avoid “job type” in UI copy.
- ADR: `docs/adr/0013-employment-type-scrape-and-matcher-gate.md`.
