# JustApply

## What

JustApply is a local tool that finds jobs, scores them against your resume, finds LinkedIn contacts, and tracks applications on a Kanban board.

No LinkedIn account is needed. Job and contact data is fetched through third-party APIs — your personal LinkedIn login is never used.

## Why

This repo automates job search, contacting people, and tracking positions so you can focus on applying and interviewing.

## How

### 1. Setup

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Fill in API keys in `.env` (see `.env.example` for variable names).

**API keys you need:**

- **Gemini** (`GEMINI_API_KEY`) — scores jobs and writes outreach messages
- **Bright Data** (`BRIGHTDATA_API_KEY`, `BRIGHTDATA_JOB_SCRAPER_ID`) — scrapes LinkedIn job listings
- **Apify** (`APIFY_API_TOKEN`) — finds company contacts for outreach

### 2. Launch

```bash
python3 -m src.web.run_dashboard
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

### 3. Run the pipeline

Use the **Kanban Dashboard** UI and/or the **JustApply** agent skill ([`.claude/skills/just-apply/SKILL.md`](.claude/skills/just-apply/SKILL.md)) to search jobs, enrich contacts, and move cards through lanes.

---

## For developers

- Domain terms → [`CONTEXT.md`](CONTEXT.md)
- Project rules → [`CLAUDE.md`](CLAUDE.md)
- Tests → `pytest tests/`
