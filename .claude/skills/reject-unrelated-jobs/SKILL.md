---
name: reject-unrelated-jobs
description: Use this skill whenever the user wants to clean up, filter, or reject jobs in the tracker database that are unrelated to AI, Data, QA, or PM fields. Trigger for requests like "clean up unrelated jobs", "reject non-tech jobs", "remove irrelevant roles", or when referencing the reject_unrelated.py script.
---

# Reject Unrelated Jobs Skill

This skill guides the agent in identifying and rejecting jobs in the tracker database that do not match the target fields (AI, Data, QA, PM) in both English and French.

## 1. How It Works
The skill leverages a helper script located at `.claude/skills/reject-unrelated-jobs/scripts/reject_unrelated.py` to query and scan the local database. It automatically filters out jobs using a predefined list of regex keywords with word boundaries:
- **QA / Quality Assurance** (QA, quality, quality assurance, test, testing, sdet, automation, automatique)
- **PM / Project Management** (project, projet, program, programme, delivery, scrum, product, produit, pm, chef de projet, gestionnaire)
- **Data / Analytics** (data, données, analyst, analyste, analytics, analytique, bi, business intelligence, sql, database, reporting)
- **AI / Machine Learning** (ai, ia, machine learning, ml, llm, deep learning, nlp, generative, générative)

## 2. Standard Workflow

Follow these steps when the user requests to filter out or reject unrelated jobs:

### Step 1: Scan for Unrelated Jobs
Run the helper script to scan the database and see the candidate list.
By default, the script scans only jobs in the `sourced` status lane:
```bash
python3 .claude/skills/reject-unrelated-jobs/scripts/reject_unrelated.py --list
```
To scan **all active (non-rejected)** jobs instead of just the `sourced` ones, append the `--all-active` flag:
```bash
python3 .claude/skills/reject-unrelated-jobs/scripts/reject_unrelated.py --list --all-active
```

### Step 2: Present Candidates to the User
Present the resulting list of unrelated job candidates to the user in a clean table format. **Always ask for the user's explicit confirmation before performing the database update.**

### Step 3: Execute the Rejection
Once the user confirms they want to proceed:
- To reject **all** the detected candidates, run:
  ```bash
  python3 .claude/skills/reject-unrelated-jobs/scripts/reject_unrelated.py --reject-all
  ```
  *(Add `--all-active` to the command if the dry-run scan was performed on all active jobs)*
  
- To reject **specific** job IDs from the candidates, run:
  ```bash
  python3 .claude/skills/reject-unrelated-jobs/scripts/reject_unrelated.py --reject-ids <comma_separated_ids>
  ```
