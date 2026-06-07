# Job Hunter Skill

This repository is dedicated to the **Job Hunting** system, which automates job search, resume matching, personalized candidate outreach, and application tracking.

## Workspace Layout

```text
CLAUDE.md                    # Project rules
CONTEXT.md                   # Job Hunter system architecture
job_hunter.py                # Thin CLI orchestrator launcher
src/
├── database.py              # SQLite database storage operations
├── run_dashboard.py         # Launches local FastAPI server
├── server.py                # FastAPI backend endpoints
├── cli.py                   # CLI implementation
├── dashboard.html           # Kanban board UI
└── core/                    # Core modules (matcher, outreach, scraper)
tests/                       # Pytest unit and integration tests
.claude/
├── settings.json            # MCP server configuration
└── skills/
    └── job-hunter/SKILL.md  # Job Hunter agent skill guides
```

## Setup Instructions

### 1. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```
Ensure you have:
* `GEMINI_API_KEY`: Required for resume evaluation and cover letter generation.
* `GITHUB_PERSONAL_ACCESS_TOKEN`: Required for git/issues integration.
* `BRIGHTDATA_API_KEY`: Required for job scraping.
* `APIFY_API_KEY`: Required for fallback outreach contact scraping.

### 2. Python Virtual Environment Setup
Create a virtual environment and install the required dependencies:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Running the Pipelines

### Job Search & Match
To search for jobs (e.g. "QA") and match them against your resume:
```bash
python3 job_hunter.py --search "QA"
```

### Candidate Outreach Promotion
To source contacts, generate cover letters, and promote marked jobs to the applications sheet:
```bash
python3 job_hunter.py --promote
```

### Launch Kanban Dashboard
To launch the local FastAPI dashboard:
```bash
python3 -m src.run_dashboard
```
Open `http://127.0.0.1:8000` in your web browser.

### Running Tests
Execute python unit and integration tests using pytest:
```bash
.venv/bin/pytest tests/
```
