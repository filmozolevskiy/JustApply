# [PRD] Documentation and Domain Alignment

> **GitHub Issue:** [#112](https://github.com/filmozolevskiy/JustApply/issues/112)

## Problem Statement

Agent rules, skills, README layout, and ADR numbering drift from the live product: status lanes are **Scraped**/**Matched**/**Accepted**, env vars use `APIFY_API_TOKEN`, batch evaluation and **Evaluation Lock** exist, but `CLAUDE.md` still describes an older tree and "Applications" tables. Contributors and agents misconfigure env vars, use wrong vocabulary, and navigate the repo with stale maps.

## Solution

Synchronize all human-facing and agent-facing documentation with `CONTEXT.md` as the authoritative domain glossary. Fix env var names, project structure, CLI terminology, and ADR numbering so onboarding and agent workflows match production behavior.

## User Stories

1. As a new contributor, I want README setup env vars to match `.env.example`, so that copy-paste setup works.

2. As an agent, I want `CLAUDE.md` project structure to list pipelines, service, safety, schemas, batch evaluation, and enrichment modules, so that I edit the right files.

3. As an agent, I want skills to verify `APIFY_API_TOKEN` (not `APIFY_API_KEY`), so that enrichment is not misdiagnosed as missing credentials.

4. As a maintainer, I want ADR numbers to be unique, so that references like "ADR 0003" are unambiguous.

5. As a contributor, I want CLI command descriptions to use **Enrichment** language aligned with **Accepted Jobs**, so that `--promote` is understandable in domain terms.

6. As a contributor, I want README repo layout to mention batch poller, evaluation lock, and safety gate at a high level, so that architecture is discoverable.

7. As an agent, I want schema field guidance to reference the single `jobs` table / **Job Tracker Database**, not a separate Applications sheet, so that CRUD stays consistent.

8. As a maintainer, I want stale ADR env var names updated or footnoted, so that historical docs do not contradict `.env.example`.

9. As a contributor, I want `CONTEXT.md` cross-links from README for deep domain terms, so that I know where vocabulary is defined.

10. As an agent, I want skill preflight checks to list all required env vars with correct names, so that Bright Data, Apify, and Gemini failures are distinguishable.

11. As a maintainer, I want duplicate or superseded status names (`found`, `sourced`, `enriching`) documented only as migration history, not active lanes, so that new docs do not resurrect obsolete terms.

12. As a contributor, I want dashboard feature GIF paths and static asset paths in README to match actual locations, so that docs build trust.

13. As an agent, I want run commands table to mention batch backfill/collect if exposed in CLI, so that automation scripts use correct flags.

14. As a maintainer, I want each published PRD GitHub issue linked from its `docs/prd/` file, so that traceability matches prior PRDs.

## Implementation Decisions

- Treat `CONTEXT.md` as canonical for lane names, pipeline behavior, and glossary terms; propagate terminology outward — never the reverse.
- Update `CLAUDE.md`: project tree, CLI descriptions, schema note (jobs table only), verification steps unchanged.
- Update `.claude/skills/just-apply/SKILL.md` and `.cursor/skills/just-apply/SKILL.md` env var checklist to `GEMINI_API_KEY`, `BRIGHTDATA_API_KEY`, `BRIGHTDATA_JOB_SCRAPER_ID`, `APIFY_API_TOKEN`.
- Update README repo layout section to reflect major packages without turning into a full file listing.
- Renumber duplicate `docs/adr/0003-*` files — pick next free number for one ADR, update cross-references inside ADRs and PRDs.
- Add footnotes to older ADRs where historical env names differ (`APIFY_API_KEY` → `APIFY_API_TOKEN`) rather than rewriting history body text extensively.
- Align CLI help text for `--promote` with "enrich **Matched**/**Accepted** jobs" wording while keeping flag name for backward compatibility unless a separate alias PRD is opened.
- Do not change runtime code behavior in this PRD except CLI help strings if needed for accuracy.

## Testing Decisions

Documentation PRD — automated tests are optional smoke only:

- Grep/check script or CI doc lint (optional): fail if README mentions deprecated env var names.
- Manual review checklist in QA section is primary.
- **Prior art:** existing PRD files linking to GitHub issues; mirror that pattern for new PRDs.

## QA Validation

- [ ] Follow README setup using only documented env var names → `.env` matches what enrichment and scrape code expect.
- [ ] Read `CLAUDE.md` project tree → every top-level orchestration area referenced exists in the repo.
- [ ] Open `.claude/skills/just-apply/SKILL.md` → Apify token name matches `.env.example`.
- [ ] Search `docs/adr/` for duplicate numeric prefixes → each ADR number appears once.

## Out of Scope

- Writing a full CONTRIBUTING.md or architecture diagram deck.
- Rewriting all historical PRD/ADR bodies for lane renames already captured in `CONTEXT.md`.
- User-facing marketing copy beyond README accuracy fixes.

## Further Notes

README env vars were partially fixed since the original audit; remaining drift lives mainly in agent rules, skills, ADR 0002/0003 numbering, and `CLAUDE.md` structure. This PRD is safe to ship independently of code refactors.
