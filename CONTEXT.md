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
An LLM-based component that compares job descriptions with candidate resumes to compute compatibility scores, list strengths, identify skill gaps, and generate a concise job summary. Runs only on jobs that survive deduplication and **Pre-Evaluation Filters** in the Search & Evaluation Pipeline. Remote type for gating uses scraper-derived values; the Resume Matcher does not run for jobs filtered out before evaluation.
_Avoid_: Resume filter, CV checker

**Search & Evaluation Pipeline**:
The orchestrated flow triggered by job search: scrape listings via Bright Data, deduplicate against existing Kanban cards, apply Pre-Evaluation Filters, then run the Resume Matcher only on remaining new jobs. No LLM calls occur for duplicates or jobs rejected by cheap filters. Emits an aggregate cost summary to Task Logs at completion (scraped, duplicates skipped, pre-filtered, evaluated, saved counts).
_Avoid_: search pipeline, job search flow, scrape-and-match

**Pre-Evaluation Filters**:
Cheap, non-LLM checks applied to new scraped jobs after deduplication and before the Resume Matcher. In v1, includes remote-type matching against the search run's allowed remote preferences using scraper-derived `remoteType`. Rejected jobs are not saved to the Job Tracker Database; each rejection is logged to the Task Logs console. **Recruiting Company** detection is not a Pre-Evaluation Filter — agency postings still pass through to the Resume Matcher and are saved with penalty, per existing behavior.
_Avoid_: pre-filter, cheap gate, early rejection

**LinkedIn Scraper API**:
A hybrid web scraping integration using third-party APIs (Bright Data for job listings and Apify for company employee details) to fetch data without requiring personal LinkedIn credentials or cookies. It operates in a fail-fast manner with trigger rate-limiting to protect API credentials and credits from run-away loops.
_Avoid_: Local scraper, browser automation, LinkedIn MCP server, silent mock fallbacks

**Russian Speaker**:
A company employee classified by the LLM (using name, headline, languages, current position, and location) as likely having a Russian or CIS cultural background. Targeted for referral outreach because shared cultural background increases referral likelihood — not limited to HR or recruiting roles.
_Avoid_: Russian HR contact, Russian recruiter, language filter

**Job Poster**:
The LinkedIn employee Bright Data identifies as the person who published a job listing (~11% of listings). Stored as a preliminary contact at sourcing time (`is_job_poster: true`) and visible on the Kanban immediately. Shows a **Poster** badge in the UI — retained permanently even after enrichment assigns an Outreach Audience. On enrichment, the Contact Sample is fetched (from cache or Apify) and classified; results are merged by LinkedIn profile URL, preserving `is_job_poster` on the matching contact. Dropped from the contact list only if they match neither active Outreach Audience toggle.
_Avoid_: poster contact, job author, listing owner

**Contact**:
A person in a job's outreach list. Carries identity flags (`is_job_poster`) and Outreach Audience flags (`russian_speaker`, `is_recruiter`) set during enrichment classification. Identity flags are for display and tracking; audience flags control inclusion and message template selection. LinkedIn profile identity is matched by normalized `/in/{slug}` URL. The contacted checkbox toggles that contact's contacted flag only — it does not change the job's pipeline status.
_Avoid_: employee record, profile entry, lead

**Contact Sample**:
Up to 100 LinkedIn employee profiles fetched from a target company via Apify, passed as a batch to the LLM for Outreach Audience classification. The Job Poster is included in the same classification pass when present. Up to 5 contacts per Outreach Audience type are selected from the classified results.
_Avoid_: Employee list, full company scrape

**Contact Sample Cache**:
A per-company store in the Job Tracker Database of the most recent raw Contact Sample, keyed by the normalized LinkedIn company slug (lowercase, trimmed, spaces and underscores to hyphens — the same transform used for Apify lookup). Reused across enrichments for jobs at the same company to avoid repeat Apify calls; entries do not expire by age. Busted only by an explicit **Refresh Contacts** action — re-enrichment alone does not invalidate the cache. Outreach Audience classification and Job Poster merge run on every enrichment regardless of cache hit — only the Apify fetch is skipped. Empty or failed Apify fetches are never cached. Cache hits and misses are logged to Task Logs; cache hits are also recorded in the job's Job Activity Log.
_Avoid_: contact cache, outreach candidate cache, classified contact cache

**Refresh Contacts**:
The sole manual re-run action for contact sourcing on enriched jobs. Lives in the Outreach Contacts section header. Busts the Contact Sample Cache for the job's company, fetches a fresh Contact Sample via Apify, and re-runs classification and template generation. Not shown on sourced jobs — first fetch uses Enrich Job. There is no separate cache-preserving re-enrich action in the Kanban Dashboard; changing Outreach Settings on an already-enriched job requires Refresh Contacts.
_Avoid_: force refresh, bust cache, reload contacts, re-enrich

**Outreach Audience**:
The classification assigned to a contact by the LLM: Russian Speaker, Recruiter, or both. Determines which Outreach Message Template is loaded and which badges the Kanban Dashboard shows. Badges follow classification flags only (`is_recruiter` → **HR** badge, `russian_speaker` → **RU** badge) — not title keyword matching. When a contact qualifies as both, the Recruiter template takes priority and the contact is grouped under Recruiters — but both audience badges are shown.
_Avoid_: Contact type, outreach category, audience filter

**Contact Group**:
The visual section a contact appears under in the job drawer: **Recruiters**, **Russian Speakers**, or **Other** — in that order. Recruiters and Russian Speakers follow Outreach Audience flags; dual-classified contacts belong to Recruiters. Other holds contacts with neither audience flag. Empty groups are hidden.
_Avoid_: contact bucket, audience section, contact category

**Active Contact**:
The contact currently selected in the job drawer whose Outreach Audience determines which Outreach Message Template is shown in the textarea. Clicking a contact row sets them as Active Contact and loads the matching template (Recruiter template when `is_recruiter` is true — including dual-classified contacts; otherwise Russian Speaker template). The Active Contact row is visually highlighted (e.g. cyan left border). On switch, the greeting name in the textarea is replaced with the new contact's first name (first word of `name`) — whether the stored template still has a Name Placeholder or the previous contact's name was showing. That substitution is display-only for copy/paste; the stored Outreach Message Template keeps the Name Placeholder. The contacted checkbox is independent — it only toggles contacted status on that contact and does not move the job card. When the drawer opens, Active Contact defaults to the first uncontacted contact in the list; if all contacts are already marked contacted, it falls back to the first contact in the list.
_Avoid_: selected contact, focused contact, current contact

**Outreach Message Template**:
An audience-specific Connection Note draft stored on a job — either a Recruiter Outreach Template or a Russian Speaker Outreach Template. Generated at enrichment time only (at most two LLM calls); there is no Regenerate action in the Kanban Dashboard. The greeting uses a **Name Placeholder** instead of a contact name so the user can paste the same draft to multiple people and fill in the name manually. The Kanban Dashboard shows the template matching the Active Contact's Outreach Audience. User edits in the textarea are saved back to the corresponding audience template on the job, with the greeting name normalized back to the Name Placeholder before save so the stored draft stays audience-generic.
_Avoid_: outreach message, single draft, per-contact message

**Recruiter Outreach Template**:
The Outreach Message Template used for Recruiter contacts. Stored separately from the Russian Speaker Outreach Template on each job.
_Avoid_: recruiter message, HR template

**Russian Speaker Outreach Template**:
The Outreach Message Template used for Russian Speaker contacts. Stored separately from the Recruiter Outreach Template on each job.
_Avoid_: russian message, referral template

**Legacy Outreach Message**:
The single outreach draft stored on jobs enriched before the two-template model. On read, migrated into the Recruiter Outreach Template; the Russian Speaker Outreach Template remains empty until the job is re-enriched.
_Avoid_: old outreachMessage, single draft migration

**Minimal Fallback Template**:
The hardcoded Connection Note used when LLM generation exceeds 200 characters after retry. Uses three `______` placeholders — contact name, company, and job title — plus the audience call to action. Recruiter ending: `I would be grateful to connect and share my CV.` Russian Speaker ending: `I'd be grateful if you could refer me for the role.`
_Avoid_: fallback message, default template, truncate

**Name Placeholder**:
The literal `______` used where the user fills in text manually. In a normal Outreach Message Template, one placeholder appears in the greeting (e.g. `Hello ______,`) for the contact's first name. In a Minimal Fallback Template, three placeholders stand in for contact name, company, and job title.
_Avoid_: first name, contact name, {firstName}

**Connection Note**:
A LinkedIn outreach message sent with a connection request, hard-limited to 200 characters. All Outreach Message Templates must fit this limit — no posting link, no bullet points, shortened company name and job title. Recruiter and Russian Speaker templates share the same shape; only the call to action differs. If generation exceeds 200 characters, the Outreach Generator retries once with stricter shortening instructions; if still over limit, it falls back to a **Minimal Fallback Template** — a fixed Connection Note with three Name Placeholders (greeting name, company, job title) and the audience-appropriate call to action.
_Avoid_: connection message, invite note, short message, InMail

**Outreach Generator**:
An LLM-based component that creates Connection Note Outreach Message Templates for each audience type present on a job. Both formats are ESL-friendly, use the Name Placeholder, and stay within 200 characters. The LLM shortens the company name and job title at its discretion to fit the limit. The body always includes the fixed fit line (`My experience align well with the requirements.`). The **Russian Speaker** template ends with a referral ask (`I'd be grateful if you could refer me for the role.`). The **Recruiter** template ends with a connect / share-CV ask (`I would be grateful to connect and share my CV.`). Generates whichever templates are needed based on classified contacts and Outreach Settings. On Enrichment Failure, generates both templates anyway.
_Avoid_: Letter generator, email writer

**Enrichment**:
The pipeline that sources a Contact Sample (from the Contact Sample Cache or via Apify), classifies Outreach Audience contacts, and generates Outreach Message Templates for a job. First enrichment is triggered via Enrich Job on sourced listings. On enriched jobs, contact sourcing re-runs only via Refresh Contacts. Classification and Job Poster merge run on every enrichment; merges results by LinkedIn profile URL and preserves identity flags.
_Avoid_: promote, contact sourcing, outreach generation

**Enrichment Note**:
A system-written status message on a job (`enrichmentNote`) recording the outcome of the most recent enrichment run. Set when an Enrichment Failure occurs; cleared on the next successful enrichment. Shown as a warning on the Kanban card and in full in the job drawer. Not user-editable — distinct from `comment`.
_Avoid_: enrichment error, failure message, enrich status

**Enrichment Failure**:
An enrichment run that ends with zero Outreach Audience contacts or encounters an infrastructure error (Apify trigger failure, timeout, missing credentials, classification error). The job stays in the Enriched lane with an Enrichment Note explaining the reason. Even with zero contacts, the Outreach Generator still produces both Recruiter and Russian Speaker Outreach Templates so the user can cold-connect manually.
_Avoid_: failed enrich, sourcing error, empty contacts

**Outreach Settings**:
A global configuration panel in the Kanban Dashboard for toggling which Outreach Audience types to target during enrichment (Russian Speakers, Recruiters, or both). Applies to all enrichments — not per-job.
_Avoid_: Outreach filters, enrichment config, audience popup

**Job Activity Log**:
A per-job append-only history of lifecycle events: lane moves, enrichment outcomes, contacts marked contacted, job creation, and Contact Sample Cache hits during enrichment. Excludes comment edits, outreach template edits, and other pipeline internals (Apify polling, LLM retries, Pre-Evaluation Filter rejections). Shown only in the job drawer — not on the Kanban card — directly below Job Info. Hidden until the first event exists. Collapsed by default with a chevron; collapsed view shows the latest event as a one-line preview (no timestamp); expand to reveal the full chronological list with smart-date timestamps (time only for today, date + time for older entries). Lane moves are logged separately from per-contact contacted toggles — marking a contact contacted does not log a lane move. Enrichment started is recorded separately from enrichment outcome; failures include the Enrichment Note text. Populated forward from rollout — no retroactive history for jobs already in the tracker. Retains at most 50 entries; oldest drop off. Distinct from the global Task Logs console.
_Avoid_: card history, audit trail, status log, event feed

**Kanban Dashboard**:
A FastAPI-based single-page web application served locally on localhost `127.0.0.1:8000` to visualize application progress across status lanes (`Sourced`, `Enriching`, `Enriched`, `Contacted`, `Interviewing`, `Rejected`). Moving a job to the Contacted lane is always a deliberate user action — via the drawer's **Mark Contacted** button or the kanban card's lane chevrons — never triggered by marking an individual contact as contacted. The job drawer exposes a foldable **Job Activity Log** section. Streams pipeline logs from background tasks (job search and enrichment) to an on-page console via Server-Sent Events. Enrichment completion logs match the outcome: success when contacts are found, error on Enrichment Failure. Contact Groups and audience badges appear in the job drawer only. The outreach textarea shows a live character counter (`142/200`) that turns red when the draft exceeds the Connection Note limit.
_Avoid_: Sheets UI, Command Center

**Board Controls**:
A client-side UI component on the Kanban Dashboard allowing the user to filter job listings by remote type and company size, and sort them by match score or novelty in real-time.
_Avoid_: DB filters, scraper filters, query controls

**Recruiting Company**:
A job posting publisher classified (via LLM matching or local company keyword lists) as a staffing or recruitment agency rather than the direct hiring employer. Job cards from recruiting companies display a dedicated badge on the Kanban Dashboard and are automatically discouraged by applying a compatibility score penalty.
_Avoid_: Headhunter posting, agency recruiter


