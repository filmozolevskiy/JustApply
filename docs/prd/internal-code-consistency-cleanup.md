# [PRD] Internal Code Consistency Cleanup

> **GitHub Issue:** [#115](https://github.com/filmozolevskiy/JustApply/issues/115)

## Problem Statement

The codebase carries legacy facades, unused helpers, duplicated parsing logic, scattered environment loading, deprecated asyncio APIs, and commented-out scraper filters. These do not usually break user flows but increase agent confusion, warning noise, and the cost of safe refactors.

## Solution

Remove or consolidate dead and duplicate code paths, centralize configuration loading where practical, and align async logging helpers on one implementation — without changing **Search & Evaluation Pipeline** filtering behavior visible to users today.

## User Stories

1. As a maintainer, I want unused CLI resume-name helpers removed, so that search resume selection is obvious (`general_cv.md` / Profile Manager).

2. As a maintainer, I want the legacy outreach facade removed or clearly deprecated once callers use enrichment modules, so that import paths are single.

3. As a maintainer, I want duplicate activity-log parsing logic in one place, so that JSON log shape changes happen once.

4. As a maintainer, I want scraper post-filters either enabled with tests or deleted (not left commented), so that intent is clear.

5. As a maintainer, I want `inspect.iscoroutinefunction` used consistently for log callbacks, so that Python 3.14+ deprecation warnings disappear from test runs.

6. As a maintainer, I want `load_dotenv` centralized or documented as intentional per-module, so that env loading is predictable.

7. As a maintainer, I want legacy DB `start_enrichment` removed after coordinator migration, so that enrichment status transitions have one owner.

8. As a contributor, I want `--sites` CLI flag removed or implemented, so that argparse help is truthful.

9. As a maintainer, I want hardcoded cost constants documented next to ADR spend rules, so that Bright Data and Apify estimates stay explainable.

10. As a maintainer, I want duplicate MODEL_NAME constants absent, so that Gemini model selection is configured in one client module.

11. As an agent, I want grep for TODO/FIXME replaced by tracked issues where needed, so that debt is visible on the board.

12. As a maintainer, I want weak `Contact` schema extras retained only if required for forward-compatible contact payloads, or tightened with tests, so that validation matches persisted JSON.

13. As a maintainer, I want service docstrings to use **Scraped**/**Matched**/**Accepted** terms, so that code comments match `CONTEXT.md`.

14. As a maintainer, I want pytest collection free of `sys.path.insert` in every test module if packaging fix lands, so that tests import like production.

## Implementation Decisions

- Delete unused `_resume_name_for_position` and dead commented scraper title/timezone filters unless product re-enables them with ADR + tests.
- Consolidate `_parse_activity_log` into job model layer; DB layer calls shared helper.
- Replace `asyncio.iscoroutinefunction` in scraper with `inspect.iscoroutinefunction` matching pipelines/enrichment.
- Remove `src/core/outreach.py` facade after updating imports to `core.enrichment` (or keep thin re-export with deprecation comment one release — prefer removal if test grep shows no production imports).
- Remove DB `start_enrichment` export if coordinator `begin_enrichment` is sole API; update `db.__init__` exports.
- Centralize env loading in CLI entry and web startup; modules read `os.environ` without repeated `load_dotenv()` where startup already loaded `.env`.
- Document `COST_PER_APIFY_RUN` and Bright Data per-record constants adjacent to spend confirmation logic; no user-facing price change in this PRD.
- `--sites`: remove from CLI if still unused, or wire to scraper if quick — default removal unless product needs multi-site.
- **Contact** model: keep `extra="allow"` if Apify payloads require unknown fields; add test fixture documenting allowed extensions.

## Testing Decisions

- Full pytest suite must pass; no behavior change assertions except warning count reduction.
- If commented scraper filters are removed, add no new user-visible filtering tests (behavior unchanged).
- If filters are re-enabled, add scraper tests for keyword/timezone gating per product decision recorded in Implementation.
- **Prior art:** scraper tests, job model tests, CLI tests, import smoke tests.

## QA Validation

- [ ] Run `python3 -m src.cli --search "QA"` with valid env → search completes and **Scraped Jobs** appear on dashboard.
- [ ] Run enrichment from dashboard on an **Accepted Job** → contacts/templates behave as before cleanup.
- [ ] Run full pytest locally → pass with fewer deprecation warnings than before (visible in CI log summary).

## Out of Scope

- Feature work on scraper keyword/timezone filters (only delete or fully restore with spec).
- Package publishing to PyPI (may overlap Dashboard Maintainability / Tooling PRDs).
- Large refactors of enrichment LLM prompts or matcher batch logic.

## Further Notes

This PRD bundles low-risk hygiene items from the audit that are independent of user-facing features. Ship after or in parallel with **Enrichment Pipeline Hardening** if coordinator API removal conflicts — coordinate ordering so enrichment tests stay green.
