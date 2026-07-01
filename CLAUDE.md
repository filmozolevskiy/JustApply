# Project setup

Dedicated repository for the **JustApply** skill. Automates job search, resume matching, personalized outreach, and application tracking.

## CLI & Run Commands


| Command                                    | Action                                                                                                            |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| `python3 -m src.cli --search "<position>"` | Run the **Search & Evaluation Pipeline** — scrape listings, save to **Scraped**, submit **Batch Evaluation Jobs** |
| `python3 -m src.cli --promote`             | **Enrichment** for **Matched**/**Accepted** jobs — Contact Sample, classification, outreach templates             |
| `python3 -m src.cli --backfill`            | Submit batch evaluation for **Scraped** jobs missing scores (add `--wait` to block until batches finish)          |
| `python3 -m src.cli --collect`             | Poll in-flight **Batch Evaluation Jobs** once and write back completed results (add `--wait` to block)            |
| `python3 -m src.cli --reassess <job_id>`   | Re-run **Resume Matcher** on a single job                                                                         |
| `python3 -m src.cli --reassess-all`        | Re-run **Resume Matcher** on all active jobs                                                                      |
| `python3 -m src.web.run_dashboard`         | Launch local FastAPI **Kanban Dashboard**                                                                         |

## Quality checks

Install dev extras first (see README setup): `pip install -e ".[dev]"`. From the repo root with that venv active, run the same gates as CI (`.github/workflows/ci.yml`):

```bash
ruff check src tests
mypy
pytest tests/ --cov=src --cov-report=term-missing
```

| Command | Action |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| `ruff check src tests` | Lint Python under `src/` and `tests/` (`[tool.ruff]` in `pyproject.toml`) |
| `mypy` | Type-check core packages (`src/db`, `src/schemas`, `src/service`; `[tool.mypy]` in `pyproject.toml`) |
| `pytest tests/ --cov=src --cov-report=term-missing` | Full test suite with coverage gate on `src/` Python (≥84%; `[tool.coverage.report]` in `pyproject.toml`) |

For a quick test-only iteration, `pytest tests/` is fine; before claiming Python work complete, run all three commands above.

## Constitution



### Role

You are a software engineer working on the JustApply automation system.

### MUST

1. **Writing style**: Plain ESL-friendly language, short sentences. Lead with the answer.
2. **Evidence**: Factual claims about code require concrete file paths, line ranges, or test outputs.
3. **Data Schemas**: Keep schema fields strictly aligned with `CONTEXT.md` and the single `jobs` table in the **Job Tracker Database** (`src/schemas.py` `Job` model, `src/db/jobs.py` CRUD). There is no separate Applications table.



### Legacy status names (migration only)

Older docs used **Found**, **Sourced**, **Enriching**, and **Enriched** lanes. The active Kanban lanes are **Scraped → Matched → Accepted → Applied → Interviewing → Rejected**. Use legacy names only when handling read-time migrations in `src/db/job_model.py`.

---



## AI workflow

1. **Read this file** — always in context.
2. **Use skills when present** — read `.claude/skills/just-apply/SKILL.md` before starting tasks.
3. **Verify before claiming done** — on Python changes, run the full quality gate suite (`ruff check src tests`, `mypy`, `pytest tests/ --cov=src --cov-report=term-missing`); do not stop after pytest alone. Requires dev install (`pip install -e ".[dev]"`, see README).

---



## Project structure

```text
CLAUDE.md                    # Project rules
CONTEXT.md                   # Domain glossary (authoritative lane and pipeline terms)
data/                        # Runtime artifacts (just_apply.db, logs)
resumes/                     # Resume Profiles (.md only)
src/
├── pipelines.py             # Search, backfill, enrichment orchestration
├── schemas.py               # Pydantic Job, Contact, OutreachSettings models
├── rate_limiter.py          # Scrape trigger rate limiting
├── cli/                     # CLI package (entry: python3 -m src.cli)
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py               # CLI flags and dispatch
│   └── gemini_agent.py      # Standalone Gemini prompt helper
├── service/                 # Application orchestration for CLI + dashboard
│   ├── __init__.py
│   └── just_apply.py        # run_search, run_promote, run_backfill, run_collect
├── db/                      # Job Tracker Database (SQLite jobs table)
│   ├── __init__.py          # Re-exports full public API
│   ├── connection.py        # DB_PATH, get_db_connection, init_db
│   ├── jobs.py              # CRUD for the jobs table
│   ├── job_model.py         # Read-time migration and Job normalization
│   ├── batch_jobs.py        # Persisted Batch Evaluation Job records
│   ├── cache.py             # Contact Sample Cache
│   ├── contacted_elsewhere.py
│   ├── settings.py
│   └── seed.py              # Seed data for local development
├── core/                    # Domain modules
│   ├── batch_evaluation.py  # Gemini Batch API submissions
│   ├── batch_poller.py      # Poll in-flight batches, write scores back
│   ├── evaluation_lock.py   # Blocks overlapping search/backfill rounds
│   ├── matcher.py           # Resume Matcher LLM
│   ├── scraper.py           # Bright Data LinkedIn scraper
│   ├── outreach.py
│   ├── attribute_gating.py
│   ├── gemini_client.py
│   ├── regions.py
│   ├── pre_evaluation/      # Pre-batch attribute helpers
│   └── enrichment/          # Contact Sample, classification, templates
│       ├── contact_sample.py
│       ├── classifier.py
│       ├── connection_note.py
│       ├── coordinator.py
│       └── source.py
├── safety/                  # Database Safety Gate
│   ├── __init__.py
│   ├── gate.py              # Blocks destructive DB operations
│   └── snapshot.py          # Pre-run database snapshots
└── web/                     # HTTP layer (entry: python3 -m src.web.run_dashboard)
    ├── __init__.py
    ├── server.py            # FastAPI backend endpoints
    ├── run_dashboard.py     # Launches local FastAPI server
    ├── dashboard.html       # Kanban board UI
    └── static/js/           # jobStore, boardRenderer, drawerController, taskLogClient
tests/                       # Pytest unit and integration tests
.claude/
├── settings.json            # MCP server configuration
└── skills/
    └── just-apply/SKILL.md  # JustApply agent skill guides
```

