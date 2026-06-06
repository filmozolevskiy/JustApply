---
name: job-hunter
description: Use this skill whenever the user mentions searching for jobs, matching or evaluating candidate resumes against jobs, searching company employees/recruiters, generating cover letters, promoting active applications in Google Sheets, or running the job_hunter.py script.
---

# Job Hunter Automation Skill

This skill guides the agent in coordinating the end-to-end Job Hunter pipeline to search for jobs, match them against candidate resumes, update the Job Tracker Sheet in Google Sheets, and source referral contacts on LinkedIn to generate outreach.

## 1. Prerequisites Check

Before executing any commands, inspect the workspace and verify the environment:
- Verify that `GEMINI_API_KEY` is present in the `.env` file at the root. If not, prompt the user to add it.
- Check if `token.json` exists in the root directory. 
  - If `token.json` is missing or Sheets MCP commands fail with auth errors, guide the user to run the credentials flow manually:
    ```bash
    python3 scripts/google_sheets_mcp.py --auth
    ```
    This launches the local browser-based OAuth 2.0 user consent flow.

## 2. Search & Evaluation Pipeline

When the user asks to find or search for positions (e.g. "search for QA jobs"):
1. Determine the target position name (e.g., "QA", "project/delivery manager", "automation specialist", "data analyst/bi analyst").
2. Parse any user-specified job boards (e.g. LinkedIn, Indeed, ZipRecruiter) and map them to the `--sites` argument.
3. Run the orchestrator pipeline command:
   ```bash
   python3 job_hunter.py "<position>"
   ```
   Add optional flags:
   - Use `--sites linkedin,indeed` to restrict search sources.
   - Use `--skip-unmatched` to ignore listings that do not align with the candidate profile.
4. Verify the CLI output. If successful, proceed to read the `Jobs` tab contents to verify the updates.

## 3. Interactive Promotion & Outreach Pipeline

When matched jobs are in the `Jobs` tab:
1. Fetch and list the current jobs in the `Jobs` sheet using the `google-sheets/list_jobs` tool or by running the script.
2. Display the matched jobs to the user, highlighting the company, title, `match` details, and `no-match` gaps.
3. Ask the user which specific jobs they want to proceed with.
4. For each selected job, update the status to "Yes" using the `google-sheets/update_job_status` tool:
   ```python
   # Example parameters:
   # job_title="QA Engineer", company="Docker", should_proceed="Yes"
   ```
5. Run the promotion CLI command to source company contacts and generate outreach letters:
   ```bash
   python3 job_hunter.py "<position>" --promote
   ```
6. Verify that the promoted jobs are listed in the `Applications` tab with generated Cover Letters, referral messages, and LinkedIn contact details.

## 4. Verification

After executing any pipeline step, verify the sheets update:
- Call the `google-sheets/list_jobs` tool to verify the `Jobs` tab has new entries.
- Call the `google-sheets/list_applications` tool to confirm that applications were correctly promoted.
