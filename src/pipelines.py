import asyncio
import inspect

from . import database
from .core.scraper import scrape_linkedin_jobs
from .core.matcher import load_resume, evaluate_job, check_recruiter_by_name
from .core.outreach import source_contacts, load_resume_for_outreach, generate_outreach_message


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
    """Scrape, evaluate, deduplicate, and save jobs. Returns list of saved job dicts."""

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

    await log(f"Found {len(jobs)} matching jobs.")

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

    for job in jobs:
        title = job.get("title") or ""
        company = job.get("company") or ""
        link = job.get("link") or ""

        if database.job_exists(title, company, link):
            await log(f"Skipping duplicate job: '{title}' at '{company}'")
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

    await log(f"Pipeline complete. {len(saved)} jobs saved.")
    return saved


async def run_enrichment_pipeline(job: dict, log_func=None) -> dict | None:
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

    title = job.get("title") or ""
    company = job.get("company") or ""
    await log(f"Enriching '{title}' at '{company}'...")

    contacts = await source_contacts(job, log_func=log_func)
    if contacts:
        await log(f"Found {len(contacts)} contact(s). Primary: {contacts[0].get('name', 'Unknown')}")
    else:
        await log("No contacts found.", "warning")

    primary_contact = contacts[0] if contacts else None
    contact_name = primary_contact.get("name") if primary_contact else "Hiring Manager"
    is_russian = bool(primary_contact.get("russian_speaker")) if primary_contact else False

    resume_name = job.get("resumeUsed") or "qa.md"
    resume_content = load_resume_for_outreach(resume_name)
    outreach_message = await generate_outreach_message(job, contact_name, is_russian, resume_content)

    enriched = database.enrich_job(job_id, contacts, outreach_message)
    if enriched:
        await log(f"Enrichment complete for job id={job_id}.", "success")
    return enriched
