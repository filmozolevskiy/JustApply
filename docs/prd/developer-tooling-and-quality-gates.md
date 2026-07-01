# [PRD] Developer Tooling and Quality Gates

> **GitHub Issue:** [#111](https://github.com/filmozolevskiy/JustApply/issues/111)

## Problem Statement

Contributors and agents working on JustApply cannot reproduce the same dependency set across machines, lack automated lint/type/coverage gates, and mix runtime and dev dependencies in one flat requirements file. Regressions in style, typing, and untested modules are caught only at manual pytest time — if at all.

## Solution

Introduce standard Python project metadata with pinned dependencies, separate dev extras, and CI-friendly quality commands (lint, format check, type check, coverage threshold) that run locally and in automation without changing runtime behavior of the **Kanban Dashboard** or CLI.

## User Stories

1. As a contributor, I want a single documented install command for runtime deps, so that I can run the dashboard and CLI reliably.

2. As a contributor, I want a documented dev install that includes pytest and quality tools, so that I do not pollute minimal deployments.

3. As a maintainer, I want dependency versions pinned or locked, so that CI and local runs match.

4. As a maintainer, I want `ruff` (or equivalent) to enforce consistent Python style, so that reviews focus on behavior.

5. As a maintainer, I want optional `mypy` (or partial typing gates) on core packages, so that public APIs stay typed.

6. As a maintainer, I want coverage reporting with a modest threshold on `src/`, so that new modules do not land untested.

7. As an agent, I want `pytest`, lint, and type commands documented in project rules, so that verification is repeatable.

8. As a contributor, I want CI to fail on lint or test failures, so that broken main is rare.

9. As a maintainer, I want the Gemini SDK dependency (`google-genai`) version constrained intentionally, so that SDK upgrades are deliberate.

10. As a contributor, I want FastAPI form/file dependencies declared for tests that import the app, so that collection errors do not depend on accidental local installs.

11. As a maintainer, I want a lock file or constrained ranges policy documented, so that security patches are applied predictably.

12. As a contributor, I want quality commands to run in under a few minutes on laptop hardware, so that the loop stays usable.

13. As a maintainer, I want HTML dashboard assets excluded from Python coverage thresholds, so that metrics reflect testable backend logic.

14. As a contributor, I want README setup steps to reference the new install flow, so that onboarding matches reality.

## Implementation Decisions

- Add `pyproject.toml` as the canonical project metadata source; migrate dependency declarations from flat `requirements.txt` (may keep a generated or re-exported requirements file for backward compatibility if needed).
- Split dependencies: runtime (FastAPI, uvicorn, google-genai, httpx, pydantic, sse-starlette, python-dotenv, python-multipart, watchfiles) vs dev (pytest, pytest-asyncio, pytest-cov, ruff, mypy).
- Pin or lock versions per team policy (exact pins or upper-bounded compatible releases — document choice in Further Notes).
- Add `ruff` configuration aligned with existing code style (line length, import order) — minimal rule churn on first pass; fix only auto-safe issues or scope initial enablement to new changes if legacy noise is huge.
- Add `mypy` initially on selected packages (`src/db`, `src/schemas`, `src/service`) with pragmatic ignores for third-party stubs.
- Add `pytest-cov` with threshold (~existing effective coverage on `src/` excluding HTML/JS static assets); fail CI below threshold.
- Document commands in project agent rules: `pytest tests/`, `ruff check`, `mypy`, `coverage report`.
- Ensure default venv install includes dev extras for contributors; CI installs dev group.
- Do not change application runtime behavior, API routes, or domain logic in this PRD.

## Testing Decisions

This PRD's deliverable is tooling; validation is meta:

- CI job (or documented local script) runs pytest + ruff + mypy + coverage and exits non-zero on failure.
- Fresh clone following README installs successfully and runs full test suite.
- **Prior art:** existing 800+ pytest tests; no new product tests required unless a thin smoke test ensures packaging imports work (`python -m src.cli --help`).

## QA Validation

- [ ] Clone repo on a clean machine, follow README install → `pytest tests/` passes.
- [ ] Run documented lint command → completes with exit code 0 on main after PR lands.
- [ ] Run documented type-check command → completes with exit code 0 on scoped packages.
- [ ] Run `python3 -m src.web.run_dashboard` → dashboard still opens at http://127.0.0.1:8000.

## Out of Scope

- Rewriting tests to increase coverage on HTML/JS (dashboard tests may remain string/HTTP based).
- Pre-commit hooks (optional follow-up).
- Publishing to PyPI as an installable package name (editable local install is enough).
- Docker or Railway deployment manifests.

## Further Notes

Audit found pytest mixed into runtime requirements and no coverage tooling — this PRD closes that gap. Prefer lock file (`uv lock` or pip-tools) if the maintainer already uses one elsewhere; otherwise document minimum compatible pins in `pyproject.toml`.
