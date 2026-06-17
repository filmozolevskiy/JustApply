import asyncio
import inspect

from . import db as database
from .core.scraper import scrape_linkedin_jobs
from .core.matcher import load_resume, evaluate_job, check_recruiter_by_name
from .core.enrichment import source_contacts, generate_outreach_templates, company_cache_slug
from .core.enrichment.coordinator import clear_enrichment_prior
from .core.enrichment.contact_sample import _run_apify_actor
from .core.pre_evaluation import format_remote_type_rejection, passes_remote_type_filter
from .schemas import Job, OutreachSettings
from .db.job_model import coerce_job


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
        if not passes_remote_type_filter(job, allowed_remote_types):
            pre_filtered_count += 1
            await log(
                format_remote_type_rejection(title, company, job, allowed_remote_types),
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
            evaluation = await evaluate_job(job, resume_content, log_func)
            if evaluation:
                job["matchScore"] = evaluation.get("matchScore", 0)
                job["matchType"] = evaluation.get("matchType", "")
                job["shouldProceed"] = evaluation.get("shouldProceed", False)
                job["strengths"] = evaluation.get("strengths", [])
                job["gaps"] = evaluation.get("gaps", [])
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


async def run_reclassify_pipeline(job_id: int, log_func=None) -> Job:
    """Re-run classification and template generation on cached Contact Sample — no Apify call."""
    from .db.cache import get_contact_sample

    job = database.get_job(job_id)
    if not job:
        raise ValueError("Job not found")
    job = coerce_job(job)
    if job.status != "accepted":
        raise ValueError("Job must be in Accepted lane to re-classify")

    slug = company_cache_slug(job.company or "", job.companyUrl or "")
    if not get_contact_sample(slug):
        raise ValueError("No cached contact sample for this company")

    settings = OutreachSettings(**database.get_outreach_settings())
    source_meta = {}
    contacts = await source_contacts(
        job,
        settings=settings,
        log_func=log_func,
        meta=source_meta,
    )

    enrichment_note = ""
    if not contacts:
        if source_meta.get("empty_reason") == "no_company_url":
            enrichment_note = "No LinkedIn company URL — cannot fetch employees."
        elif source_meta.get("empty_reason") == "no_employees":
            enrichment_note = "No LinkedIn employees found for this company."
        else:
            enrichment_note = "No contacts matched active Outreach Settings."

    templates = await generate_outreach_templates(
        job,
        contacts,
        log_func=log_func,
        short_connection_note=settings.short_connection_note,
    )
    outreach_message = templates.get("recruiter") or templates.get("russian_speaker") or ""

    updated = database.enrich_job(
        job_id,
        contacts,
        outreach_message,
        enrichment_note=enrichment_note,
        recruiter_template=templates.get("recruiter", ""),
        russian_speaker_template=templates.get("russian_speaker", ""),
        activity_kind="reclassify",
    )
    if not updated:
        raise ValueError("Failed to persist re-classified job")
    return updated


async def run_load_more_contacts_pipeline(job_id: int, log_func=None) -> Job:
    """Fetch next Apify page, append to Contact Sample Cache, and re-classify."""
    from .db.cache import get_contact_sample, append_contact_sample

    job = database.get_job(job_id)
    if not job:
        raise ValueError("Job not found")
    job = coerce_job(job)
    if job.status != "accepted":
        raise ValueError("Job must be in Accepted lane to load more contacts")

    slug = company_cache_slug(job.company or "", job.companyUrl or "")
    cache_entry = get_contact_sample(slug)
    if not cache_entry:
        raise ValueError("No cached contact sample for this company")

    pages_fetched = cache_entry.get("pages_fetched", 1)
    company_url = job.companyUrl or ""

    new_profiles = await _run_apify_actor(
        company_url,
        log_func=log_func,
        start_page=pages_fetched + 1,
    )

    append_contact_sample(slug, new_profiles)

    settings = OutreachSettings(**database.get_outreach_settings())
    source_meta = {}
    contacts = await source_contacts(
        job,
        settings=settings,
        log_func=log_func,
        meta=source_meta,
    )

    enrichment_note = ""
    if not contacts:
        if source_meta.get("empty_reason") == "no_company_url":
            enrichment_note = "No LinkedIn company URL — cannot fetch employees."
        elif source_meta.get("empty_reason") == "no_employees":
            enrichment_note = "No LinkedIn employees found for this company."
        else:
            enrichment_note = "No contacts matched active Outreach Settings."

    templates = await generate_outreach_templates(
        job,
        contacts,
        log_func=log_func,
        short_connection_note=settings.short_connection_note,
    )
    outreach_message = templates.get("recruiter") or templates.get("russian_speaker") or ""

    updated = database.enrich_job(
        job_id,
        contacts,
        outreach_message,
        enrichment_note=enrichment_note,
        recruiter_template=templates.get("recruiter", ""),
        russian_speaker_template=templates.get("russian_speaker", ""),
        activity_kind="load_more",
        new_profile_count=len(new_profiles),
    )
    if not updated:
        raise ValueError("Failed to persist updated job")
    return updated


async def run_enrichment_pipeline(job: Job, log_func=None) -> Job | None:
    """Source contacts, generate outreach message, and persist enriched job."""

    async def log(msg: str, level: str = "info"):
        if log_func is None:
            return
        if inspect.iscoroutinefunction(log_func):
            await log_func(msg, level)
        else:
            log_func(msg, level)

    job = coerce_job(job)
    job_id = job.id
    if not job_id:
        return None

    if job.status != "accepted":
        await log(f"Job id={job_id} is not accepted; call begin_enrichment first.", "error")
        return None

    title = job.title or ""
    company = job.company or ""
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
            meta=source_meta,
        )
    except Exception as exc:
        enrichment_note = f"Enrichment failed: {exc}"
        await log(enrichment_note, "error")

    if not enrichment_note:
        if source_meta.get("empty_reason") == "no_company_url":
            enrichment_note = "No LinkedIn company URL — cannot fetch employees."
        elif not contacts:
            if source_meta.get("empty_reason") == "no_employees":
                enrichment_note = "No LinkedIn employees found for this company."
            else:
                enrichment_note = "No contacts matched active Outreach Settings."

    if contacts:
        await log(f"Found {len(contacts)} contact(s). Primary: {contacts[0].get('name', 'Unknown')}")
    else:
        await log("No contacts found.", "warning")

    templates = await generate_outreach_templates(
        job,
        contacts,
        log_func=log_func,
        short_connection_note=settings.short_connection_note,
    )
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
        clear_enrichment_prior(job_id)
        if enrichment_note:
            await log(f"Enrichment failed for job id={job_id}: {enrichment_note}", "error")
        else:
            await log(f"Enrichment complete for job id={job_id}.", "success")
    return enriched
