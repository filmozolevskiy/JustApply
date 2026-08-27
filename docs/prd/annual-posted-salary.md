# [PRD] Annual Posted Salary

> **GitHub Issue:** [#171](https://github.com/filmozolevskiy/JustApply/issues/171)

## Problem Statement

Job seekers cannot compare or filter pay across listings. **Posted Salary** arrives as free text — hourly vs yearly, multi-location bands, mixed currencies — so the Kanban card, drawer, and Salary Min setting cannot treat pay as a comparable annual figure. Salary Min in Job Search Settings is cosmetic today: it does not drive scrape filtering or post-evaluation rejection.

## Solution

Normalize listing **Posted Salary** at **Resume Matcher** writeback into an **Annual Posted Salary** band (`annualMin` / `annualMax` + native currency) for the location matching the job's listing location. Show that annual band on Matched+ cards and the drawer. Apply **Salary Min** from Job Search Settings as a post-evaluation attribute gate (pass when `annualMax ≥ Min`; unknown pay passes). Keep the raw salary string stored; no FX conversion and no currency switcher in v1 (ADR 0014).

## User Stories

1. As a job seeker, I want **Posted Salary** extracted as structured facts by the **Resume Matcher**, so that hourly, monthly, and yearly listings can be compared after evaluation.
2. As a job seeker, I want code (not the LLM) to annualize those facts into an **Annual Posted Salary** band, so that hour→year math stays consistent and testable.
3. As a job seeker, I want a single posted figure stored as equal `annualMin` and `annualMax`, so that point salaries and bands share one shape.
4. As a job seeker, I want an hourly band converted using the listing's stated hours-per-week when present, otherwise 2,080 hours/year, so that full-time defaults are explicit.
5. As a job seeker, I want monthly amounts ×12 and daily amounts ×260 (unless the listing states otherwise), so that non-yearly periods still become annual.
6. As a job seeker, I want multi-location pay resolved to the band matching the job's listing `location`, so that the card pay matches where the role is posted.
7. As a job seeker, I want fallback to the first stated location band when no location matches, so that sparse or odd location labels still produce a band.
8. As a job seeker, I want **Annual Posted Salary** computed only at matcher writeback (not at scrape), so that I only care about comparable pay on evaluated jobs.
9. As a job seeker viewing a **Scraped** card, I want no salary line until evaluation finishes, so that I am not shown incomparable raw text as if it were annual.
10. As a job seeker viewing a **Matched** (or later) card, I want the annual band with currency on the card, so that I can triage pay at a glance.
11. As a job seeker in the job drawer, I want the same annual band (not the raw listing string), so that card and drawer stay consistent.
12. As a job seeker, I want equal min/max collapsed to one displayed number, so that point salaries read cleanly.
13. As a job seeker, I want the raw **Posted Salary** string still stored on the job, so that reassess and debugging can inspect the original text.
14. As a job seeker, I want **Salary Min** to stay in Job Search Settings as free text (e.g. `$120k`, `120000`), so that I do not relearn a new control.
15. As a job seeker, I want Salary Min parsed to an integer annual amount for the run, so that the gate can compare numbers.
16. As a job seeker, I want empty or unparseable Salary Min to disable the salary gate, so that a blank field does not reject everyone.
17. As a job seeker, I want Salary Min not to filter the Bright Data scrape, so that scrape spend and discoverability stay unchanged.
18. As a job seeker, I want Salary Min applied after evaluation as an attribute gate, so that underpaid roles become **Attribute-filtered Jobs** in **Rejected**.
19. As a job seeker, I want a job to pass the salary gate when `annualMax ≥ Salary Min`, so that a band that reaches my floor stays eligible (ADR 0014).
20. As a job seeker, I want jobs with no extractable Posted Salary to pass the salary gate, so that “pay not listed” roles are not mass-rejected.
21. As a job seeker, I want Salary Min compared as bare numbers across currencies, so that v1 needs no FX table or currency switcher (ADR 0014).
22. As a job seeker, I want Salary Min for a search/backfill round persisted on the **Batch Evaluation Job** like remote/seniority prefs, so that writeback uses the prefs from submit time.
23. As a job seeker, I want salary gate failures counted with other **Attribute-filtered Jobs** in **Task Logs**, so that evaluation summaries stay coherent.
24. As a job seeker with existing Matched cards that only have free-text salary, I want forward-only behavior (no migration parser, no forced reassess-all), so that I am not surprised by a Gemini bill or brittle regex backfill.
25. As a job seeker who runs `--reassess` / `--reassess-all`, I want those jobs to get structured facts and an annual band on the next writeback, so that I can opt in to backfill.
26. As a job seeker, I want Glassdoor **Company Research** salary left unchanged, so that employer medians stay separate from listing **Posted Salary**.
27. As a job seeker, I want **Enrichment** (contacts/outreach) unchanged by this work, so that pay normalization is not confused with contact enrichment.
28. As a maintainer, I want domain terms **Posted Salary**, **Annual Posted Salary**, and **Salary Min** used in docs and UI copy, so that language stays aligned with CONTEXT.md and ADR 0014.

## Implementation Decisions

- Extend the **Resume Matcher** JSON contract: replace free-text-only `salary` extraction with structured **Posted Salary** facts (amounts, pay period, currency, optional location-tagged bands, optional hours-per-week). Still persist a human-readable raw salary string on the job for audit.
- Add a pure annualizer module: structured facts + job `location` → `annualMin`, `annualMax`, currency. Location match → else first band. Hourly: stated hours/week or 2080; monthly ×12; daily ×260 unless overridden.
- Add a Salary Min parser: free-text settings → optional integer annual minimum; empty/invalid → gate disabled.
- Extend attribute gating to accept optional annual band + Salary Min; pass when Min unset, band missing, or `annualMax ≥ Min`; fail otherwise. Include salary in attribute-mismatch Task Log reasons when relevant.
- Persist parsed Salary Min on each **Batch Evaluation Job** at submit (search/backfill), alongside existing search remote/seniority (and Employment Type) preferences; **Batch Poller** writeback reads it for the gate.
- Schema: keep existing text `salary`; add nullable numeric annual fields + currency (or equivalent structured storage on the job). No delete of the free-text column.
- Dashboard: Matched+ card and drawer render annual band only (collapse equal ends); Scraped shows no salary line. Do not surface raw string in UI once a band exists.
- Job Search Settings: keep Salary Min field; improve placeholder/help to annual examples; parse client-side or server-side before storing on the batch — scrape path ignores salary for Bright Data filtering.
- Forward-only for existing rows; reassess paths reuse the new matcher + annualizer + gate.
- Follow ADR 0014: no FX, no currency switcher, gate on `annualMax`, currency-agnostic compare.

## Testing Decisions

- Good tests assert external behavior: annualizer outputs, gate pass/fail, poller lane outcomes, rendered UI strings — not private helper names or prompt wording trivia.
- **Annualizer** — unit tests for period conversion, hours override, location pick, point→equal band. New focused test module preferred.
- **Salary Min parser** — unit tests for `$120k`, `120,000`, empty, garbage.
- **Attribute gate** — extend `tests/test_attribute_gating.py` for salary cases (annualMax threshold, unknown pay, disabled Min, currency-agnostic).
- **Batch poller writeback** — extend poller tests: structured evaluation → annual fields written; salary gate → Rejected vs Matched; Min persisted on batch row. Prior art: `tests/test_batch_poller.py`, employment-type gate tests.
- **Matcher contract** — update `tests/test_matcher.py` mocks to structured salary facts; assert annualizer/writeback path receives them.
- **Dashboard modules** — assert Matched card/drawer salary markup uses annual band; Scraped omits salary line. Prior art: dashboard HTML/JS module tests.
- Do not require live Gemini or Bright Data for these seams.

## QA Validation

- [ ] Run a search with Salary Min empty and mock/real eval producing yearly pay → Matched card shows an annual band with currency (not `$70/hr` raw).
- [ ] Run a search with Salary Min like `$120k` and a job whose annual band top is below 120000 → job lands in **Rejected** (attribute-filtered), not **Matched**.
- [ ] Same Min with a job band `100k–130k` → job can land in **Matched** (annualMax reaches Min).
- [ ] Listing with no pay mentioned + Salary Min set → job can still reach **Matched** if other gates pass.
- [ ] Hourly listing (e.g. `$70–80/hr`) after eval → card shows annualized band, not hourly text.
- [ ] Multi-location pay text where one location matches the job location → displayed band matches that location.
- [ ] Open drawer on a Matched job with a band → drawer salary matches the card annual display; raw string not shown as the primary salary line.
- [ ] Scraped lane card before eval finishes → no salary line on the card.
- [ ] Existing pre-feature Matched job still on board without reassess → still usable; annual display/gating appears only after reassess or new eval (forward-only).
- [ ] Confirm Glassdoor **Company Research** salary row still works independently of listing annual band.

## Out of Scope

- Foreign-exchange conversion and any currency switcher / native-currency-only filter.
- Moving Salary Min into **Board Controls**.
- Scrape-time Bright Data salary filtering.
- Glassdoor **Company Research** salary changes.
- Migration script or forced reassess-all to backfill old free-text salaries.
- Treating Salary Min as Enrichment or bundling pay work into contact enrichment.
- Daily/contract exotic calendars beyond the stated defaults (hours/week override, ×12, ×260).

## Further Notes

- Domain glossary: **Posted Salary**, **Annual Posted Salary**, **Salary Min** in CONTEXT.md.
- Decision record: ADR 0014 (gate on `annualMax`; currency-agnostic Min; no FX).
- Confirmed test seams: annualizer, Salary Min parser, attribute gate, batch poller writeback, matcher contract, dashboard display, Job Search Settings pass-through (scrape ignores salary).
