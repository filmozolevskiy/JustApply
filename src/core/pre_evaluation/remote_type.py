"""Remote-type normalization and Pre-Evaluation Filter gating."""

REMOTE = "remote"
HYBRID = "hybrid"
IN_OFFICE = "in_office"
ANY = "any"

_IN_OFFICE_ALIASES = frozenset({"in office", "in-office", "in_office", "onsite", "on-site", "on site"})


def normalize_remote_type(value: str) -> str:
    """Map scraper/UI variants to canonical remoteType values."""
    normalized = (value or "").lower().strip().replace("-", " ")
    if normalized in _IN_OFFICE_ALIASES:
        return IN_OFFICE
    if normalized == HYBRID:
        return HYBRID
    if normalized == REMOTE:
        return REMOTE
    return normalized.replace(" ", "_") if normalized else ""


def normalize_allowed_remote_types(allowed_remote_types: list | None) -> list[str]:
    """Normalize search-run remote preferences for filter comparisons."""
    return [normalize_remote_type(t) for t in (allowed_remote_types or []) if t]


def should_apply_remote_type_filter(allowed_remote_types: list | None) -> bool:
    allowed = normalize_allowed_remote_types(allowed_remote_types)
    return bool(allowed) and ANY not in allowed


def passes_remote_type_filter(job: dict, allowed_remote_types: list | None) -> bool:
    """Return True when job survives remote-type Pre-Evaluation Filter."""
    if not should_apply_remote_type_filter(allowed_remote_types):
        return True
    allowed = normalize_allowed_remote_types(allowed_remote_types)
    job_remote_type = normalize_remote_type(job.get("remoteType") or "")
    return job_remote_type in allowed


def format_remote_type_rejection(
    title: str,
    company: str,
    job: dict,
    allowed_remote_types: list | None,
) -> str:
    allowed = normalize_allowed_remote_types(allowed_remote_types)
    job_remote_type = normalize_remote_type(job.get("remoteType") or "")
    return (
        f"Pre-filter: '{title}' at '{company}' — "
        f"remote type '{job_remote_type}' not in {allowed}"
    )
