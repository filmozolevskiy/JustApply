import asyncio
import inspect

from . import db as database
from .core.scraper import scrape_linkedin_jobs
from .core.matcher import load_resume, evaluate_job, check_recruiter_by_name
from .core.enrichment import source_contacts, generate_outreach_templates
from .schemas import OutreachSettings


async def run_search_pipeline(
    query: str,
    location: str = "Remote",
    active_resume: str = "qa.md",
    mock_eval: bool = False,
    allowed_remote_types: list = None,
    seniorities: str = "any",
    company_sizes: str = "any",
    countries: str = "us",
    time_range: str = "any",
    log_func=None,
) -> list:
    """Scrape, deduplicate, apply Pre-Evaluation Filters, evaluate, and save jobs. Returns list of saved job dicts."""

    async def log(msg: str, level: str = "info"):
        if log_func is None:
            return
        if inspect.iscoroutinefunction(log_func):
            await log_func(msg, level)
        else:
            log_func(msg, level)

    jobs = await scrape_linkedin_jobs(
        query=query,
        location=location,
        remote_types=allowed_remote_types,
        seniorities=seniorities,
        company_sizes=company_sizes,
        countries=countries,
        time_range=time_range,
        log_func=log_func,
    )

    scraped_count = len(jobs)
    await log(f"Found {scraped_count} matching jobs.")

    resume_content = None
    if not mock_eval:
        try:
            resume_content = load_resume(active_resume)
            await log(f"Loaded resume profile: {active_resume}")
        except FileNotFoundError:
            try:
                resume_content = load_resume("qa.md")
                await log(f"Resume '{active_resume}' not found, falling back to qa.md", "warning")
            except FileNotFoundError:
                await log("No resume found. Skipping LLM evaluation.", "warning")

    database.init_db()
    saved = []
    duplicates_count = 0
    pre_filtered_count = 0
    evaluated_count = 0

    # Normalise allowed remote types once for Pre-Evaluation Filter comparisons.
    _allowed_remote = [t.lower().strip() for t in (allowed_remote_types or [])]
    _filter_remote = bool(_allowed_remote) and "any" not in _allowed_remote

    for job in jobs:
        title = job.get("title") or ""
        company = job.get("company") or ""
        link = job.get("link") or ""

        # 1. Deduplicate — skip jobs already on the board.
        if database.job_exists(title, company, link):
            await log(f"Skipping duplicate: '{title}' at '{company}'")
            duplicates_count += 1
            continue

        # 2. Pre-Evaluation Filters — cheap non-LLM checks before Resume Matcher.
        if _filter_remote:
            job_remote_type = (job.get("remoteType") or "").lower()
            if job_remote_type not in _allowed_remote:
                pre_filtered_count += 1
                await log(
                    f"Pre-filter: '{title}' at '{company}' — remote type '{job_remote_type}' not in {_allowed_remote}",
                    "info",
                )
                continue

        job["resumeUsed"] = active_resume

        if mock_eval:
            job.setdefault("matchScore", 0)
            job.setdefault("matchType", "")
            job.setdefault("shouldProceed", False)
            job.setdefault("strengths", [])
            job.setdefault("gaps", [])
            if check_recruiter_by_name(company):
                job["isRecruiter"] = True
                job["gaps"].append("Posted by a recruiting agency/staffing firm")
            else:
                job["isRecruiter"] = False
        elif resume_content:
            evaluated_count += 1
            await log(f"Evaluating '{title}' at {company}...")
            evaluation = await evaluate_job(job, resume_content, log_func, allowed_remote_types)
            if evaluation:
                job["matchScore"] = evaluation.get("matchScore", 0)
                job["matchType"] = evaluation.get("matchType", "")
                job["shouldProceed"] = evaluation.get("shouldProceed", False)
                job["strengths"] = evaluation.get("strengths", [])
                job["gaps"] = evaluation.get("gaps", [])
                if "remoteType" in evaluation:
                    job["remoteType"] = evaluation["remoteType"]
                if "summary" in evaluation:
                    job["description"] = evaluation["summary"]
                job["isRecruiter"] = evaluation.get("isRecruiter", False)
                if evaluation.get("salary"):
                    job["salary"] = evaluation["salary"]

        job_id = database.add_job(job)
        if job_id is not None:
            job["id"] = job_id
            saved.append(job)
            await log(f"Saved: '{title}' at {company} (id={job_id})")

    saved_count = len(saved)
    await log(
        f"Pipeline complete. Scraped: {scraped_count} | Duplicates skipped: {duplicates_count} | "
        f"Pre-filtered: {pre_filtered_count} | Evaluated: {evaluated_count} | Saved: {saved_count}"
    )
    return saved


async def run_enrichment_pipeline(job: dict, log_func=None, bust_cache: bool = False) -> dict | None:
    """Source contacts, generate outreach message, and persist enriched job."""

    async def log(msg: str, level: str = "info"):
        if log_func is None:
            return
        if inspect.iscoroutinefunction(log_func):
            await log_func(msg, level)
        else:
            log_func(msg, level)

    job_id = job.get("id")
    if not job_id:
        return None

    if job.get("status") != "enriching":
        if not database.start_enrichment(job_id):
            await log(f"Job id={job_id} not found.", "error")
            return None

    title = job.get("title") or ""
    company = job.get("company") or ""
    await log(f"Enriching '{title}' at '{company}'...")

    enrichment_note = ""
    contacts = []

    source_meta = {}
    try:
        settings = OutreachSettings(**database.get_outreach_settings())
        contacts = await source_contacts(
            job,
            settings=settings,
            log_func=log_func,
            bust_cache=bust_cache,
            meta=source_meta,
        )
    except Exception as exc:
        enrichment_note = f"Enrichment failed: {exc}"
        await log(enrichment_note, "error")

    if not enrichment_note and not contacts:
        if source_meta.get("empty_reason") == "no_employees":
            enrichment_note = "No LinkedIn employees found for this company."
        else:
            enrichment_note = "No contacts matched active Outreach Settings."
        await log("No contacts found.", "warning")
    elif contacts:
        await log(f"Found {len(contacts)} contact(s). Primary: {contacts[0].get('name', 'Unknown')}")

    templates = await generate_outreach_templates(job, contacts, log_func=log_func)
    outreach_message = templates.get("recruiter") or templates.get("russian_speaker") or ""

    enriched = database.enrich_job(
        job_id,
        contacts,
        outreach_message,
        enrichment_note=enrichment_note,
        recruiter_template=templates.get("recruiter", ""),
        russian_speaker_template=templates.get("russian_speaker", ""),
    )
    if enriched:
        if enrichment_note:
            await log(f"Enrichment failed for job id={job_id}: {enrichment_note}", "error")
        else:
            await log(f"Enrichment complete for job id={job_id}.", "success")
    return enriched
