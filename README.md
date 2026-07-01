# JustApply 🚀

### Overview
JustApply is an AI-powered job search and application pipeline that automates the "manual" parts of hunting for roles. It scrapes LinkedIn job listings, scores them against your resume using Gemini, and enriches leads with recruiter contacts. Stop wasting time on low-match roles and start applying where it counts.

### Details
- **Kanban Tracking**: Manage your application lifecycle in a modern web dashboard with refined board controls and search.
  ![Kanban Tracking](images/kanban.gif)
- **AI Automated Scraping + Match Scoring**: Automatically evaluate job descriptions against your experience to generate a match score and summary. 
  ![AI Automated Scraping + Match Scoring](images/search.gif)
- **Smart Enrichment + Outreach & Cache**: Finds hiring managers and recruiters using Apify, featuring specialized filters for HR or specific languages (e.g., Russian-only). 
  ![Smart Enrichment + Outreach & Cache](images/enriching.gif)
- **Cost Controls**: Built-in warnings for paid Apify actions. It asks before spending your lunch money on contact scraping.
  ![Cost Controls](images/cost_control.png)

### How it Works
JustApply uses **FastAPI** for the backend and **Gemini** for intelligent job assessment. It leverages **Bright Data** for resilient scraping and **Apify** for contact discovery. Data is stored locally in `data/just_apply.db` (SQLite) to keep your search private and persistent.

For domain terminology — Kanban lanes, pipeline stages, batch evaluation, enrichment — see [`CONTEXT.md`](CONTEXT.md).

### Setup

All commands below must be run from the **repo root** with the project virtualenv active.

1. **Clone and install**:
   ```bash
   git clone https://github.com/filmozolevskiy/JustApply.git
   cd JustApply

   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate

   pip install -r requirements.txt
   ```
2. **Environment**:
   ```bash
   cp .env.example .env
   ```
   Fill in at least:
   - `GEMINI_API_KEY` — resume matching and outreach
   - `BRIGHTDATA_API_KEY` and `BRIGHTDATA_JOB_SCRAPER_ID` — job scraping
   - `APIFY_API_TOKEN` — contact enrichment

   See `.env.example` for the full list.
3. **Run dashboard**:
   ```bash
   python3 -m src.web.run_dashboard
   ```
   Open http://127.0.0.1:8000
4. **Run CLI** (same shell — repo root + venv active):
   ```bash
   python3 -m src.cli --search "Data Engineer"
   python3 -m src.cli --promote
   ```

**Troubleshooting:** If you see `No module named 'src'` or `requirements.txt` not found, you are not in the repo directory or you activated the wrong venv. Run `cd` into the clone, then `source .venv/bin/activate`. Confirm with `which python3` — it should point to `.venv/bin/python3` inside the repo.

### Repo Layout
```text
.
├── CONTEXT.md         # Domain glossary (lanes, pipelines, batch evaluation)
├── data/              # Runtime SQLite db (just_apply.db) and logs
├── images/            # README screenshots and GIFs
├── resumes/           # Resume Profiles (.md only)
├── src/
│   ├── pipelines.py   # Search & Evaluation Pipeline, backfill, enrichment orchestration
│   ├── cli/           # CLI entry points (python3 -m src.cli)
│   ├── service/       # run_search, run_promote, run_backfill, run_collect
│   ├── core/
│   │   ├── batch_evaluation.py  # Gemini Batch API submissions
│   │   ├── batch_poller.py      # Poll in-flight batches, write scores back
│   │   ├── evaluation_lock.py   # Blocks overlapping search/backfill rounds
│   │   ├── matcher.py           # Resume Matcher LLM
│   │   ├── scraper.py           # Bright Data LinkedIn scraper
│   │   └── enrichment/          # Contact Sample, classification, outreach templates
│   ├── db/            # Job Tracker Database (SQLite jobs table)
│   ├── safety/        # Database Safety Gate (blocks destructive DB ops)
│   └── web/
│       ├── server.py            # FastAPI backend
│       ├── dashboard.html       # Kanban board UI
│       └── static/js/           # jobStore, boardRenderer, drawerController, taskLogClient
├── tests/
├── .env.example
└── requirements.txt
```
