"""Pre-Evaluation Filters — cheap non-LLM gates before Resume Matcher."""

from .remote_type import (
    ANY,
    HYBRID,
    IN_OFFICE,
    REMOTE,
    format_remote_type_rejection,
    normalize_allowed_remote_types,
    normalize_remote_type,
    passes_remote_type_filter,
    should_apply_remote_type_filter,
)

__all__ = [
    "ANY",
    "HYBRID",
    "IN_OFFICE",
    "REMOTE",
    "format_remote_type_rejection",
    "normalize_allowed_remote_types",
    "normalize_remote_type",
    "passes_remote_type_filter",
    "should_apply_remote_type_filter",
]
