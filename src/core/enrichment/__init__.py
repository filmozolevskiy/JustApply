"""Enrichment: Contact Sample sourcing, classification, and Connection Note generation."""

from .connection_note import (
    FIT_LINE,
    RECRUITER_CTA,
    RUSSIAN_SPEAKER_CTA,
    generate_connection_note_template,
    generate_outreach_templates,
    minimal_fallback_template,
)
from .classifier import classify_contacts, normalize_apify_employee, _normalize_apify_employee
from .contact_sample import (
    ApifyTimeoutError,
    CONTACT_SAMPLE_SIZE,
    _fetch_apify_employees_at_url,
    _run_apify_actor,
    _run_apify_for_company_page,
    _run_apify_for_slug,
    company_cache_slug,
    company_slug_candidates,
    linkedin_company_slug_from_url,
    normalize_company_slug,
    normalize_linkedin_company_url,
    normalize_linkedin_url,
    poster_to_apify_item,
)
from .source import source_contacts

__all__ = [
    "FIT_LINE",
    "RECRUITER_CTA",
    "RUSSIAN_SPEAKER_CTA",
    "ApifyTimeoutError",
    "CONTACT_SAMPLE_SIZE",
    "classify_contacts",
    "company_cache_slug",
    "company_slug_candidates",
    "generate_connection_note_template",
    "generate_outreach_templates",
    "linkedin_company_slug_from_url",
    "minimal_fallback_template",
    "normalize_apify_employee",
    "normalize_company_slug",
    "normalize_linkedin_company_url",
    "normalize_linkedin_url",
    "poster_to_apify_item",
    "source_contacts",
    "_fetch_apify_employees_at_url",
    "_normalize_apify_employee",
    "_run_apify_actor",
    "_run_apify_for_company_page",
    "_run_apify_for_slug",
]
