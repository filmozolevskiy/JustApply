# Job Hunter

A system to automate job search, resume matching, personalized outreach, and application tracking.

## Language

**Job Tracker Database**:
A local SQLite database (`job_tracker.db` inside the `src/` directory) serving as the persistent storage for job listings, compatibility scores, outreach contacts, notes, and application pipeline workflows.
_Avoid_: Google Sheets, Job Tracker Sheet, Drive database, Trello database

**Resume Profiles**:
Markdown files (`.md`) stored in a local `resumes/` folder in the project root representing the candidate's professional background tailored for specific target roles (e.g. `qa.md`, `project_manager.md`).
_Avoid_: Google Drive CVs, resume database, cloud resumes

**Resume Matcher**:
An LLM-based component that compares job descriptions with candidate resumes to compute compatibility scores, list strengths, identify skill gaps, determine remote/hybrid status, and generate a concise job summary. The target role is configured per search run using the corresponding profile.
_Avoid_: Resume filter, CV checker

**LinkedIn Scraper API**:
A hybrid web scraping integration using third-party APIs (Bright Data for job listings and Apify for company employee details) to fetch data without requiring personal LinkedIn credentials or cookies.
_Avoid_: Local scraper, browser automation, LinkedIn MCP server

**Russian Speaker**:
A company employee identified (via Gemini name/headline classification) as likely having a Russian or CIS cultural background. Targeted for referral outreach because shared cultural background increases referral likelihood — not limited to HR or recruiting roles.
_Avoid_: Russian HR contact, Russian recruiter, language filter

**Contact Sample**:
Up to 100 LinkedIn employee profiles fetched from a target company via Apify, used as the pool for Russian Speaker classification. If no Russian speakers are found in the sample, the top 3 HR/recruiter profiles from the same sample serve as the fallback outreach targets.
_Avoid_: Employee list, full company scrape

**Outreach Generator**:
An LLM-based component that creates customized cover letters and referral request messages tailored to a specific job listing and the candidate's resume.
_Avoid_: Letter generator, email writer

**Kanban Dashboard**:
A FastAPI-based single-page web application served locally on localhost `127.0.0.1:8000` to visualize application progress across status lanes (`Sourced`, `Enriching`, `Enriched`, `Contacted`, `Interviewing`, `Rejected`).
_Avoid_: Sheets UI, Command Center
