---
name: just-apply
description: Use this skill whenever the user mentions searching for jobs, matching or evaluating candidate resumes against jobs, searching company employees/recruiters, generating outreach templates, enriching Accepted Jobs in the Job Tracker Database, or running the JustApply CLI (python3 -m src.cli).
---

# JustApply Automation Skill

This skill guides the agent in coordinating the end-to-end JustApply pipeline to search for jobs, match them against candidate resumes, update the local SQLite Job Tracker Database, and source referral contacts on LinkedIn to generate outreach.

## 1. Prerequisites Check

Before executing any commands, inspect the workspace and verify the environment:
- Verify that `GEMINI_API_KEY`, `BRIGHTDATA_API_KEY`, `BRIGHTDATA_JOB_SCRAPER_ID`, and `APIFY_API_TOKEN` are present in the `.env` file at the root. If not, prompt the user to add them (names must match `.env.example`).

## 2. Search & Evaluation Pipeline

When the user asks to find or search for positions (e.g. "search for QA jobs"):
1. Determine the target position name (e.g., "QA", "Project/Delivery Manager", "Data Analyst").
2. Run the orchestrator pipeline command:
   ```bash
   python3 -m src.cli --search "<position>"
   ```
3. New listings land in the **Scraped** lane immediately after scrape. The **Batch Poller** evaluates them asynchronously and moves passing jobs to **Matched** (or **Rejected** on attribute-gate failure).
4. Verify the CLI output. Job listings are saved to the SQLite database (`data/just_apply.db`) and visible in the Kanban Dashboard.

## 3. Triage & Enrichment

Jobs move through **Scraped → Matched → Accepted**:
1. **Scraped** — unevaluated listings waiting for batch evaluation.
2. **Matched** — evaluated jobs with compatibility scores; triage here and drag to **Accepted** to pursue a role.
3. **Accepted** — jobs you are pursuing. Run **Enrichment** (Contact Sample + outreach templates) via the dashboard or CLI.

To enrich **Matched** or **Accepted** jobs ready for outreach from the CLI:
```bash
python3 -m src.cli --promote
```

Run the Kanban Dashboard locally:
```bash
python3 -m src.web.run_dashboard
```

Access the dashboard at `http://127.0.0.1:8000` to manage jobs across lanes: **Scraped**, **Matched**, **Accepted**, **Applied**, **Interviewing**, **Rejected**. Marking a contact's checkbox as contacted only updates that contact's flag — it does not change the job's lane. Use the **Mark Applied** button or drag a card to **Applied** to record that you applied.
