"""Enrichment orchestration: Contact Sample sourcing with cache and classification."""

import inspect

from .contact_sample import (
    CONTACT_SAMPLE_SIZE,
    _run_apify_actor,
    company_cache_slug,
    normalize_linkedin_url,
    poster_to_apify_item,
    ApifyTimeoutError,
)
from .classifier import classify_contacts


async def source_contacts(job: dict, settings=None, log_func=None, bust_cache: bool = False, meta: dict | None = None) -> list:
    """
    Return outreach contacts for a job using LLM classification.

    Checks the Contact Sample Cache first. On cache miss, fetches via Apify and
    writes the result to cache when non-empty. On cache hit, skips the Apify call.
    The Job Poster from existing contacts is included in the same classification
    batch — deduped by normalized LinkedIn URL or injected as a synthetic extra
    when absent. Falls back to classifying the poster alone if no profiles are
    available. Preserves contacted:True from previous contacts matched by
    normalized URL. bust_cache=True deletes the cache entry before lookup.
    """
    from ...schemas import OutreachSettings
    from ...db.cache import get_contact_sample, set_contact_sample, delete_contact_sample
    from ...db.jobs import log_activity

    if settings is None:
        settings = OutreachSettings()

    async def log(msg, level="info"):
        if log_func:
            if inspect.iscoroutinefunction(log_func):
                await log_func(msg, level)
            else:
                log_func(msg, level)

    existing = job.get("contacts") or []
    job_poster = next((c for c in existing if c.get("is_job_poster")), None)
    contacted_by_slug = {
        normalize_linkedin_url(c.get("url", "")): c.get("contacted", False)
        for c in existing
        if normalize_linkedin_url(c.get("url", ""))
    }

    company = job.get("company") or ""
    company_url = job.get("companyUrl") or ""
    if not company:
        await log("No company name for Apify sourcing.", "warning")
        return []

    slug = company_cache_slug(company, company_url)

    if bust_cache:
        delete_contact_sample(slug)

    cache_entry = get_contact_sample(slug)
    if cache_entry:
        display = cache_entry.get("display_name") or company
        fetched_at = cache_entry.get("fetched_at") or ""
        await log(f"Contact Sample Cache hit for '{display}' (fetched {fetched_at}).", "info")
        job_id = job.get("id")
        if job_id:
            log_activity(job_id, f"Contact Sample Cache hit · {display}")
        items = cache_entry["profiles"]
    else:
        await log(f"Fetching up to {CONTACT_SAMPLE_SIZE} employees for '{company}'...", "info")
        try:
            items = await _run_apify_actor(
                company,
                log_func=log_func,
                company_url=company_url or None,
            )
        except ApifyTimeoutError as e:
            await log(f"Apify polling timed out: {e}", "error")
            items = []
        if items:
            set_contact_sample(slug, items, display_name=company)

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

    if meta is not None and not contacts:
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
