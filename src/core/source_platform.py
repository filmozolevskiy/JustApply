"""Source Platform values for the Search & Evaluation Pipeline scrape phase.

v1 ships Bright Data LinkedIn and Apify LinkedIn. Reserved boards (Indeed /
Glassdoor) are rejected with a clear unsupported error — never silently fall
through to Bright Data.
"""

from __future__ import annotations

BRIGHTDATA_LINKEDIN = "brightdata_linkedin"
APIFY_LINKEDIN = "apify_linkedin"
APIFY_INDEED = "apify_indeed"
APIFY_GLASSDOOR = "apify_glassdoor"

DEFAULT_SOURCE_PLATFORM = BRIGHTDATA_LINKEDIN

# Platforms the scrape dispatcher can run today.
SUPPORTED_SOURCE_PLATFORMS = frozenset({BRIGHTDATA_LINKEDIN, APIFY_LINKEDIN})

# Known future options — named in errors so callers know they are reserved, not typos.
RESERVED_SOURCE_PLATFORMS = frozenset({APIFY_INDEED, APIFY_GLASSDOOR})


class UnsupportedSourcePlatformError(ValueError):
    """Raised when a Source Platform value is not wired for scrape dispatch."""


def validate_source_platform(platform: str | None) -> str:
    """Return a normalized supported platform, or raise UnsupportedSourcePlatformError."""
    if platform is None or (isinstance(platform, str) and not platform.strip()):
        return DEFAULT_SOURCE_PLATFORM

    normalized = platform.strip()
    if normalized in SUPPORTED_SOURCE_PLATFORMS:
        return normalized

    if normalized in RESERVED_SOURCE_PLATFORMS:
        raise UnsupportedSourcePlatformError(
            f"Source Platform {normalized!r} is not supported yet "
            f"(reserved for a later slice). Supported: {sorted(SUPPORTED_SOURCE_PLATFORMS)}."
        )

    raise UnsupportedSourcePlatformError(
        f"Source Platform {normalized!r} is unsupported. "
        f"Supported: {sorted(SUPPORTED_SOURCE_PLATFORMS)}."
    )
