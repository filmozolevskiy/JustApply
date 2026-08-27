import inspect

from . import db as database
from .core.annual_posted_salary import annualize_posted_salary
from .core.apify_linkedin_scraper import scrape_apify_linkedin_jobs
from .core.attribute_gating import (
    format_attribute_mismatch,
    merge_job_attributes,
    passes_attribute_gate,
)
from .core.batch_evaluation import submit_backfill_batches, submit_batch_evaluation
from .core.company_research.glassdoor_intel import (
    GlassdoorInfrastructureError,
    GlassdoorIntelError,
    _pick_company_match,
    _summarize_interviews,
    build_job_company_research_snapshot,
    default_apify_runner,
    format_activity_log_message,
    format_repick_activity_log_message,
    normalize_salary_row,
    parse_overview_row,
)
from .core.company_research.preflight import (
    company_research_allowed,
    resolve_company_research_slices,
)
from .core.enrichment import company_cache_slug, generate_outreach_templates, source_contacts
from .core.enrichment.contact_sample import (
    _run_apify_for_recruiters,
    _run_apify_for_russian_speakers,
    detect_country_from_location,
    linkedin_company_slug_from_url,
)
from .core.enrichment.coordinator import clear_enrichment_prior
from .core.matcher import check_recruiter_by_name, evaluate_job, load_resume
from .core.scraper import scrape_linkedin_jobs
from .core.source_platform import (
    APIFY_LINKEDIN,
    BRIGHTDATA_LINKEDIN,
    validate_source_platform,
)
from .db.job_model import coerce_job
from .schemas import Job, OutreachSettings

# Reassess demotes on attribute-gate failure only from these lanes.
_REASSESS_DEMOTE_STATUSES = frozenset({"scraped", "matched"})


async def run_search_pipeline(
    query: str,
    location: str = "Remote",
    search_regions: list[tuple[str, str]] | None = None,
    per_region_limit: int = 200,
    active_resume: str = "general_cv.md",
    mock_eval: bool = False,
    mock_scraper: bool = False,
    allowed_remote_types: list = None,
    seniorities: str = "any",
    company_sizes: str = "any",
    employment_types: str = "any",
    salary_min: int | None = None,
    countries: str = "us",
    time_range: str = "any",
    platform: str | None = None,
    log_func=None,
    job_saved_func=None,
) -> list:
    """Scrape, deduplicate, evaluate, attribute-gate, and save jobs. Returns list of saved job dicts.

    ``platform`` selects the scrape provider (Source Platform). Unsupported
    values raise before any vendor call — never fall through to Bright Data.

    ``mock_scraper`` forces the LinkedIn scraper into mock mode (no Bright Data
    or Apify Actor call). Callers should resolve it via ``service.scraper_will_mock``
    so a mock-evaluation run never triggers a real, billable scrape.
    """
    resolved_platform = validate_source_platform(platform)

    async def log(msg: str, level: str = "info"):
        if log_func is None:
            return
        if inspect.iscoroutinefunction(log_func):
            await log_func(msg, level)
        else:
            log_func(msg, level)

    if resolved_platform == BRIGHTDATA_LINKEDIN:
        jobs = await scrape_linkedin_jobs(
            query=query,
            location=location,
            search_regions=search_regions,
            per_region_limit=per_region_limit,
            remote_types=allowed_remote_types,
            seniorities=seniorities,
            company_sizes=company_sizes,
            employment_types=employment_types,
            countries=countries,
            time_range=time_range,
            log_func=log_func,
            force_mock=mock_scraper,
        )
    elif resolved_platform == APIFY_LINKEDIN:
        await log("Source Platform: Apify LinkedIn scrape starting.", "info")
        jobs = await scrape_apify_linkedin_jobs(
            query=query,
            location=location,
            search_regions=search_regions,
            per_region_limit=per_region_limit,
            remote_types=allowed_remote_types,
            seniorities=seniorities,
            company_sizes=company_sizes,
            employment_types=employment_types,
            countries=countries,
            time_range=time_range,
            log_func=log_func,
            force_mock=mock_scraper,
        )
        await log("Source Platform: Apify LinkedIn scrape finished.", "info")
    else:
        # validate_source_platform only returns supported values; keep exhaustiveness.
        raise RuntimeError(f"No scrape dispatcher for platform {resolved_platform!r}")

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
    
    # 1. Deduplicate first
    new_jobs = []
    duplicates_count = 0
    for job in jobs:
        title = job.get("title") or ""
        company = job.get("company") or ""
        link = job.get("link") or ""
        if database.job_exists(title, company, link):
            duplicates_count += 1
            continue
        new_jobs.append(job)
    
    await log(f"Deduplication complete: {len(new_jobs)} new jobs, {duplicates_count} duplicates skipped.")

    if not new_jobs:
        await log("No new jobs to save.", "summary")
        return []

    saved = []
    jobs_to_submit = []

    for job in new_jobs:
        job["resumeUsed"] = active_resume
        job.setdefault("matchScore", 0)
        job.setdefault("matchType", "")
        job.setdefault("shouldProceed", False)
        job.setdefault("strengths", [])
        job.setdefault("gaps", [])
        job["status"] = "scraped"

        if mock_eval:
            if check_recruiter_by_name(job.get("company", "")):
                job["isRecruiter"] = True
                job["gaps"].append("Posted by a recruiting agency/staffing firm")
            else:
                job["isRecruiter"] = False

        job_id = database.add_job(job)
        if job_id is None:
            continue

        job["id"] = job_id
        saved.append(job)
        if job_saved_func:
            if inspect.iscoroutinefunction(job_saved_func):
                await job_saved_func(job)
            else:
                job_saved_func(job)

        if not mock_eval and resume_content:
            jobs_to_submit.append(job)

    batches_submitted = 0
    if jobs_to_submit:
        created_batches = await submit_batch_evaluation(
            jobs_to_submit,
            resume_content,
            kind="search",
            log_func=log_func,
            allowed_remote_types=allowed_remote_types,
            seniorities=seniorities,
            employment_types=employment_types,
            salary_min=salary_min,
        )
        batches_submitted = len(created_batches)

    saved_count = len(saved)
    await log(
        f"Pipeline complete. Scraped: {scraped_count} | Duplicates skipped: {duplicates_count} | "
        f"Saved to Scraped: {saved_count} | Batch jobs submitted: {batches_submitted}",
        "summary",
    )
    return saved


async def run_backfill_pipeline(
    active_resume: str = "general_cv.md",
    allowed_remote_types: list = None,
    seniorities: str = "any",
    employment_types: str = "any",
    salary_min: int | None = None,
    wait: bool = False,
    log_func=None,
    db_path=None,
) -> dict:
    """Submit Batch Evaluation Jobs for unevaluated jobs; poller writes results back.

    Jobs with empty matchType are fetched regardless of status or archive state.
    Submission uses the shared batch path with an in-flight cap; the Batch Poller
    moves passing jobs to Matched and gate failures to Rejected.
    """

    async def log(msg: str, level: str = "info"):
        if log_func is None:
            return
        if inspect.iscoroutinefunction(log_func):
            await log_func(msg, level)
        else:
            log_func(msg, level)

    database.init_db(db_path)
    jobs = database.get_unevaluated_jobs(db_path=db_path)
    total = len(jobs)

    if not total:
        await log("No unevaluated jobs found — nothing to backfill.", "summary")
        return {"total": 0, "batches_submitted": 0, "jobs_submitted": 0}

    await log(f"Backfill: {total} unevaluated jobs found.")

    try:
        resume_content = load_resume(active_resume)
        await log(f"Loaded resume: {active_resume}")
    except FileNotFoundError:
        try:
            resume_content = load_resume("general_cv.md")
            active_resume = "general_cv.md"
            await log("Resume not found, falling back to general_cv.md", "warning")
        except FileNotFoundError:
            await log("No resume found — cannot backfill.", "error")
            return {"total": total, "batches_submitted": 0, "jobs_submitted": 0}

    job_dicts = [j.model_dump() for j in jobs]
    submission = await submit_backfill_batches(
        job_dicts,
        resume_content,
        wait=wait,
        log_func=log_func,
        db_path=db_path,
        allowed_remote_types=allowed_remote_types,
        seniorities=seniorities,
        employment_types=employment_types,
        salary_min=salary_min,
    )

    await log(
        f"Backfill complete. Total: {total} | Jobs submitted: {submission['jobs_submitted']} | "
        f"Batches submitted: {submission['batches_submitted']}",
        "summary",
    )
    return {
        "total": total,
        "batches_submitted": submission["batches_submitted"],
        "jobs_submitted": submission["jobs_submitted"],
        "chunks_remaining": submission.get("chunks_remaining", 0),
    }


async def run_reassess_pipeline(
    job_id: int,
    active_resume: str = "general_cv.md",
    allowed_remote_types: list | None = None,
    seniorities: str = "any",
    employment_types: str = "any",
    salary_min: int | None = None,
    log_func=None,
) -> Job:
    """Re-run Resume Matcher on an existing job and persist updated scores.

    Applies the attribute gate from the caller's Job Search Settings (defaults
    are “any” — CLI v1). On gate failure, only Scraped/Matched jobs move to
    Rejected; Accepted+ keep their lane while matcher fields still update.
    """
    job = database.get_job(job_id)
    if not job:
        raise ValueError("Job not found")

    remote_prefs = allowed_remote_types if allowed_remote_types is not None else ["any"]

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
            await log("Resume not found, falling back to general_cv.md", "warning")
        except FileNotFoundError:
            raise ValueError("No resume profile found for reassessment")

    title = job.title or ""
    company = job.company or ""
    await log(f"Re-assessing '{title}' at {company} with {active_resume}...")

    job_dict = job.model_dump()
    original_status = (job_dict.get("status") or "").strip().lower()
    evaluation = await evaluate_job(job_dict, resume_content, log_func)
    if not evaluation:
        await log("Resume Matcher returned no result; job unchanged.", "warning")
        raise ValueError("Resume Matcher failed — no evaluation returned")

    merged = merge_job_attributes(job_dict, evaluation)
    annual_band = annualize_posted_salary(
        evaluation.get("postedSalary"),
        job_location=job_dict.get("location") or "",
    )
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
        "annualMin": annual_band["annualMin"] if annual_band else None,
        "annualMax": annual_band["annualMax"] if annual_band else None,
        "annualCurrency": annual_band["annualCurrency"] if annual_band else None,
        "remoteType": merged["remoteType"],
        "seniority": merged["seniority"],
        "employmentType": merged["employmentType"],
        "unclassified": False,
    }

    updated = database.update_job_evaluation(job_id, fields)
    if not updated:
        raise ValueError("Failed to persist reassessed job")

    gate_ok = passes_attribute_gate(
        merged["remoteType"],
        merged["seniority"],
        remote_prefs,
        seniorities,
        employment_type=merged["employmentType"],
        employment_types=employment_types,
        annual_max=fields["annualMax"],
        annual_min=fields["annualMin"],
        salary_min=salary_min,
    )
    if not gate_ok and original_status in _REASSESS_DEMOTE_STATUSES:
        mismatch = format_attribute_mismatch(
            title,
            company,
            remote_type=merged["remoteType"],
            seniority=merged["seniority"],
            allowed_remote_types=remote_prefs,
            seniorities=seniorities,
            employment_type=merged["employmentType"],
            employment_types=employment_types,
            annual_max=fields["annualMax"],
            annual_min=fields["annualMin"],
            salary_min=salary_min,
        )
        await log(mismatch, "warning")
        demoted = database.update_job_status(job_id, "rejected")
        if demoted:
            updated = demoted

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

    async def log(msg: str, level: str = "info"):
        if log_func is None:
            return
        if inspect.iscoroutinefunction(log_func):
            await log_func(msg, level)
        else:
            log_func(msg, level)

    job = database.get_job(job_id)
    if not job:
        raise ValueError("Job not found")
    job = coerce_job(job)
    if job.status != "accepted":
        raise ValueError("Job must be in Accepted lane to re-classify")

    enrichment_note = ""
    settings = OutreachSettings()

    try:
        settings = OutreachSettings(**database.get_outreach_settings())
    except Exception as exc:
        enrichment_note = f"Could not load Outreach Settings: {exc}"
        await log(enrichment_note, "error")

    # Detect country from job location for targeted outreach
    detected_country = detect_country_from_location(job.location)
    slug = company_cache_slug(job.company or "", job.companyUrl or "", country=detected_country)

    async def safe_generate_templates(contacts_list):
        nonlocal enrichment_note
        try:
            return await generate_outreach_templates(
                job,
                contacts_list,
                log_func=log_func,
                short_connection_note=settings.short_connection_note,
            )
        except Exception as exc:
            template_note = f"Outreach template generation failed: {exc}"
            enrichment_note = (
                f"{enrichment_note} {template_note}".strip()
                if enrichment_note
                else template_note
            )
            await log(template_note, "error")
            return {"recruiter": "", "russian_speaker": ""}

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
        templates = await safe_generate_templates(existing_contacts)
        outreach_message = templates.get("recruiter") or templates.get("russian_speaker") or ""
        note = (
            enrichment_note
            or "Outreach templates refreshed; contacts unchanged (no cached employee sample)."
        )
        note_kind = "" if enrichment_note else "info"
        updated = database.enrich_job(
            job_id,
            [],
            outreach_message,
            enrichment_note=note,
            enrichment_note_kind=note_kind,
            recruiter_template=templates.get("recruiter", ""),
            russian_speaker_template=templates.get("russian_speaker", ""),
            activity_kind="reclassify_no_cache",
            keep_contacts=True,
        )
        if not updated:
            raise ValueError("Failed to persist re-classified job")
        return updated

    source_meta = {}
    contacts = []
    try:
        contacts = await source_contacts(
            job,
            settings=settings,
            log_func=log_func,
            meta=source_meta,
        )
    except Exception as exc:
        sourcing_note = f"Contact sourcing failed: {exc}"
        enrichment_note = (
            f"{enrichment_note} {sourcing_note}".strip()
            if enrichment_note
            else sourcing_note
        )
        await log(sourcing_note, "error")

    if not enrichment_note and not contacts:
        if source_meta.get("empty_reason") == "no_company_url":
            enrichment_note = "No LinkedIn company URL — cannot fetch employees."
        elif source_meta.get("empty_reason") == "no_employees":
            enrichment_note = "No LinkedIn employees found for this company."
        else:
            enrichment_note = "No contacts matched active Outreach Settings."

    templates = await safe_generate_templates(contacts)
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
    from .core.enrichment.contact_sample import (
        company_cache_slug,
        detect_country_from_location,
        resolve_load_more_streams,
    )
    from .db.cache import append_contact_sample, get_contact_sample

    job = database.get_job(job_id)
    if not job:
        raise ValueError("Job not found")
    job = coerce_job(job)
    if job.status != "accepted":
        raise ValueError("Job must be in Accepted lane to load more contacts")

    settings = OutreachSettings(**database.get_outreach_settings())
    # Detect country from job location for targeted outreach
    detected_country = detect_country_from_location(job.location)
    slug = company_cache_slug(job.company or "", job.companyUrl or "", country=detected_country)
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

    # Country filter list for Apify calls
    country_filter = [detected_country] if detected_country else None

    total_new_profiles = 0
    for stream_info in billable:
        stream = stream_info["stream_key"]
        start_page = stream_info["page"]
        if stream == "recruiters":
            new_profiles = await _run_apify_for_recruiters(
                company_url, log_func=log_func, start_page=start_page, locations=country_filter
            )
        else:
            new_profiles = await _run_apify_for_russian_speakers(
                company_url, log_func=log_func, start_page=start_page, locations=country_filter
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
    settings = OutreachSettings()

    try:
        settings = OutreachSettings(**database.get_outreach_settings())
    except Exception as exc:
        enrichment_note = f"Could not load Outreach Settings: {exc}"
        await log(enrichment_note, "error")

    source_meta = {}
    try:
        contacts = await source_contacts(
            job,
            settings=settings,
            log_func=log_func,
            meta=source_meta,
        )
    except Exception as exc:
        sourcing_note = f"Contact sourcing failed: {exc}"
        enrichment_note = (
            f"{enrichment_note} {sourcing_note}".strip()
            if enrichment_note
            else sourcing_note
        )
        await log(sourcing_note, "error")

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


async def run_company_research_pipeline(
    job_id: int,
    glassdoor_job_title: str,
    log_func=None,
    apify_runner=None,
    db_path=None,
    activity_log_override: str | None = None,
) -> Job:
    """Fetch Glassdoor employer intel, update cache, and persist job snapshot."""

    async def log(msg: str, level: str = "info"):
        if log_func is None:
            return
        if inspect.iscoroutinefunction(log_func):
            await log_func(msg, level)
        else:
            log_func(msg, level)

    job = database.get_job(job_id, db_path=db_path)
    if not job:
        raise ValueError(f"Job id={job_id} not found")
    if not company_research_allowed(job.status, job.archived):
        raise ValueError("Company research is only available for Matched and later lanes")

    title = (glassdoor_job_title or job.title or "").strip()
    resolved = resolve_company_research_slices(
        job.company or "",
        job.title or "",
        glassdoor_job_title=title,
    )
    company_key = resolved["company_key"]
    title_key = resolved["title_key"]
    cache_row = resolved.get("cache_row") or {}
    billable = set(resolved["billable_slices"])

    runner = apify_runner or default_apify_runner
    linkedin_slug = linkedin_company_slug_from_url(job.companyUrl or "")

    company_id = cache_row.get("glassdoorCompanyId") or ""
    matched_name = cache_row.get("matchedName") or ""
    overview = {
        "companySize": cache_row.get("companySize"),
        "rating": cache_row.get("rating"),
        "reviewCount": cache_row.get("reviewCount"),
        "recommendPercent": cache_row.get("recommendPercent"),
    }
    salary = (cache_row.get("salariesByTitle") or {}).get(title_key)
    interviews = (cache_row.get("interviewsByTitle") or {}).get(title_key)

    try:
        if "companySearch" in billable:
            await log(f"Glassdoor company search for '{job.company}'…")
            search_rows = await runner("companySearch", company_name=job.company or "")
            match = _pick_company_match(job.company or "", search_rows, linkedin_slug)
            company_id = str(
                match.get("companyId") or match.get("id") or match.get("employerId") or ""
            )
            if not company_id:
                raise GlassdoorIntelError(f"Could not resolve Glassdoor company ID for '{job.company}'")
            matched_name = str(
                match.get("companyName") or match.get("name") or match.get("shortName") or job.company
            )
            await log(f"Matched Glassdoor employer: {matched_name}")
            database.set_company_research_cache(
                company_key,
                {"glassdoorCompanyId": company_id, "matchedName": matched_name},
                db_path=db_path,
            )

        if "companyOverview" in billable:
            await log(f"Glassdoor overview for {matched_name}…")
            overview_rows = await runner("companyOverview", company_id=company_id)
            overview = parse_overview_row(overview_rows)
            database.set_company_research_cache(
                company_key,
                {
                    "glassdoorCompanyId": company_id,
                    "matchedName": matched_name,
                    **overview,
                },
                db_path=db_path,
            )
            await log("Overview cached")

        if "companySalaries" in billable:
            await log(f"Glassdoor salaries for '{title}'…")
            salary_rows = await runner(
                "companySalaries",
                company_id=company_id,
                job_title=title,
            )
            salary = None
            for row in salary_rows:
                salary = normalize_salary_row(row, title)
                if salary:
                    break
            salaries_by_title = dict(cache_row.get("salariesByTitle") or {})
            salaries_by_title[title_key] = salary
            database.set_company_research_cache(
                company_key,
                {"salariesByTitle": salaries_by_title},
                db_path=db_path,
            )
            await log("Salary slice cached" if salary else "Salary slice cached (empty)")

        if "companyInterviews" in billable:
            await log(f"Glassdoor interviews for '{title}'…")
            interview_rows = await runner(
                "companyInterviews",
                company_id=company_id,
                job_title=title,
            )
            interviews = _summarize_interviews(interview_rows, title)
            interviews_by_title = dict(cache_row.get("interviewsByTitle") or {})
            interviews_by_title[title_key] = interviews
            database.set_company_research_cache(
                company_key,
                {"interviewsByTitle": interviews_by_title},
                db_path=db_path,
            )
            await log(f"Interview slice cached ({len(interviews)} snippets)")

        snapshot = build_job_company_research_snapshot(
            glassdoor_company_id=company_id,
            matched_name=matched_name,
            overview=overview,
            glassdoor_job_title=title,
            salary=salary,
            interviews=interviews or [],
        )
        updated = database.update_company_research(job_id, snapshot, db_path=db_path)
        if not updated:
            raise ValueError("Failed to persist company research snapshot")
        database.log_activity(
            job_id,
            activity_log_override or format_activity_log_message(snapshot),
            db_path=db_path,
        )
        await log("Company research complete.", "success")
        return database.get_job(job_id, db_path=db_path) or updated

    except GlassdoorInfrastructureError as exc:
        database.log_activity(job_id, f"Company research failed · {exc}", db_path=db_path)
        await log(f"Company research failed: {exc}", "error")
        raise
    except GlassdoorIntelError as exc:
        database.log_activity(job_id, f"Company research failed · {exc}", db_path=db_path)
        await log(f"Company research failed: {exc}", "error")
        raise


async def run_company_research_repick_pipeline(
    job_id: int,
    glassdoor_job_title: str,
    glassdoor_company_id: str,
    matched_name: str,
    log_func=None,
    apify_runner=None,
    db_path=None,
) -> Job:
    """Repick Glassdoor employer — clear cache, seed new match, fetch billable slices."""
    from .db.company_research_cache import delete_company_research_cache, normalize_company_name

    job = database.get_job(job_id, db_path=db_path)
    if not job:
        raise ValueError(f"Job id={job_id} not found")
    if not company_research_allowed(job.status, job.archived):
        raise ValueError("Company research is only available for Matched and later lanes")

    company_key = normalize_company_name(job.company or "")
    delete_company_research_cache(company_key, db_path=db_path)
    database.set_company_research_cache(
        company_key,
        {
            "glassdoorCompanyId": glassdoor_company_id,
            "matchedName": matched_name,
        },
        db_path=db_path,
    )

    return await run_company_research_pipeline(
        job_id,
        glassdoor_job_title,
        log_func=log_func,
        apify_runner=apify_runner,
        db_path=db_path,
        activity_log_override=format_repick_activity_log_message(matched_name),
    )
