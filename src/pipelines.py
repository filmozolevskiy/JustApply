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
    active_resume: str = "general_cv.md",
    mock_eval: bool = False,
    allowed_remote_types: list = None,
    seniorities: str = "any",
    company_sizes: str = "any",
    countries: str = "us",
    time_range: str = "any",
    log_func=None,
    job_saved_func=None,
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
                resume_content = load_resume("general_cv.md")
                await log(f"Resume '{active_resume}' not found, falling back to general_cv.md", "warning")
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
            if job_saved_func:
                if inspect.iscoroutinefunction(job_saved_func):
                    await job_saved_func(job)
                else:
                    job_saved_func(job)

    saved_count = len(saved)
    await log(
        f"Pipeline complete. Scraped: {scraped_count} | Duplicates skipped: {duplicates_count} | "
        f"Attribute-filtered: {attribute_filtered_count} | Evaluated: {evaluated_count} | Saved: {saved_count}",
        "summary",
    )
    return saved


async def run_reassess_pipeline(
    job_id: int,
    active_resume: str = "general_cv.md",
    log_func=None,
) -> Job:
    """Re-run Resume Matcher on an existing job and persist updated scores."""
    job = database.get_job(job_id)
    if not job:
        raise ValueError("Job not found")

    async def log(msg: str, level: str = "info"):
        if log_func is None:
            return
        if inspect.iscoroutinefunction(log_func):
            await log_func(msg, level)
        else:
            log_func(msg, level)

    try:
        resume_content = load_resume(active_resume)
    except FileNotFoundError:
        try:
            resume_content = load_resume("general_cv.md")
            active_resume = "general_cv.md"
            await log(f"Resume not found, falling back to general_cv.md", "warning")
        except FileNotFoundError:
            raise ValueError("No resume profile found for reassessment")

    title = job.title or ""
    company = job.company or ""
    await log(f"Re-assessing '{title}' at {company} with {active_resume}...")

    job_dict = job.model_dump()
    evaluation = await evaluate_job(job_dict, resume_content, log_func)
    if not evaluation:
        await log("Resume Matcher returned no result; job unchanged.", "warning")
        raise ValueError("Resume Matcher failed — no evaluation returned")

    merged = merge_job_attributes(job_dict, evaluation)
    fields = {
        "matchScore": evaluation.get("matchScore", 0),
        "matchType": evaluation.get("matchType", ""),
        "shouldProceed": evaluation.get("shouldProceed", False),
        "resumeUsed": active_resume,
        "strengths": evaluation.get("strengths", []),
        "gaps": evaluation.get("gaps", []),
        "description": evaluation.get("summary") or job.description or "",
        "isRecruiter": evaluation.get("isRecruiter", False),
        "salary": evaluation.get("salary") or job.salary or "",
        "remoteType": merged["remoteType"],
        "seniority": merged["seniority"],
        "unclassified": False,
    }

    updated = database.update_job_evaluation(job_id, fields)
    if not updated:
        raise ValueError("Failed to persist reassessed job")

    await log(
        f"Re-assessed: score {fields['matchScore']}, "
        f"{fields['matchType']}, shouldProceed={fields['shouldProceed']}",
        "success",
    )
    return updated


async def run_reclassify_pipeline(job_id: int, log_func=None) -> Job:
    """Re-run classification and template generation.

    Cache-hit path: re-classifies cached Contact Sample for all active streams — no Apify call.
    No-cache path: regenerates Outreach Message Templates only; contacts unchanged.
    """
    from .db.cache import get_contact_sample

    job = database.get_job(job_id)
    if not job:
        raise ValueError("Job not found")
    job = coerce_job(job)
    if job.status != "accepted":
        raise ValueError("Job must be in Accepted lane to re-classify")

    slug = company_cache_slug(job.company or "", job.companyUrl or "")
    settings = OutreachSettings(**database.get_outreach_settings())

    # Check whether any active stream has cached data.
    if settings.target_recruiters or settings.target_russian_speakers:
        active_streams = []
        if settings.target_recruiters:
            active_streams.append("recruiters")
        if settings.target_russian_speakers:
            active_streams.append("russian")
        has_cache = any(get_contact_sample(slug, stream=s) for s in active_streams)
    else:
        has_cache = bool(get_contact_sample(slug, stream=""))

    if not has_cache:
        # Template-only path: regenerate templates without touching contacts.
        existing_contacts = [c.model_dump() for c in job.contacts]
        templates = await generate_outreach_templates(
            job,
            existing_contacts,
            log_func=log_func,
            short_connection_note=settings.short_connection_note,
        )
        outreach_message = templates.get("recruiter") or templates.get("russian_speaker") or ""
        note = "Outreach templates refreshed; contacts unchanged (no cached employee sample)."
        updated = database.enrich_job(
            job_id,
            [],
            outreach_message,
            enrichment_note=note,
            enrichment_note_kind="info",
            recruiter_template=templates.get("recruiter", ""),
            russian_speaker_template=templates.get("russian_speaker", ""),
            activity_kind="reclassify_no_cache",
            keep_contacts=True,
        )
        if not updated:
            raise ValueError("Failed to persist re-classified job")
        return updated

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
    """Fetch next Apify page for billable streams, append to per-stream cache, and re-classify."""
    from .db.cache import get_contact_sample, append_contact_sample
    from .core.enrichment.contact_sample import resolve_load_more_streams

    job = database.get_job(job_id)
    if not job:
        raise ValueError("Job not found")
    job = coerce_job(job)
    if job.status != "accepted":
        raise ValueError("Job must be in Accepted lane to load more contacts")

    settings = OutreachSettings(**database.get_outreach_settings())
    slug = company_cache_slug(job.company or "", job.companyUrl or "")
    company_url = job.companyUrl or ""

    resolved = resolve_load_more_streams(
        slug, settings.model_dump(), company_url, get_contact_sample,
    )
    billable = resolved["billable_streams"]
    if not billable:
        reason = resolved.get("blocked_reason") or "unknown"
        messages = {
            "missing_company_url": "No LinkedIn company URL — cannot fetch employees.",
            "no_audience_toggles": "No audience toggles active in Contact Search Settings.",
            "all_streams_exhausted": "All active streams are exhausted — LinkedIn returned no further profiles.",
        }
        raise ValueError(messages.get(reason, "No streams available to fetch."))

    total_new_profiles = 0
    for stream_info in billable:
        stream = stream_info["stream_key"]
        start_page = stream_info["page"]
        if stream == "recruiters":
            new_profiles = await _run_apify_for_recruiters(
                company_url, log_func=log_func, start_page=start_page
            )
        else:
            new_profiles = await _run_apify_for_russian_speakers(
                company_url, log_func=log_func, start_page=start_page
            )
        append_contact_sample(slug, new_profiles, stream=stream)
        total_new_profiles += len(new_profiles)

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
        new_profile_count=total_new_profiles,
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
    enrichment_note_kind = ""
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
        elif settings.target_recruiters and settings.target_russian_speakers:
            recruiter_kept = sum(1 for c in contacts if c.get("is_recruiter"))
            russian_kept = sum(1 for c in contacts if c.get("russian_speaker"))
            empty_streams = []
            if recruiter_kept == 0:
                empty_streams.append("Recruiters")
            if russian_kept == 0:
                empty_streams.append("Russian Speakers")
            if empty_streams and (recruiter_kept > 0 or russian_kept > 0):
                enrichment_note = (
                    f"No {' or '.join(empty_streams)} contacts found. "
                    "Try Load More Contacts."
                )
                enrichment_note_kind = "warning"

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
        enrichment_note_kind=enrichment_note_kind,
        recruiter_template=templates.get("recruiter", ""),
        russian_speaker_template=templates.get("russian_speaker", ""),
    )
    if enriched:
        clear_enrichment_prior(job_id)
        if enrichment_note and enrichment_note_kind != "warning":
            await log(f"Enrichment failed for job id={job_id}: {enrichment_note}", "error")
        else:
            await log(f"Enrichment complete for job id={job_id}.", "success")
    return enriched
