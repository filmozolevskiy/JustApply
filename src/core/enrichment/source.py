"""Enrichment orchestration: Contact Sample sourcing with cache and classification."""

import inspect

from ...db.job_model import coerce_job
from ...schemas import Job, OutreachSettings
from .contact_sample import (
    CONTACT_SAMPLE_SIZE,
    RECRUITER_SAMPLE_SIZE,
    RUSSIAN_SAMPLE_SIZE,
    _run_apify_actor,
    _run_apify_for_recruiters,
    _run_apify_for_russian_speakers,
    company_cache_slug,
    normalize_linkedin_url,
    poster_to_apify_item,
    ApifyTimeoutError,
    ApifyInfrastructureError,
)
from .classifier import classify_contacts


async def source_contacts(job: Job, settings=None, log_func=None, meta: dict | None = None) -> list:
    """
    Return outreach contacts for a job using LLM classification.

    Checks the Contact Sample Cache first (per-stream for recruiter-only mode).
    On cache miss with a valid companyUrl, fetches via Apify and writes the result
    to cache (including empty results from successful runs). Infrastructure failures
    (no token, trigger error, timeout) are not cached and propagate as exceptions.
    Missing companyUrl skips Apify; the job poster is classified alone when present.

    When only Recruiters is active, uses the 'recruiters' stream cache key and fetches
    via Apify with HR function filter (maxItems=3). Legacy unfiltered cache entries
    (stream='') are not used for stream-based queries.
    """
    from ...db.cache import get_contact_sample, set_contact_sample
    from ...db.jobs import log_activity

    if settings is None:
        settings = OutreachSettings()

    async def log(msg, level="info"):
        if log_func:
            if inspect.iscoroutinefunction(log_func):
                await log_func(msg, level)
            else:
                log_func(msg, level)

    job = coerce_job(job)
    existing = [c.model_dump() for c in job.contacts]
    job_poster = next((c for c in existing if c.get("is_job_poster")), None)
    contacted_by_slug = {
        normalize_linkedin_url(c.get("url", "")): c.get("contacted", False)
        for c in existing
        if normalize_linkedin_url(c.get("url", ""))
    }

    company = job.company or ""
    company_url = job.companyUrl or ""
    if not company:
        await log("No company name for Apify sourcing.", "warning")
        return []

    slug = company_cache_slug(company, company_url)

    # Determine audience mode
    recruiter_only = settings.target_recruiters and not settings.target_russian_speakers
    russian_only = settings.target_russian_speakers and not settings.target_recruiters
    dual_audience = settings.target_recruiters and settings.target_russian_speakers

    if recruiter_only:
        items = await _source_stream(
            stream="recruiters",
            slug=slug,
            company=company,
            company_url=company_url,
            sample_size=RECRUITER_SAMPLE_SIZE,
            log=log,
            meta=meta,
            job_id=job.id,
            get_contact_sample=get_contact_sample,
            set_contact_sample=set_contact_sample,
            log_activity=log_activity,
        )
    elif russian_only:
        items = await _source_stream(
            stream="russian",
            slug=slug,
            company=company,
            company_url=company_url,
            sample_size=RUSSIAN_SAMPLE_SIZE,
            log=log,
            meta=meta,
            job_id=job.id,
            get_contact_sample=get_contact_sample,
            set_contact_sample=set_contact_sample,
            log_activity=log_activity,
        )
    elif dual_audience:
        recruiter_items = await _source_stream(
            stream="recruiters",
            slug=slug,
            company=company,
            company_url=company_url,
            sample_size=RECRUITER_SAMPLE_SIZE,
            log=log,
            meta=meta,
            job_id=job.id,
            get_contact_sample=get_contact_sample,
            set_contact_sample=set_contact_sample,
            log_activity=log_activity,
        )
        russian_items = await _source_stream(
            stream="russian",
            slug=slug,
            company=company,
            company_url=company_url,
            sample_size=RUSSIAN_SAMPLE_SIZE,
            log=log,
            meta=meta,
            job_id=job.id,
            get_contact_sample=get_contact_sample,
            set_contact_sample=set_contact_sample,
            log_activity=log_activity,
        )
        items = _merge_profiles(recruiter_items, russian_items)
    else:
        # Legacy unfiltered path (neither toggle on)
        cache_entry = get_contact_sample(slug, stream="")
        if cache_entry:
            display = cache_entry.get("display_name") or company
            fetched_at = cache_entry.get("fetched_at") or ""
            await log(f"Contact Sample Cache hit for '{display}' (fetched {fetched_at}).", "info")
            job_id = job.id
            if job_id:
                log_activity(job_id, f"Contact Sample Cache hit · {display}")
            items = cache_entry["profiles"]
        elif not company_url:
            await log("No company URL (companyUrl) — skipping Apify.", "warning")
            if meta is not None:
                meta["empty_reason"] = "no_company_url"
            items = []
        else:
            await log(f"Fetching up to {CONTACT_SAMPLE_SIZE} employees for '{company}'...", "info")
            items = await _run_apify_actor(company_url, log_func=log_func)
            set_contact_sample(slug, items, display_name=company, stream="")

    poster_slug = normalize_linkedin_url(job_poster.get("url", "")) if job_poster else ""
    fetched_profiles = bool(items)

    if items:
        if job_poster and poster_slug:
            apify_slugs = {
                normalize_linkedin_url(
                    item.get("linkedinUrl") or item.get("linkedInUrl") or
                    item.get("profileUrl") or item.get("url") or ""
                )
                for item in items
            }
            if poster_slug not in apify_slugs:
                await log("Job Poster not in Apify sample; injecting as synthetic profile.", "info")
                items = items + [poster_to_apify_item(job_poster)]
        contacts = await classify_contacts(items, settings)
    elif job_poster:
        await log("Apify returned no profiles; classifying Job Poster alone.", "warning")
        contacts = await classify_contacts([poster_to_apify_item(job_poster)], settings)
    else:
        contacts = []

    if meta is not None and not contacts and meta.get("empty_reason") != "no_company_url":
        if not fetched_profiles and not job_poster:
            meta["empty_reason"] = "no_employees"
        else:
            meta["empty_reason"] = "no_audience_match"

    poster_slug = normalize_linkedin_url(job_poster.get("url", "")) if job_poster else ""
    for contact in contacts:
        contact_slug = normalize_linkedin_url(contact.get("url", ""))
        if poster_slug and contact_slug == poster_slug:
            contact["is_job_poster"] = True
        if contact_slug in contacted_by_slug:
            contact["contacted"] = contacted_by_slug[contact_slug]

    await log(f"Found {len(contacts)} classified contact(s).", "info")
    return contacts


def _merge_profiles(recruiter_items: list, russian_items: list) -> list:
    """Merge two stream profile lists, deduplicating by normalized LinkedIn URL."""
    seen_urls: set[str] = set()
    merged = []
    for item in recruiter_items + russian_items:
        url = normalize_linkedin_url(
            item.get("linkedinUrl") or item.get("linkedInUrl") or
            item.get("profileUrl") or item.get("url") or ""
        )
        if url:
            if url in seen_urls:
                continue
            seen_urls.add(url)
        merged.append(item)
    return merged


async def _source_stream(
    *,
    stream: str,
    slug: str,
    company: str,
    company_url: str,
    sample_size: int,
    log,
    meta: dict | None,
    job_id,
    get_contact_sample,
    set_contact_sample,
    log_activity,
) -> list:
    """Fetch and cache profiles for one audience stream."""
    cache_entry = get_contact_sample(slug, stream=stream)
    if cache_entry:
        display = cache_entry.get("display_name") or company
        fetched_at = cache_entry.get("fetched_at") or ""
        await log(
            f"Contact Sample Cache hit for '{display}' ({stream} stream, fetched {fetched_at}).", "info"
        )
        if job_id:
            log_activity(job_id, f"Contact Sample Cache hit · {display} ({stream} stream)")
        return cache_entry["profiles"]

    if not company_url:
        await log("No company URL (companyUrl) — skipping Apify.", "warning")
        if meta is not None:
            meta["empty_reason"] = "no_company_url"
        return []

    await log(f"Fetching up to {sample_size} profiles for '{company}' ({stream} stream, page 1)...", "info")
    if stream == "recruiters":
        items = await _run_apify_for_recruiters(company_url, log_func=log)
    elif stream == "russian":
        items = await _run_apify_for_russian_speakers(company_url, log_func=log)
    else:
        items = await _run_apify_actor(company_url, log_func=log)
    set_contact_sample(slug, items, display_name=company, stream=stream)
    return items
