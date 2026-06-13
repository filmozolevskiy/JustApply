# Project setup

Dedicated repository for the **Job Hunter** skill. Automates job search, resume matching, personalized outreach, and application tracking.

## CLI & Run Commands

| Command | Action |
|:---|:---|
| `python3 -m src.cli --search "<position>"` | Search and evaluate jobs for a position (e.g. "QA", "Project/Delivery Manager") |
| `python3 -m src.cli --promote` | Sourced LinkedIn contacts, generate Cover Letters & promote to Applications |
| `python3 -m src.web.run_dashboard` | Launch local FastAPI Kanban Dashboard |
| `pytest tests/` | Run all unit and integration tests |

## Constitution

### Role
You are a software engineer working on the Job Hunter automation system.

### MUST
1. **Writing style**: Plain language, short sentences. Lead with the answer.
2. **Evidence**: Factual claims about code require concrete file paths, line ranges, or test outputs.
3. **Data Schemas**: Keep schema fields strictly aligned with `CONTEXT.md` (e.g. `Jobs` and `Applications` headers).

---

## AI workflow

1. **Read this file** — always in context.
2. **Use skills when present** — read `.claude/skills/job-hunter/SKILL.md` before starting tasks.
3. **Verify before claiming done** — run pytest and verify no regressions.

---

## Project structure

```text
CLAUDE.md                    # Project rules
CONTEXT.md                   # Job Hunter system architecture / context
data/                        # Runtime artifacts (job_tracker.db, logs)
src/
├── db/                      # Database package (Job Tracker Database operations)
│   ├── __init__.py          # Re-exports full public API
│   ├── connection.py        # DB_PATH, get_db_connection, init_db
│   ├── seed.py              # Seed data for local development
│   └── jobs.py              # CRUD operations for the jobs table
├── rate_limiter.py          # Scrape trigger rate limiting
├── cli/                     # CLI package (entry: python3 -m src.cli)
│   ├── __init__.py
│   ├── __main__.py
│   └── cli.py               # CLI implementation
├── web/                     # HTTP layer (entry: python3 -m src.web.run_dashboard)
│   ├── __init__.py
│   ├── server.py            # FastAPI backend endpoints
│   ├── run_dashboard.py     # Launches local FastAPI server
│   └── dashboard.html       # Kanban board UI
└── core/                    # Core modules (matcher, outreach, scraper)
tests/                       # Pytest unit and integration tests
.claude/
├── settings.json            # MCP server configuration
└── skills/
    └── job-hunter/SKILL.md  # Job Hunter agent skill guides
```
