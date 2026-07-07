"""Preflight slice resolution for Company Research."""

from __future__ import annotations

from src.db.company_research_cache import (
    get_company_research_cache,
    normalize_company_name,
    normalize_glassdoor_job_title,
)

SLICE_LABELS = {
    "companySearch": "Company search",
    "companyOverview": "Company overview",
    "companySalaries": "Salaries",
    "companyInterviews": "Interviews",
}

COMPANY_RESEARCH_LANES = frozenset({"matched", "accepted", "applied", "interviewing"})


def company_research_allowed(status: str, archived: bool = False) -> bool:
    return status in COMPANY_RESEARCH_LANES and not archived


def effective_glassdoor_job_title(
    listing_title: str,
    *,
    glassdoor_job_title: str | None = None,
    existing_research: dict | None = None,
) -> str:
    """Resolve the title used for cache keys and drawer labels."""
    if glassdoor_job_title and glassdoor_job_title.strip():
        return glassdoor_job_title.strip()
    if existing_research and existing_research.get("glassdoorJobTitle"):
        return str(existing_research["glassdoorJobTitle"]).strip()
    return (listing_title or "").strip()


def resolve_company_research_slices(
    company: str,
    listing_title: str,
    glassdoor_job_title: str | None = None,
    cache_row: dict | None = None,
) -> dict:
    title = (glassdoor_job_title or listing_title or "").strip() or listing_title
    title_key = normalize_glassdoor_job_title(title)
    company_key = normalize_company_name(company)
    cache_row = cache_row if cache_row is not None else get_company_research_cache(company_key)

    cached_slices: list[str] = []
    billable_slices: list[str] = []

    has_id = bool(cache_row and cache_row.get("glassdoorCompanyId"))
    has_overview = bool(
        cache_row
        and cache_row.get("companySize")
        and cache_row.get("rating") is not None
        and cache_row.get("reviewCount") is not None
    )
    salaries = (cache_row or {}).get("salariesByTitle") or {}
    interviews = (cache_row or {}).get("interviewsByTitle") or {}
    has_salary = title_key in salaries
    has_interviews = title_key in interviews

    if has_id:
        cached_slices.append("companySearch")
    else:
        billable_slices.append("companySearch")

    if has_overview:
        cached_slices.append("companyOverview")
    else:
        billable_slices.append("companyOverview")

    if has_salary:
        cached_slices.append("companySalaries")
    else:
        billable_slices.append("companySalaries")

    if has_interviews:
        cached_slices.append("companyInterviews")
    else:
        billable_slices.append("companyInterviews")

    estimated_runs = len(billable_slices)
    return {
        "company_key": company_key,
        "default_glassdoor_job_title": title,
        "glassdoor_job_title": title,
        "title_key": title_key,
        "cached_slices": cached_slices,
        "billable_slices": billable_slices,
        "estimated_runs": estimated_runs,
        "will_call_apify": estimated_runs > 0,
        "cache_row": cache_row,
    }


def slice_labels(slices: list[str]) -> list[str]:
    return [SLICE_LABELS.get(s, s) for s in slices]
