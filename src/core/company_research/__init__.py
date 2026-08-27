"""Company Research package."""

from .glassdoor_intel import (
    GlassdoorInfrastructureError,
    GlassdoorIntelError,
    _pick_company_match,
    _summarize_interviews,
    build_job_company_research_snapshot,
    default_apify_runner,
    format_activity_log_message,
    normalize_salary_row,
    parse_overview_row,
)
from .preflight import (
    COMPANY_RESEARCH_LANES,
    company_research_allowed,
    resolve_company_research_slices,
    slice_labels,
)

__all__ = [
    "COMPANY_RESEARCH_LANES",
    "GlassdoorInfrastructureError",
    "GlassdoorIntelError",
    "_pick_company_match",
    "_summarize_interviews",
    "build_job_company_research_snapshot",
    "company_research_allowed",
    "default_apify_runner",
    "format_activity_log_message",
    "normalize_salary_row",
    "parse_overview_row",
    "resolve_company_research_slices",
    "slice_labels",
]
