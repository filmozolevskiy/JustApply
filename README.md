# Job Hunter Skill

This repository is dedicated to the **Job Hunting** system, which automates job search, resume matching, personalized candidate outreach, and application tracking.

## Workspace Layout

```text
CLAUDE.md                    # Project rules
CONTEXT.md                   # Job Hunter system architecture
job_hunter.py                # Main orchestrator CLI
scripts/
└── google_sheets_mcp.py     # Custom Google Sheets MCP Server
tests/
├── test_job_hunter.py       # Orchestrator CLI tests
└── test_google_sheets_mcp.py# Sheets MCP server tests
jobspy-mcp-server/           # Node.js JobSpy MCP server wrapper
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

### 2. Python Virtual Environment Setup
Create a virtual environment and install the required dependencies:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Google Sheets MCP Authentication
Make sure your Google Cloud Console `credentials.json` file is present in the root folder, then run the browser-based OAuth 2.0 flow to create `token.json`:
```bash
python3 scripts/google_sheets_mcp.py --auth
```

### 4. Jobspy MCP Node Server Setup
Install Node dependencies for the JobSpy MCP server:
```bash
cd jobspy-mcp-server
npm install
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

### Running Tests
Execute python unit and integration tests using pytest:
```bash
pytest tests/
```
