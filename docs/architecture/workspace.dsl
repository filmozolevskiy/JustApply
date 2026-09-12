workspace "JustApply" "Local job-search automation: scrape listings, score them against Resume Profiles, source outreach contacts, and track applications." {

    !identifiers hierarchical
    !impliedRelationships false

    model {
        user = person "Job Seeker" "Runs searches, triages Kanban cards, confirms paid API spend, and sends LinkedIn outreach from generated templates."

        justApply = softwareSystem "JustApply" "Scrapes job listings, evaluates them with the Resume Matcher, enriches Accepted Jobs, and stores everything in a local Job Tracker Database. Never logs into the user's LinkedIn account." {
            !docs .
            !adrs adr

            dashboard = container "Kanban Dashboard" "Primary UI. FastAPI serves the board and hosts the Batch Poller on startup. Default http://127.0.0.1:8000" "Python, FastAPI, HTML/JS" {
                ui = component "Kanban UI" "Lanes Scraped through Rejected, job drawer, Profile Manager, Spend Confirmation, and Task Logs." "HTML/JS"
                api = component "HTTP API" "REST for jobs, settings, resumes, search, enrichment, Company Research, and evaluation lock." "FastAPI"
                poller = component "Batch Poller" "Resumes in-flight Batch Evaluation Jobs, polls Gemini Batch API, writes scores, and may auto-retry failed Scraped Jobs." "Python"
                searchPipe = component "Search & Evaluation Pipeline" "Scrape by Search Region, dedupe, save Scraped Jobs immediately, submit Batch Evaluation Jobs, return without waiting." "Python"
                enrichPipe = component "Enrichment" "Contact Sample (cache or Apify), Outreach Audience classification, Outreach Message Templates. Runs in place on Accepted Jobs." "Python"
                research = component "Company Research" "Glassdoor employer intel via Apify. Manual; does not change Kanban lane." "Python"
                matcher = component "Resume Matcher" "Per-job Gemini Batch prompts: score, strengths, gaps, attributes, Posted Salary. Attribute gating after write-back." "Python"
                scraper = component "LinkedIn Scraper adapters" "Bright Data and Apify listing scrapers. Rate-limited. Mock mode for tests." "Python"
                safety = component "Database Safety Gate" "Blocks destructive database operations and writes Database Snapshots before runs." "Python"
            }

            cli = container "CLI" "Same pipelines as the dashboard without the Batch Poller loop: --search, --promote, --backfill, --collect, --reassess." "Python"

            db = container "Job Tracker Database" "Single SQLite jobs table plus batch records, Contact Sample Cache, Company Research Cache, and settings. data/just_apply.db" "SQLite" {
                tags "Database"
            }

            resumes = container "Resume Profiles" "Markdown files in resumes/. Active Resume Profile is chosen in the Profile Manager." "Markdown files" {
                tags "FileStore"
            }

            snapshots = container "Database Snapshots" "Pre-run copies used for Migration Failure Recovery. ~/.just_apply/backups/" "Files" {
                tags "FileStore"
            }
        }

        brightData = softwareSystem "Bright Data" "Job listing scraper API. Credits per record. Primary listing source." {
            tags "External"
        }
        apify = softwareSystem "Apify" "LinkedIn company-employee Contact Sample actors and Glassdoor Company Research actors." {
            tags "External"
        }
        gemini = softwareSystem "Google Gemini" "Interactive LLM plus Gemini Batch API (50% of interactive price) for Resume Matcher evaluation." {
            tags "External"
        }
        linkedin = softwareSystem "LinkedIn" "Source of listings, Job Posters, and employee profiles. JustApply never uses the user's login or cookies." {
            tags "External"
        }
        glassdoor = softwareSystem "Glassdoor" "Employer ratings, salary bands, and interview snippets fetched only through Apify." {
            tags "External"
        }

        user -> justApply "Runs search, triage, and enrichment locally" "HTTPS and CLI"
        user -> justApply.dashboard "Triages cards, manages Resume Profiles, confirms scrape and Apify spend" "HTTPS"
        user -> justApply.dashboard.ui "Uses the Kanban board and Spend Confirmation" "HTTPS"
        user -> justApply.cli "Runs search, promote, backfill, collect, reassess" "CLI"
        user -> linkedin "Applies and sends connection notes" "HTTPS"

        justApply -> brightData "Scrapes job listings" "HTTPS"
        justApply -> apify "Fetches contacts and Glassdoor intel" "HTTPS"
        justApply -> gemini "Resume matching, classification, templates" "HTTPS"

        justApply.dashboard -> justApply.db "CRUD jobs, batches, caches, settings" "SQLite"
        justApply.cli -> justApply.db "CRUD jobs, batches, caches, settings" "SQLite"
        justApply.dashboard -> justApply.resumes "List, edit, import PDF, select Active Resume Profile" "Filesystem"
        justApply.cli -> justApply.resumes "Loads Active Resume Profile for matching" "Filesystem"
        justApply.dashboard -> justApply.snapshots "Writes snapshots via Database Safety Gate" "Filesystem"
        justApply.cli -> justApply.snapshots "Writes snapshots via Database Safety Gate" "Filesystem"

        justApply.dashboard -> brightData "Scrapes listings after Spend Confirmation" "HTTPS"
        justApply.cli -> brightData "Scrapes listings" "HTTPS"
        justApply.dashboard -> apify "Contact Sample, Load More Contacts, Company Research" "HTTPS"
        justApply.cli -> apify "Contact Sample via --promote" "HTTPS"
        justApply.dashboard -> gemini "Batch evaluation, classification, templates, Resume Import" "HTTPS"
        justApply.cli -> gemini "Submit and collect Batch Evaluation Jobs" "HTTPS"

        brightData -> linkedin "Reads public job listings" "HTTPS"
        apify -> linkedin "Reads company employee profiles" "HTTPS"
        apify -> glassdoor "Reads employer intel" "HTTPS"

        justApply.dashboard.ui -> justApply.dashboard.api "JSON over HTTP" "HTTPS"
        justApply.dashboard.api -> justApply.dashboard.searchPipe "Search and backfill" "In-process"
        justApply.dashboard.api -> justApply.dashboard.enrichPipe "Enrich Job, Load More Contacts, Re-classify" "In-process"
        justApply.dashboard.api -> justApply.dashboard.research "Company Research and Wrong company?" "In-process"
        justApply.dashboard.api -> justApply.dashboard.matcher "Reassess one or all jobs" "In-process"
        justApply.dashboard.api -> justApply.dashboard.safety "Init and guarded writes" "In-process"
        justApply.dashboard.api -> justApply.db "Reads and writes" "SQLite"
        justApply.dashboard.api -> justApply.resumes "Profile Manager and Resume Import" "Filesystem"
        justApply.dashboard.poller -> justApply.dashboard.matcher "Applies batch JSON to jobs" "In-process"
        justApply.dashboard.poller -> gemini "Polls Batch Evaluation Jobs" "HTTPS"
        justApply.dashboard.poller -> justApply.db "Moves Scraped to Matched or Rejected" "SQLite"
        justApply.dashboard.searchPipe -> justApply.dashboard.scraper "Fetch listings by Search Region" "In-process"
        justApply.dashboard.searchPipe -> justApply.dashboard.matcher "Submit Batch Evaluation Jobs" "In-process"
        justApply.dashboard.searchPipe -> justApply.db "Save Scraped Jobs before any LLM call" "SQLite"
        justApply.dashboard.scraper -> brightData "Job listings" "HTTPS"
        justApply.dashboard.scraper -> apify "Optional LinkedIn listing source" "HTTPS"
        justApply.dashboard.matcher -> gemini "Gemini Batch API JSONL" "HTTPS"
        justApply.dashboard.matcher -> justApply.resumes "Reads Active Resume Profile" "Filesystem"
        justApply.dashboard.enrichPipe -> apify "Audience-targeted employee pages" "HTTPS"
        justApply.dashboard.enrichPipe -> gemini "Classify contacts and generate templates" "HTTPS"
        justApply.dashboard.enrichPipe -> justApply.db "Contacts, templates, Contact Sample Cache" "SQLite"
        justApply.dashboard.research -> apify "Glassdoor actors" "HTTPS"
        justApply.dashboard.research -> justApply.db "Company Research Cache and job snapshot" "SQLite"
        justApply.dashboard.safety -> justApply.snapshots "Copy just_apply.db" "Filesystem"
        justApply.dashboard.safety -> justApply.db "Allows or blocks operations" "SQLite"
    }

    views {
        systemContext justApply "SystemContext" {
            include *
            include linkedin
            include glassdoor
            autoLayout lr
            description "JustApply sits on the Job Seeker's machine. Vendors scrape LinkedIn and Glassdoor; Gemini scores jobs and drafts outreach. The user still applies on LinkedIn."
        }

        container justApply "Containers" {
            include *
            autoLayout lr
            description "Two entry points share one SQLite database and Resume Profiles. The dashboard hosts the Batch Poller; the CLI can --collect the same batches."
        }

        component justApply.dashboard "DashboardComponents" {
            include *
            autoLayout tb
            description "In-process Python modules behind FastAPI. CLI calls the same pipelines without the UI or the long-running poller loop."
        }

        dynamic justApply.dashboard "SearchAndEvaluation" {
            autoLayout lr
            description "Search & Evaluation Pipeline: save Scraped first, evaluate later."
            user -> justApply.dashboard.ui "Confirms scrape Spend Confirmation" "HTTPS"
            justApply.dashboard.ui -> justApply.dashboard.api "Start search" "HTTPS"
            justApply.dashboard.api -> justApply.dashboard.searchPipe "run_search" "In-process"
            justApply.dashboard.searchPipe -> justApply.dashboard.scraper "Scrape each Search Region" "In-process"
            justApply.dashboard.scraper -> brightData "Job listings" "HTTPS"
            justApply.dashboard.searchPipe -> justApply.db "Save new jobs as Scraped" "SQLite"
            justApply.dashboard.searchPipe -> justApply.dashboard.matcher "Submit Batch Evaluation Jobs" "In-process"
            justApply.dashboard.matcher -> gemini "JSONL batch (fire and return)" "HTTPS"
            justApply.dashboard.poller -> gemini "Poll until complete" "HTTPS"
            justApply.dashboard.poller -> justApply.db "Matched, Rejected, or Unclassified" "SQLite"
        }

        dynamic justApply.dashboard "EnrichmentFlow" {
            autoLayout lr
            description "Enrichment on an Accepted Job. Apify only on cache miss for an active, non-exhausted audience stream."
            user -> justApply.dashboard.ui "Enrich Job after Spend Confirmation" "HTTPS"
            justApply.dashboard.ui -> justApply.dashboard.api "POST enrich" "HTTPS"
            justApply.dashboard.api -> justApply.dashboard.enrichPipe "source contacts and templates" "In-process"
            justApply.dashboard.enrichPipe -> apify "Contact Sample if cache miss" "HTTPS"
            justApply.dashboard.enrichPipe -> gemini "Classify Outreach Audience and generate templates" "HTTPS"
            justApply.dashboard.enrichPipe -> justApply.db "Write contacts, templates, cache" "SQLite"
        }

        styles {
            element "Person" {
                shape person
                background #08427b
                color #ffffff
            }
            element "Software System" {
                background #1168bd
                color #ffffff
            }
            element "External" {
                background #999999
                color #ffffff
            }
            element "Container" {
                background #438dd5
                color #ffffff
            }
            element "Database" {
                shape cylinder
                background #438dd5
                color #ffffff
            }
            element "FileStore" {
                shape folder
                background #85bbf0
                color #000000
            }
            element "Component" {
                background #85bbf0
                color #000000
            }
        }
    }

    configuration {
        scope softwaresystem
    }
}
