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
An LLM-based component that compares job descriptions with candidate resumes to compute compatibility scores, list strengths, identify skill gaps, classify remote type and seniority from listing content, and generate a concise job summary. Runs on every new scraped job that survives deduplication in the Search & Evaluation Pipeline. After evaluation, the pipeline drops jobs whose classified remote type or seniority do not match the search run's allowed preferences before saving. When the matcher fully fails, scraper-derived values are used for attribute gating instead. **Recruiting Company** detection stays in the Resume Matcher — agency postings are still saved with penalty, per existing behavior.
_Avoid_: Resume filter, CV checker

**Search & Evaluation Pipeline**:
The orchestrated flow triggered by job search: scrape listings via Bright Data (company size filtered at scrape), deduplicate against existing Kanban cards, run the Resume Matcher on each remaining new job, then drop jobs whose remote type or seniority do not match the search preferences before saving. No LLM calls occur for duplicates. Emits an aggregate cost summary to Task Logs at completion (scraped, duplicates skipped, attribute-filtered, evaluated, saved counts) using a distinct summary log style.
_Avoid_: search pipeline, job search flow, scrape-and-match

**Unclassified Job**:
A **Found Job** whose remote type and seniority were not classified by the Resume Matcher because the matcher call fully failed; attribute values used for gating and display came from the **LinkedIn Scraper API** instead. Shown with an **Unclassified** badge on the Kanban card and job drawer — explanatory text on hover only. mock_eval jobs are not Unclassified.
_Avoid_: scraper-classified job, unverified job, fallback job

**LinkedIn Scraper API**:
A hybrid web scraping integration using third-party APIs (Bright Data for job listings and Apify for company employee details) to fetch data without requiring personal LinkedIn credentials or cookies. No LinkedIn account login is needed — the user's personal account is never used. It operates in a fail-fast manner with trigger rate-limiting to protect API credentials and credits from run-away loops.
_Avoid_: Local scraper, browser automation, LinkedIn MCP server, silent mock fallbacks, LinkedIn login

**Found Job**:
A job listing saved by the Search & Evaluation Pipeline and shown in the **Found** Kanban lane. The first pipeline stage before the user decides to pursue the role. New jobs enter here after scrape and resume match; they have not been accepted or enriched yet.
_Avoid_: sourced job, scraped job, new listing

**Accepted Job**:
A job the user has decided to pursue, shown in the **Accepted** Kanban lane. Reached by dragging from **Found** (no Apify) or by clicking **Enrich Job** (which moves the job to Accepted if needed, then runs enrichment in place). The card stays in Accepted during and after enrichment — it does not move to separate enriching or enriched lanes.
_Avoid_: enriched job, promoted job, shortlisted job

**Russian Speaker**:
A company employee classified by the LLM (using name, headline, languages, current position, and location) as likely having a Russian or CIS cultural background. Targeted for referral outreach because shared cultural background increases referral likelihood — not limited to HR or recruiting roles.
_Avoid_: Russian HR contact, Russian recruiter, language filter

**Job Poster**:
The LinkedIn employee Bright Data identifies as the person who published a job listing (~11% of listings). Stored as a preliminary contact when the job is **Found** (`is_job_poster: true`) and visible on the Kanban immediately. Shows a **Poster** badge in the UI — retained permanently even after enrichment assigns an Outreach Audience. On enrichment, the Contact Sample is fetched (from cache or Apify) and classified; results are merged by LinkedIn profile URL, preserving `is_job_poster` on the matching contact. Dropped from the contact list only if they match neither active Outreach Audience toggle.
_Avoid_: poster contact, job author, listing owner

**Contact**:
A person in a job's outreach list. Carries identity flags (`is_job_poster`) and Outreach Audience flags (`russian_speaker`, `is_recruiter`) set during enrichment classification. Identity flags are for display and tracking; audience flags control inclusion and message template selection. LinkedIn profile identity is matched by normalized `/in/{slug}` URL. The contacted checkbox toggles that contact's contacted flag only — it does not change the job's pipeline status.
_Avoid_: employee record, profile entry, lead

**Contact Sample**:
LinkedIn employee profiles fetched from a target company via Apify using the job listing's LinkedIn company page URL (`companyUrl` from Bright Data). Enrichment issues one Apify run per active Contact Search Settings audience toggle — Recruiters only, Russian Speakers only, or both (two runs). Each run uses audience-targeted Apify filters rather than an unfiltered employee page. Each Apify page fetch returns up to **3** Recruiter profiles or up to **5** Russian Speaker profiles depending on the stream. No name-based slug guessing — if `companyUrl` is missing or a fetch returns zero profiles, Enrichment stops without further Apify calls for that audience. Results are merged by LinkedIn profile URL; the Job Poster is included in classification when present. All profiles the LLM classifies as matching an active Outreach Audience are kept on the job — there is no contact count limit per audience type.
_Avoid_: Employee list, full company scrape, unfiltered employee page

**Contact Sample Cache**:
A per-company, per-audience-stream store in the Job Tracker Database of raw Apify profiles for each active filter (`russian` or `recruiters`), keyed by LinkedIn company slug from the job listing's `companyUrl` plus stream. Each stream tracks its own profile list, how many LinkedIn search pages have been fetched, and whether the most recent Apify fetch for that stream returned zero profiles (**Stream Exhausted**). The next Apify call appends the following page for that filter only. Stores successful Apify responses including empty lists from a completed fetch. Infrastructure failures are not cached. Entries do not expire by age. Pre-migration unfiltered cache entries (single blob per company without a stream key) are treated as a cache miss for all streams — per-stream fetches do not reuse legacy data. Outreach Audience classification and Job Poster merge run on every enrichment regardless of cache hit — only Apify fetches are skipped for streams already cached and not exhausted. Cache hits and misses are logged to Task Logs; cache hits are also recorded in the job's Job Activity Log.
_Avoid_: contact cache, outreach candidate cache, classified contact cache, single merged employee list

**Re-classify**:
A manual action available on every **Accepted Job** in the job drawer — including never-enriched cards, enrichment failures, zero contacts, and jobs with no **Contact Sample Cache** entry. When a cached Contact Sample exists, re-runs Outreach Audience classification and template generation on that sample without calling Apify — same contact-sourcing path as enrichment on a cache hit, including **Job Poster** merge and preservation of per-contact contacted flags. When no cache exists, regenerates Outreach Message Templates only from job data and current **Outreach Settings**; contacts are left unchanged and no classification LLM call runs. Replaces any stored outreach templates with fresh LLM output — manual edits in the drawer are overwritten. Sets an **Enrichment Note** with fixed text: `Outreach templates refreshed; contacts unchanged (no cached employee sample).` — informational presentation on the card and drawer. The **Job Activity Log** records **Re-classified · templates refreshed** (not an enrichment failure). On a never-enriched **Accepted Job**, the no-cache path generates initial outreach templates without sourcing contacts — **Enrich Job** remains required for employee discovery. Used after **Outreach Settings** change or when the user wants to refresh contacts from the same employee sample. Multiple jobs may be queued — each runs sequentially with spinner feedback on the active card while others show a **Queued** badge until their turn. No cost confirmation — no Apify spend.
_Avoid_: re-enrich, refresh contacts, re-run enrichment

**Stream Exhausted**:
An audience stream whose most recent Apify fetch returned zero profiles in the raw API response. Overlap with profiles already in the **Contact Sample Cache** after deduplication does not exhaust a stream — only an empty Apify response does. **Load More Contacts** and **Enrichment** do not call Apify again for that stream until its **Contact Sample Cache** entry is cleared. Changing Contact Search Settings does not reset exhaustion. There is no user-facing cache reset in v1 — exhaustion is final for that company and stream until manual cache removal. Distinct from a cache miss — no prior per-stream fetch exists yet, and **Load More Contacts** may still fetch page 1 and create the cache entry.
_Avoid_: empty cache, no results, stream capped

**Load More Contacts**:
The manual action on **Accepted Jobs** to fetch the next Apify page for each **active** Contact Search Settings audience stream that is not **Stream Exhausted**. Shown on any **Accepted Job** with a `companyUrl` — prior enrichment is not required. A missing per-stream cache is not a blocker — **Load More Contacts** fetches page 1 and creates the cache entry for that stream. Only streams with an active toggle are considered. If one active stream is exhausted and another is not, only the non-exhausted stream is fetched (one Apify run). If both active streams can load more, both are fetched (two Apify runs). The Kanban Dashboard confirms with the user before each run using the same native `confirm()` style as **Enrich Job** — plain-text summary listing only the billable stream(s), profile count per stream, page number, total run count, estimated cost, and “Proceed?”. Appends new profiles to that stream's Contact Sample Cache entry (never replaces earlier pages), then re-runs classification and template generation on the combined cached streams for active toggles. Each page costs one Apify run per stream loaded. The user may keep loading until every active stream is **Stream Exhausted**, or they stop. When no stream can be fetched, the preflight response includes a structured **blocked reason** (e.g. all active streams **Stream Exhausted**, no audience toggles active, or missing `companyUrl`) and the dashboard shows a specific message for that reason — not a generic or misleading quota message. Not shown on **Found Jobs**. When Outreach Settings change, use **Re-classify** on each job to apply new audience toggles without Apify.
_Avoid_: refresh contacts, bust cache, reload contacts, re-fetch page one, load all streams regardless of quota

**Outreach Audience**:
The classification assigned to a contact by the LLM: Russian Speaker, Recruiter, or both. Determines which Outreach Message Template is loaded and which badges the Kanban Dashboard shows. Badges follow classification flags only (`is_recruiter` → **HR** badge, `russian_speaker` → **RU** badge) — not title keyword matching. When a contact qualifies as both, the Recruiter template takes priority and the contact is grouped under Recruiters — but both audience badges are shown. Dual-classified contacts belong to the Recruiter Contact Group only, not the Russian Speaker group; the Russian Speaker group includes only contacts with `russian_speaker` and not `is_recruiter`.
_Avoid_: Contact type, outreach category, audience filter

**Contact Group**:
The visual section a contact appears under in the job drawer: **Recruiters**, **Russian Speakers**, or **Other** — in that order. Recruiters and Russian Speakers follow Outreach Audience flags; dual-classified contacts belong to Recruiters. Other holds contacts with neither audience flag. Empty groups are hidden.
_Avoid_: contact bucket, audience section, contact category

**Active Contact**:
The contact currently selected in the job drawer whose Outreach Audience determines which Outreach Message Template is shown in the textarea. Clicking a contact row sets them as Active Contact and loads the matching template (Recruiter template when `is_recruiter` is true — including dual-classified contacts; otherwise Russian Speaker template). The Active Contact row is visually highlighted (e.g. cyan left border). On switch, the greeting name in the textarea is replaced with the new contact's first name (first word of `name`) — whether the stored template still has a Name Placeholder or the previous contact's name was showing. That substitution is display-only for copy/paste; the stored Outreach Message Template keeps the Name Placeholder. The contacted checkbox is independent — it only toggles contacted status on that contact and does not move the job card. When the drawer opens, Active Contact defaults to the first uncontacted contact in the list; if all contacts are already marked contacted, it falls back to the first contact in the list.
_Avoid_: selected contact, focused contact, current contact

**Outreach Message Template**:
An audience-specific Connection Note draft stored on a job — either a Recruiter Outreach Template or a Russian Speaker Outreach Template. Generated at enrichment or via **Re-classify** (at most two LLM calls per run). The greeting uses a **Name Placeholder** instead of a contact name so the user can paste the same draft to multiple people and fill in the name manually. The Kanban Dashboard shows the template matching the Active Contact's Outreach Audience. User edits in the textarea are saved back to the corresponding audience template on the job, with the greeting name normalized back to the Name Placeholder before save so the stored draft stays audience-generic.
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
The short Outreach Message Format: a LinkedIn message sent with a connection request, hard-limited to 200 characters. No posting link, no bullet points, shortened company name and job title. Recruiter and Russian Speaker templates share the same shape; only the call to action differs. If generation exceeds 200 characters, the Outreach Generator retries once with stricter shortening instructions; if still over limit, it falls back to a **Minimal Fallback Template** — a fixed Connection Note with three Name Placeholders (greeting name, company, job title) and the audience-appropriate call to action.
_Avoid_: connection message, invite note, short message, InMail

**Complete Outreach Message**:
The long Outreach Message Format: a fuller LinkedIn draft (~100–150 words) stored as separate Recruiter and Russian Speaker Outreach Message Templates. Uses the Name Placeholder in the greeting, includes the job posting link, highlights 1–2 resume-matched strengths as bullet points, and ends with the audience-appropriate call to action. Intended for LinkedIn accounts without the 200-character Connection Note limit. On LLM failure or missing API key, falls back to a **Complete Outreach Fallback** — a hardcoded long-form draft with Name Placeholder, job title, company, and resume profile label.
_Avoid_: long message, full message, InMail draft

**Complete Outreach Fallback**:
The hardcoded Complete Outreach Message used when LLM generation fails or no API key is set. Greeting with Name Placeholder, mentions job title and company, references the job's Resume Profile label, and ends with a generic connect / discuss CTA. Does not include posting link or bullet points.
_Avoid_: complete fallback template, long default message

**Outreach Message Format**:
The global Outreach Settings choice controlling which draft shape the Outreach Generator produces: **Connection Note** (short, ≤200 characters) or **Complete Outreach Message** (long, ~100–150 words). Default is Connection Note, selected via the **Short connection note** toggle in Contact Search Settings (checked = Connection Note, unchecked = Complete Outreach Message). Changing the format does not rewrite templates on jobs already enriched; **Re-classify** applies the new format from the cached Contact Sample without Apify.
_Avoid_: message length setting, short/long toggle, outreach mode

**Outreach Generator**:
An LLM-based component that creates Outreach Message Templates for each audience type present on a job. Output format follows the active **Outreach Message Format** setting: **Connection Note** (≤200 characters, ESL-friendly, fixed fit line) or **Complete Outreach Message** (resume-informed, bullets, posting link). Both formats use the Name Placeholder and produce separate Recruiter and Russian Speaker templates. Generates whichever templates are needed based on classified contacts and Outreach Settings. On Enrichment Failure, generates both templates anyway.
_Avoid_: Letter generator, email writer

**Enrichment**:
The pipeline that sources a Contact Sample (from the Contact Sample Cache or via Apify), classifies Outreach Audience contacts, and generates Outreach Message Templates for a job. Runs in place on an **Accepted Job** — the card does not change lanes. While running, the Accepted card shows an on-card spinner badge (e.g. “Enriching…”); the job’s pipeline status stays **Accepted**. Apify runs only when the job has a `companyUrl` and a per-stream Contact Sample Cache miss applies for a non-exhausted active stream, or **Load More Contacts** requests the next page for a non-exhausted active stream. **Enrich Job** and **Load More Contacts** use the same native browser confirmation style as today — plain-text `confirm()` with action summary, estimated cost, and “Proceed?” — listing only the billable stream(s) that will run (audience name and profile count per stream; total run count and estimated cost). No dialog when all active streams are cache hits (re-classify only). Missing `companyUrl` skips Apify and ends in Enrichment Failure with an explanatory Enrichment Note. Triggered only via **Enrich Job** or **Load More Contacts** — never by dragging to a lane. Classification and Job Poster merge run on every enrichment; merges results by LinkedIn profile URL and preserves identity flags.
_Avoid_: promote, contact sourcing, outreach generation

**Enrichment Note**:
A system-written status message on a job (`enrichmentNote`) recording contact-sourcing outcome or template-only **Re-classify** status. Set on **Enrichment Failure** or when **Re-classify** runs without a cached Contact Sample. Shown on the Kanban card and in full in the job drawer — warning presentation (amber) for enrichment failures; informational presentation (cyan) for template-only **Re-classify** notes. Cleared on the next successful enrichment that sources contacts. Not user-editable — distinct from `comment`.
_Avoid_: enrichment error, failure message, enrich status

**Enrichment Failure**:
An enrichment run that ends with zero Outreach Audience contacts across **all** active Contact Search Settings toggles, or that encounters an infrastructure error (missing or unusable `companyUrl`, Apify trigger failure, zero employees for a required stream, timeout, missing credentials, classification error). A single active toggle with zero contacts is a failure — including when that stream is **Stream Exhausted**. When multiple toggles are active and at least one stream produced contacts, the run is partial success — not a failure — even if another active stream has zero contacts. An Enrichment Note on partial success names the empty stream(s); it suggests **Load More Contacts** only when that stream is not **Stream Exhausted**, otherwise it states that LinkedIn returned no further profiles for that filter. The job stays in the **Accepted** lane. Even with zero contacts, the Outreach Generator still produces templates for active audience types so the user can cold-connect manually.
_Avoid_: failed enrich, sourcing error, empty contacts

**Outreach Settings**:
A global configuration panel in the Kanban Dashboard (labeled **Contact Search Settings** in the UI) for toggling which Outreach Audience types to target during enrichment (Russian Speakers, Recruiters, or both) and which **Outreach Message Format** to generate (Connection Note or Complete Outreach Message). Applies to all enrichments — not per-job. Changing audience or format settings does not rewrite stored templates on existing jobs; use **Re-classify**, **Enrich Job**, or **Load More Contacts** per job to apply new settings. The section heading and each toggle show a ~1 second delayed hover tooltip — the heading explains that the panel controls audiences and outreach message format; each toggle explains that specific option.
_Avoid_: Outreach filters, enrichment config, audience popup

**Auto-Archive Exemption**:
A job-level flag set when the user manually un-archives a job. Exempts that job from future automatic archival even if **Rejected At** is older than two weeks.
_Avoid_: archive override, permanent un-archive, snooze

**Rejected At**:
The timestamp recorded when a job first enters the **Rejected** lane. Set once and never cleared or reset — even if the job is later moved to another lane. Drives the two-week threshold before an **Archived Job** is hidden from the Kanban Dashboard. Jobs already in Rejected before rollout get Rejected At backfilled to migration time.
_Avoid_: rejected date, rejection time, last rejected

**Archived Job**:
A job hidden from the Kanban Dashboard by default (`archived` flag). Only **Rejected** cards can be archived manually via a hover action on the card; un-archive uses the same hover toggle when **Board Controls** visibility includes archived jobs (on archived cards in any lane). Automatic archival applies only to jobs still in **Rejected** past the **Rejected At** threshold, unless the job has an **Auto-Archive Exemption**. Manual un-archive keeps the job on the active board and sets **Auto-Archive Exemption**. An archived job may be dragged to another lane while staying archived — the lane move applies, but the card remains hidden when visibility is **Active**. Lane drag never triggers **Enrichment**. Archived jobs remain in the Job Tracker Database so deduplication still skips re-scraped listings. Automatic archival runs when the Kanban Dashboard loads jobs (`GET /api/jobs`): the sweep runs first, then results are filtered by the archived visibility setting in **Board Controls**.
_Avoid_: deleted job, purged job, expired job

**Job Activity Log**:
A per-job append-only history of lifecycle events: lane moves, enrichment outcomes, contacts marked contacted, job creation, Contact Sample Cache hits during enrichment, and archive / un-archive actions (including automatic archival after the two-week **Rejected At** threshold). Excludes comment edits, outreach template edits, and other pipeline internals (Apify polling, LLM retries, attribute mismatch rejections). Shown only in the job drawer — not on the Kanban card — directly below Job Info. Hidden until the first event exists. Collapsed by default with a chevron; collapsed view shows the latest event as a one-line preview (no timestamp); expand to reveal the full chronological list with smart-date timestamps (time only for today, date + time for older entries). Lane moves are logged separately from per-contact contacted toggles — marking a contact contacted does not log a lane move. Enrichment started is recorded separately from enrichment outcome; failures include the Enrichment Note text. Populated forward from rollout — no retroactive history for jobs already in the tracker. Retains at most 50 entries; oldest drop off. Distinct from the global Task Logs console.
_Avoid_: card history, audit trail, status log, event feed

**Kanban Dashboard**:
A FastAPI-based single-page web application served locally on localhost `127.0.0.1:8000` to visualize application progress across status lanes (`Found`, `Accepted`, `Contacted`, `Interviewing`, `Rejected`). **Enrichment** is never triggered by lane drag — only by **Enrich Job** or **Load More Contacts** buttons. **Accepted Jobs** stay in the Accepted lane during and after enrichment; an on-card spinner badge shows when enrichment is in progress. **Archived Jobs** are excluded from lanes and counts when **Board Controls** visibility is **Active**; included per the **Archived** or **All** setting otherwise. Archived cards can be dragged to other lanes while staying archived. Lane moves are drag-and-drop only — a card can be dropped on any lane, including skipping intermediate stages; lane chevrons are not shown. Dropping on the card's current lane or outside any lane is a silent no-op with no API call. Clicking a card opens the job drawer; dragging starts only after a small pointer movement threshold so clicks are not mistaken for drags. Rejecting a job is done by dragging to **Rejected** or using the card's reject control, shown on hover only. Moving a job to the **Contacted** lane is always a deliberate user action — via the drawer's **Mark Contacted** button or dragging the card to Contacted — never triggered by marking an individual contact as contacted. Lanes can be collapsed to a narrow vertical rail showing the lane name and card count; collapsed lanes remain valid drag targets and expanded lanes absorb the freed horizontal space. Collapsed lane state persists in browser local storage across reloads. Above the board, utility panels (**Pipeline Tracker**, **Task Logs**, **Outreach Settings**, **Board Controls**) share one consistent header bar style and layout order; **Board Controls** sits immediately above the lanes. **Task Logs** and **Scraper Settings** (under Pipeline Tracker) are collapsible and collapsed by default on first visit; collapse state persists in browser local storage across reloads. **Outreach Settings** and **Board Controls** stay always visible. The job drawer exposes a foldable **Job Activity Log** section. Streams pipeline logs from background tasks (job search and enrichment) to an on-page console via Server-Sent Events. Enrichment completion logs match the outcome: success when contacts are found, error on Enrichment Failure. Contact Groups and audience badges appear in the job drawer only. **Re-classify** is available on every **Accepted Job** in the drawer. **Load More Contacts** is available on every **Accepted Job** with a `companyUrl`. The drawer stays open after **Re-classify** and **Load More Contacts** complete so the user can review results and choose the next action manually. While **Re-classify** runs, the Kanban card and open drawer show a spinner badge until the run finishes; if the user closes the drawer before completion, it does not reopen automatically. The outreach textarea shows a live character counter (`142/200`) that turns red when the draft exceeds the Connection Note limit.
_Avoid_: Sheets UI, Command Center

**Board Controls**:
A client-side UI component on the Kanban Dashboard allowing the user to filter job listings by remote type, company size, and archived visibility, and sort them by match score or novelty in real-time. Archived visibility is a three-way toggle: **Active** (default — hide archived jobs), **Archived** (show only archived jobs), **All** (show both; archived cards use muted styling and an **Archived** badge). Archived visibility persists in browser local storage across reloads. Sits directly above the kanban lanes.
_Avoid_: DB filters, scraper filters, query controls

**Recruiting Company**:
A job posting publisher classified (via LLM matching or local company keyword lists) as a staffing or recruitment agency rather than the direct hiring employer. Job cards from recruiting companies display a dedicated badge on the Kanban Dashboard and are automatically discouraged by applying a compatibility score penalty.
_Avoid_: Headhunter posting, agency recruiter


