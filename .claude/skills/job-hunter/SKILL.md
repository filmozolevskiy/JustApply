---
name: job-hunter
description: Use this skill whenever the user mentions searching for jobs, matching or evaluating candidate resumes against jobs, searching company employees/recruiters, generating cover letters, promoting active applications in the SQLite database, or running the Job Hunter CLI (python3 -m src.cli).
---

# Job Hunter Automation Skill

This skill guides the agent in coordinating the end-to-end Job Hunter pipeline to search for jobs, match them against candidate resumes, update the local SQLite Job Tracker Database, and source referral contacts on LinkedIn to generate outreach.

## 1. Prerequisites Check

Before executing any commands, inspect the workspace and verify the environment:
- Verify that `GEMINI_API_KEY`, `BRIGHTDATA_API_KEY`, and `APIFY_API_KEY` are present in the `.env` file at the root. If not, prompt the user to add them.

## 2. Search & Evaluation Pipeline

When the user asks to find or search for positions (e.g. "search for QA jobs"):
1. Determine the target position name (e.g., "QA", "Project/Delivery Manager", "Data Analyst").
2. Run the orchestrator pipeline command:
   ```bash
   python3 -m src.cli --search "<position>"
   ```
3. Verify the CLI output. If successful, the job listings will be saved to the SQLite database (`data/job_tracker.db`) and visible in the local Kanban Dashboard.

## 3. Interactive Promotion & Outreach Pipeline

When matched jobs are in the database:
1. Sourced jobs will appear in the database with status `sourced`.
2. Sourced jobs with compatibility scores above the threshold and `shouldProceed=True` can be promoted to source company contacts and generate outreach letters by running:
   ```bash
   python3 -m src.cli --promote
   ```
3. Run the Kanban Dashboard locally by executing:
   ```bash
   python3 -m src.web.run_dashboard
   ```
4. Access the dashboard at `http://127.0.0.1:8000` to manage applications across status lanes (`Sourced`, `Evaluating`, `Applied`, `Contacted`, `Interviewing`, `Rejected`). Marking outreach contacts as contacted in the UI will automatically promote job status to `applied`.
