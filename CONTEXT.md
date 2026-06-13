# Job Hunter

A system to automate job search, resume matching, personalized outreach, and application tracking.

## Language

**Job Tracker Database**:
A local SQLite database (`job_tracker.db` inside the `data/` directory) serving as the persistent storage for job listings, compatibility scores, outreach contacts, notes, and application pipeline workflows.
_Avoid_: Google Sheets, Job Tracker Sheet, Drive database, Trello database

**Resume Profiles**:
Markdown files (`.md`) stored in a local `resumes/` folder in the project root representing the candidate's professional background tailored for specific target roles (e.g. `qa.md`, `project_manager.md`).
_Avoid_: Google Drive CVs, resume database, cloud resumes

**Resume Matcher**:
An LLM-based component that compares job descriptions with candidate resumes to compute compatibility scores, list strengths, identify skill gaps, determine remote/hybrid status, and generate a concise job summary. The target role is configured per search run using the corresponding profile.
_Avoid_: Resume filter, CV checker

**LinkedIn Scraper API**:
A hybrid web scraping integration using third-party APIs (Bright Data for job listings and Apify for company employee details) to fetch data without requiring personal LinkedIn credentials or cookies. It operates in a fail-fast manner with trigger rate-limiting to protect API credentials and credits from run-away loops.
_Avoid_: Local scraper, browser automation, LinkedIn MCP server, silent mock fallbacks

**Russian Speaker**:
A company employee classified by the LLM (using name, headline, languages, current position, and location) as likely having a Russian or CIS cultural background. Targeted for referral outreach because shared cultural background increases referral likelihood — not limited to HR or recruiting roles.
_Avoid_: Russian HR contact, Russian recruiter, language filter

**Contact Sample**:
Up to 100 LinkedIn employee profiles fetched from a target company via Apify, passed as a batch to the LLM for Outreach Audience classification. Up to 5 contacts per Outreach Audience type are selected from the classified results.
_Avoid_: Employee list, full company scrape

**Outreach Audience**:
The classification assigned to a contact by the LLM: Russian Speaker, Recruiter, or both. Determines which message template is used. When a contact qualifies as both, the Recruiter template takes priority.
_Avoid_: Contact type, outreach category, audience filter

**Outreach Generator**:
An LLM-based component that creates personalized outreach messages using one of two audience-specific templates: a referral request (for Russian Speakers) or a direct introduction (for Recruiters). Both templates share the same structure — short, bullet-pointed strengths, and a link to the job posting — but differ in call to action.
_Avoid_: Letter generator, email writer

**Outreach Settings**:
A global configuration panel in the Kanban Dashboard for toggling which Outreach Audience types to target during enrichment (Russian Speakers, Recruiters, or both). Applies to all enrichments — not per-job.
_Avoid_: Outreach filters, enrichment config, audience popup

**Kanban Dashboard**:
A FastAPI-based single-page web application served locally on localhost `127.0.0.1:8000` to visualize application progress across status lanes (`Sourced`, `Enriching`, `Enriched`, `Contacted`, `Interviewing`, `Rejected`).
_Avoid_: Sheets UI, Command Center

**Board Controls**:
A client-side UI component on the Kanban Dashboard allowing the user to filter job listings by remote type and company size, and sort them by match score or novelty in real-time.
_Avoid_: DB filters, scraper filters, query controls

**Recruiting Company**:
A job posting publisher classified (via LLM matching or local company keyword lists) as a staffing or recruitment agency rather than the direct hiring employer. Job cards from recruiting companies display a dedicated badge on the Kanban Dashboard and are automatically discouraged by applying a compatibility score penalty.
_Avoid_: Headhunter posting, agency recruiter


