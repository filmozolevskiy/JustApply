"""Post-evaluation attribute merge and gating for remote type, seniority, Employment Type, Salary Min."""

from .pre_evaluation.remote_type import (
    normalize_allowed_remote_types,
    normalize_remote_type,
    should_apply_remote_type_filter,
)
from .scraper import parse_employment_types

_VALID_SENIORITIES = frozenset({"junior", "mid", "senior"})
_VALID_EMPLOYMENT_TYPES = frozenset({
    "Full-time",
    "Contract",
    "Part-time",
    "Temporary",
    "Volunteer",
})
_EMPLOYMENT_TYPE_BY_LOWER = {t.lower(): t for t in _VALID_EMPLOYMENT_TYPES}


def _parse_seniorities(seniorities: str | list | None) -> list[str]:
    if seniorities is None:
        return ["any"]
    if isinstance(seniorities, str):
        parsed = [s.strip().lower() for s in seniorities.split(",") if s.strip()]
        return parsed or ["any"]
    return [s.strip().lower() for s in seniorities if s.strip()] or ["any"]


def _should_apply_seniority_filter(seniorities: str | list | None) -> bool:
    allowed = _parse_seniorities(seniorities)
    return bool(allowed) and "any" not in allowed


def _normalize_seniority(value: str) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in _VALID_SENIORITIES else normalized


def _normalize_employment_type(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    return _EMPLOYMENT_TYPE_BY_LOWER.get(raw.lower(), raw)


def _should_apply_employment_type_filter(employment_types: str | list | None) -> bool:
    allowed = parse_employment_types(employment_types)
    return bool(allowed) and "any" not in allowed


def _should_apply_salary_min_filter(salary_min: int | None) -> bool:
    return salary_min is not None


def _passes_salary_min_gate(annual_max: int | None, salary_min: int | None) -> bool:
    """ADR 0014: pass when Min unset, band missing, or annualMax ≥ Min."""
    if not _should_apply_salary_min_filter(salary_min):
        return True
    if annual_max is None:
        return True
    return int(annual_max) >= int(salary_min)


def merge_job_attributes(scraper_job: dict, evaluation: dict) -> dict:
    """Merge LLM-classified attributes with scraper fallbacks (per-field)."""
    remote_type = evaluation.get("remoteType") or scraper_job.get("remoteType") or ""
    seniority = evaluation.get("seniority") or scraper_job.get("seniority") or ""
    employment_type = (
        evaluation.get("employmentType") or scraper_job.get("employmentType") or ""
    )
    return {
        "remoteType": normalize_remote_type(remote_type),
        "seniority": _normalize_seniority(seniority),
        "employmentType": _normalize_employment_type(employment_type),
    }


def passes_attribute_gate(
    remote_type: str,
    seniority: str,
    allowed_remote_types: list | None,
    seniorities: str | list | None,
    employment_type: str = "",
    employment_types: str | list | None = "any",
    *,
    annual_max: int | None = None,
    annual_min: int | None = None,
    salary_min: int | None = None,
) -> bool:
    """Return True when merged attributes match search preferences.

    ``annual_min`` is accepted for call-site clarity but Salary Min gates on
    ``annual_max`` only (ADR 0014).
    """
    del annual_min  # Gate uses annualMax only; param kept for readable call sites.
    normalized_remote = normalize_remote_type(remote_type)
    normalized_seniority = _normalize_seniority(seniority)
    normalized_employment = _normalize_employment_type(employment_type)

    if should_apply_remote_type_filter(allowed_remote_types):
        allowed = normalize_allowed_remote_types(allowed_remote_types)
        if normalized_remote not in allowed:
            return False

    if _should_apply_seniority_filter(seniorities):
        allowed_seniorities = _parse_seniorities(seniorities)
        if normalized_seniority not in allowed_seniorities:
            return False

    if _should_apply_employment_type_filter(employment_types):
        allowed_employment = parse_employment_types(employment_types)
        if normalized_employment not in allowed_employment:
            return False

    if not _passes_salary_min_gate(annual_max, salary_min):
        return False

    return True


def format_attribute_mismatch(
    title: str,
    company: str,
    *,
    remote_type: str,
    seniority: str,
    allowed_remote_types: list | None,
    seniorities: str | list | None,
    employment_type: str = "",
    employment_types: str | list | None = "any",
    annual_max: int | None = None,
    annual_min: int | None = None,
    salary_min: int | None = None,
) -> str:
    """Format a Task Log line for an attribute gate rejection."""
    del annual_min
    reasons = []
    normalized_remote = normalize_remote_type(remote_type)
    normalized_seniority = _normalize_seniority(seniority)
    normalized_employment = _normalize_employment_type(employment_type)

    if should_apply_remote_type_filter(allowed_remote_types):
        allowed = normalize_allowed_remote_types(allowed_remote_types)
        if normalized_remote not in allowed:
            reasons.append(f"remote type '{normalized_remote}' not in {allowed}")

    if _should_apply_seniority_filter(seniorities):
        allowed_seniorities = _parse_seniorities(seniorities)
        if normalized_seniority not in allowed_seniorities:
            reasons.append(f"seniority '{normalized_seniority}' not in {allowed_seniorities}")

    if _should_apply_employment_type_filter(employment_types):
        allowed_employment = parse_employment_types(employment_types)
        if normalized_employment not in allowed_employment:
            reasons.append(
                f"employment type '{normalized_employment or 'unknown'}' "
                f"not in {allowed_employment}"
            )

    if not _passes_salary_min_gate(annual_max, salary_min):
        reasons.append(
            f"salary annualMax {annual_max} below Salary Min {salary_min}"
        )

    reason_text = "; ".join(reasons) if reasons else "attribute mismatch"
    return f"Attribute mismatch: '{title}' at '{company}' — {reason_text}"


def is_unclassified(evaluation: dict) -> bool:
    """True when the Resume Matcher fully failed (empty result)."""
    return not evaluation
