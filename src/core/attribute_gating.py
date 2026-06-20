"""Post-evaluation attribute merge and gating for remote type and seniority."""

from .pre_evaluation.remote_type import (
    normalize_allowed_remote_types,
    normalize_remote_type,
    should_apply_remote_type_filter,
)

_VALID_SENIORITIES = frozenset({"junior", "mid", "senior"})


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


def merge_job_attributes(scraper_job: dict, evaluation: dict) -> dict:
    """Merge LLM-classified attributes with scraper fallbacks (per-field)."""
    remote_type = evaluation.get("remoteType") or scraper_job.get("remoteType") or ""
    seniority = evaluation.get("seniority") or scraper_job.get("seniority") or ""
    return {
        "remoteType": normalize_remote_type(remote_type),
        "seniority": _normalize_seniority(seniority),
    }


def passes_attribute_gate(
    remote_type: str,
    seniority: str,
    allowed_remote_types: list | None,
    seniorities: str | list | None,
) -> bool:
    """Return True when merged attributes match search preferences."""
    normalized_remote = normalize_remote_type(remote_type)
    normalized_seniority = _normalize_seniority(seniority)

    if should_apply_remote_type_filter(allowed_remote_types):
        allowed = normalize_allowed_remote_types(allowed_remote_types)
        if normalized_remote not in allowed:
            return False

    if _should_apply_seniority_filter(seniorities):
        allowed_seniorities = _parse_seniorities(seniorities)
        if normalized_seniority not in allowed_seniorities:
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
) -> str:
    """Format a Task Log line for an attribute gate rejection."""
    reasons = []
    normalized_remote = normalize_remote_type(remote_type)
    normalized_seniority = _normalize_seniority(seniority)

    if should_apply_remote_type_filter(allowed_remote_types):
        allowed = normalize_allowed_remote_types(allowed_remote_types)
        if normalized_remote not in allowed:
            reasons.append(f"remote type '{normalized_remote}' not in {allowed}")

    if _should_apply_seniority_filter(seniorities):
        allowed_seniorities = _parse_seniorities(seniorities)
        if normalized_seniority not in allowed_seniorities:
            reasons.append(f"seniority '{normalized_seniority}' not in {allowed_seniorities}")

    reason_text = "; ".join(reasons) if reasons else "attribute mismatch"
    return f"Attribute mismatch: '{title}' at '{company}' — {reason_text}"


def is_unclassified(evaluation: dict) -> bool:
    """True when the Resume Matcher fully failed (empty result)."""
    return not evaluation
