import asyncio
import inspect

from . import db as database
from .core.scraper import scrape_linkedin_jobs
from .core.matcher import load_resume, evaluate_job, check_recruiter_by_name
from .core.enrichment import source_contacts, generate_outreach_templates, company_cache_slug
from .core.enrichment.coordinator import clear_enrichment_prior
from .core.enrichment.contact_sample import (
    _run_apify_actor,
    _run_apify_for_recruiters,
    _run_apify_for_russian_speakers,
)
from .core.attribute_gating import (
    format_attribute_mismatch,
    is_unclassified,
    merge_job_attributes,
    passes_attribute_gate,
)
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
    """Scrape, deduplicate, evaluate, attribute-gate, and save jobs. Returns list of saved job dicts."""

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

    if mock_eval:
        await log("mock_eval: attribute gating skipped.", "info")

    database.init_db()
    saved = []
    duplicates_count = 0
    attribute_filtered_count = 0
    evaluated_count = 0

    for job in jobs:
        title = job.get("title") or ""
        company = job.get("company") or ""
        link = job.get("link") or ""

        if database.job_exists(title, company, link):
            await log(f"Skipping duplicate: '{title}' at '{company}'")
            duplicates_count += 1
            continue

        job["resumeUsed"] = active_resume
        evaluation = {}

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
        else:
            if resume_content:
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

            merged = merge_job_attributes(job, evaluation)
            if not passes_attribute_gate(
                merged["remoteType"],
                merged["seniority"],
                allowed_remote_types,
                seniorities,
            ):
                attribute_filtered_count += 1
                await log(
                    format_attribute_mismatch(
                        title,
                        company,
                        remote_type=merged["remoteType"],
                        seniority=merged["seniority"],
                        allowed_remote_types=allowed_remote_types,
                        seniorities=seniorities,
                    ),
                    "info",
                )
                continue

            job["remoteType"] = merged["remoteType"]
            job["seniority"] = merged["seniority"]
            if is_unclassified(evaluation):
                job["unclassified"] = True

        job_id = database.add_job(job)
        if job_id is not None:
            job["id"] = job_id
            saved.append(job)
            await log(f"Saved: '{title}' at {company} (id={job_id})")

    saved_count = len(saved)
    await log(
        f"Pipeline complete. Scraped: {scraped_count} | Duplicates skipped: {duplicates_count} | "
        f"Attribute-filtered: {attribute_filtered_count} | Evaluated: {evaluated_count} | Saved: {saved_count}",
        "summary",
    )
    return saved


async def run_reclassify_pipeline(job_id: int, log_func=None) -> Job: