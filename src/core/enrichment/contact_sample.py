"""LinkedIn Scraper API integration: Contact Sample fetch via Apify."""

import os
import re
import time
import httpx
import asyncio
import inspect
from dotenv import load_dotenv


class ApifyTimeoutError(Exception):
    pass


class ApifyInfrastructureError(Exception):
    pass


APIFY_API_BASE = "https://api.apify.com/v2"
ACTOR_ID = "harvestapi~linkedin-company-employees"
CONTACT_SAMPLE_SIZE = 25
RECRUITER_SAMPLE_SIZE = 3
RECRUITER_FUNCTION_IDS = ["12"]
RUSSIAN_SAMPLE_SIZE = 5
RUSSIAN_SEARCH_QUERY = "Russian"
RUSSIAN_EXCLUDE_FUNCTION_IDS = ["12"]

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"
}
CANADA_PROVINCES = {"AB", "BC", "MB", "NB", "NL", "NS", "ON", "PE", "QC", "SK", "YT", "NT", "NU"}


def detect_country_from_location(location: str | None) -> str | None:
    """Return 'Canada' or 'United States' if detected in the location string.
    Returns None for 'Remote' or unrecognized locations.
    """
    if not location or location.lower() == "remote":
        return None

    loc_lower = location.lower()
    if "canada" in loc_lower:
        return "Canada"
    if "united states" in loc_lower or " usa" in loc_lower or " u.s.a" in loc_lower:
        return "United States"

    # Check for 2-letter codes (e.g. "Toronto, ON") — scan all matches, not just the first
    for match in re.finditer(r"\b([a-zA-Z]{2})\b", location):
        code = match.group(1).upper()
        if code in CANADA_PROVINCES:
            return "Canada"
        if code in US_STATES:
            return "United States"

    # Fallback to full province/state names if common
    if any(p in loc_lower for p in ["ontario", "quebec", "british columbia", "alberta"]):
        return "Canada"
    if any(s in loc_lower for s in ["california", "new york", "texas", "florida"]):
        return "United States"

    return None

_COMPANY_SUFFIXES = (
    "-technologies", "-technology", "-incorporated", "-corporation",
    "-holdings", "-international", "-solutions", "-services",
    "-inc", "-corp", "-llc", "-ltd", "-group", "-co",
)


def normalize_company_slug(company: str) -> str:
    """Return the primary LinkedIn company slug derived from a display name."""
    return company.lower().strip().replace(" ", "-").replace("_", "-")


def company_slug_candidates(company: str) -> list[str]:
    """Return ordered LinkedIn company slug variants to try for Apify lookup."""
    base = normalize_company_slug(company)
    if not base:
        return []

    candidates = [base]
    first = base.split("-", 1)[0]
    if first and first != base:
        candidates.append(first)

    for suffix in _COMPANY_SUFFIXES:
        if base.endswith(suffix):
            stripped = base[: -len(suffix)]
            if stripped and stripped not in candidates:
                candidates.append(stripped)

    return candidates


async def _fetch_apify_employees_at_url(
    company_url: str,
    *,
    label: str,
    log_func=None,
    timeout_seconds: float = 300.0,
    poll_interval: float = 5.0,
    start_page: int = 1,
    function_ids: list[str] | None = None,
    max_items: int | None = None,
    search_query: str | None = None,
    exclude_function_ids: list[str] | None = None,
    locations: list[str] | None = None,
    exclude_locations: list[str] | None = None,
) -> list:
    """Run Apify against one LinkedIn company page URL."""

    async def log(msg, level="info"):
        if log_func:
            if inspect.iscoroutinefunction(log_func):
                await log_func(msg, level)
            else:
                log_func(msg, level)

    load_dotenv(override=True)
    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        raise ApifyInfrastructureError("APIFY_API_TOKEN not set")

    actor_input = {
        "companies": [company_url],
        "maxItems": max_items if max_items is not None else CONTACT_SAMPLE_SIZE,
        "startPage": start_page,
    }
    if function_ids:
        actor_input["functionIds"] = function_ids
    if search_query:
        actor_input["searchQuery"] = search_query
    if exclude_function_ids:
        actor_input["excludeFunctionIds"] = exclude_function_ids
    if locations:
        actor_input["locations"] = locations
    if exclude_locations:
        actor_input["excludeLocations"] = exclude_locations

    run_url = f"{APIFY_API_BASE}/acts/{ACTOR_ID}/runs"
    params = {"token": api_token}
    headers = {"Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(run_url, params=params, headers=headers, json=actor_input)
        if resp.status_code not in (200, 201):
            await log(f"Apify trigger failed: HTTP {resp.status_code}", "error")
            raise ApifyInfrastructureError(f"Apify trigger failed: HTTP {resp.status_code}")

        run_id = resp.json().get("data", {}).get("id")
        if not run_id:
            raise ApifyInfrastructureError("Apify did not return a run ID.")

        await log(f"Apify run started: {run_id}", "info")

        status_url = f"{APIFY_API_BASE}/actor-runs/{run_id}"
        start_time = time.monotonic()
        last_status = None
        while True:
            if time.monotonic() - start_time >= timeout_seconds:
                raise ApifyTimeoutError(
                    f"Apify run {run_id} did not complete within {timeout_seconds}s"
                )
            await asyncio.sleep(poll_interval)
            status_resp = await client.get(status_url, params=params)
            if status_resp.status_code != 200:
                await log(f"Apify status check error: HTTP {status_resp.status_code}", "warning")
                continue

            run_data = status_resp.json().get("data", {})
            status = run_data.get("status")
            if status != last_status:
                await log(f"Apify run status: {status}", "info")
                last_status = status

            if status == "SUCCEEDED":
                dataset_id = run_data.get("defaultDatasetId")
                break
            if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                await log(f"Apify run ended with status: {status}", "error")
                raise ApifyInfrastructureError(f"Apify run ended with status: {status}")

        dataset_url = f"{APIFY_API_BASE}/datasets/{dataset_id}/items"
        data_resp = await client.get(dataset_url, params={**params, "format": "json"})
        if data_resp.status_code != 200:
            await log(f"Apify dataset fetch error: HTTP {data_resp.status_code}", "error")
            raise ApifyInfrastructureError(f"Apify dataset fetch error: HTTP {data_resp.status_code}")

        items = data_resp.json()
        await log(f"Apify returned {len(items)} employees for {label}.", "info")
        return items


async def _run_apify_for_slug(
    slug: str,
    log_func=None,
    timeout_seconds: float = 300.0,
    poll_interval: float = 5.0,
    start_page: int = 1,
) -> list:
    """Fetch up to CONTACT_SAMPLE_SIZE employees for one LinkedIn company slug via Apify."""
    company_url = f"https://www.linkedin.com/company/{slug}/"
    return await _fetch_apify_employees_at_url(
        company_url,
        label=f"slug '{slug}'",
        log_func=log_func,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
        start_page=start_page,
    )


async def _run_apify_for_company_page(
    company_url: str,
    log_func=None,
    timeout_seconds: float = 300.0,
    poll_interval: float = 5.0,
    start_page: int = 1,
    locations: list[str] | None = None,
) -> list:
    """Fetch employees using a Bright Data company page URL."""
    normalized = normalize_linkedin_company_url(company_url)
    if not normalized:
        return []
    slug = linkedin_company_slug_from_url(normalized)
    return await _fetch_apify_employees_at_url(
        normalized,
        label=f"company URL '{slug}'",
        log_func=log_func,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
        start_page=start_page,
        locations=locations,
    )


async def _run_apify_actor(
    company_url: str,
    log_func=None,
    timeout_seconds: float = 300.0,
    poll_interval: float = 5.0,
    start_page: int = 1,
    locations: list[str] | None = None,
) -> list:
    """Fetch employees via Apify using the LinkedIn company page URL only.

    Raises ApifyInfrastructureError for credential or API failures.
    Raises ApifyTimeoutError when local polling times out.
    Returns a (possibly empty) list on a successful Apify run.
    """
    if not company_url:
        raise ApifyInfrastructureError("No companyUrl provided for Apify fetch.")
    return await _run_apify_for_company_page(
        company_url,
        log_func=log_func,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
        start_page=start_page,
        locations=locations,
    )


async def _run_apify_for_recruiters(
    company_url: str,
    log_func=None,
    timeout_seconds: float = 300.0,
    poll_interval: float = 5.0,
    start_page: int = 1,
    locations: list[str] | None = None,
) -> list:
    """Fetch recruiter profiles via Apify using the HR function filter.

    Uses functionIds=["12"] (HR/Recruiting) and maxItems=RECRUITER_SAMPLE_SIZE.
    Raises ApifyInfrastructureError for credential or API failures.
    Raises ApifyTimeoutError when local polling times out.
    Returns a (possibly empty) list on a successful Apify run.
    """
    if not company_url:
        raise ApifyInfrastructureError("No companyUrl provided for Apify fetch.")
    normalized = normalize_linkedin_company_url(company_url)
    if not normalized:
        return []
    slug = linkedin_company_slug_from_url(normalized)
    return await _fetch_apify_employees_at_url(
        normalized,
        label=f"recruiters stream for '{slug}'",
        log_func=log_func,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
        start_page=start_page,
        function_ids=RECRUITER_FUNCTION_IDS,
        max_items=RECRUITER_SAMPLE_SIZE,
        locations=locations,
    )


async def _run_apify_for_russian_speakers(
    company_url: str,
    log_func=None,
    timeout_seconds: float = 300.0,
    poll_interval: float = 5.0,
    start_page: int = 1,
    locations: list[str] | None = None,
) -> list:
    """Fetch Russian-speaking profiles via Apify, excluding HR/Recruiters.

    Uses searchQuery="Russian", excludeFunctionIds=["12"] (HR/Recruiting), and maxItems=5.
    Raises ApifyInfrastructureError for credential or API failures.
    Raises ApifyTimeoutError when local polling times out.
    Returns a (possibly empty) list on a successful Apify run.
    """
    if not company_url:
        raise ApifyInfrastructureError("No companyUrl provided for Apify fetch.")
    normalized = normalize_linkedin_company_url(company_url)
    if not normalized:
        return []
    slug = linkedin_company_slug_from_url(normalized)
    return await _fetch_apify_employees_at_url(
        normalized,
        label=f"russian stream for '{slug}'",
        log_func=log_func,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
        start_page=start_page,
        search_query=RUSSIAN_SEARCH_QUERY,
        exclude_function_ids=RUSSIAN_EXCLUDE_FUNCTION_IDS,
        max_items=RUSSIAN_SAMPLE_SIZE,
        locations=locations,
    )


def company_cache_slug(company: str, company_url: str = "", country: str | None = None) -> str:
    """Return the cache key slug for a company's Contact Sample.
    Includes country suffix if provided (e.g. 'microsoft-canada').
    """
    slug = linkedin_company_slug_from_url(company_url)
    if not slug:
        slug = normalize_company_slug(company)

    if country:
        # Append normalized country to slug
        country_suffix = country.lower().replace(" ", "-")
        return f"{slug}-{country_suffix}"
    return slug


def normalize_linkedin_url(url: str) -> str:
    """Return the canonical /in/{slug} path from any LinkedIn profile URL."""
    if not url:
        return ""
    match = re.search(r'/in/([^/?#]+)', url)
    if match:
        return f"/in/{match.group(1)}"
    return ""


def linkedin_company_slug_from_url(url: str) -> str:
    """Return the /company/{slug} segment from a LinkedIn company page URL."""
    if not url:
        return ""
    match = re.search(r'/company/([^/?#]+)', url)
    return match.group(1) if match else ""


def normalize_linkedin_company_url(url: str) -> str:
    """Return a canonical LinkedIn company page URL without query params."""
    slug = linkedin_company_slug_from_url(url)
    if not slug:
        return ""
    return f"https://www.linkedin.com/company/{slug}/"


def poster_to_apify_item(poster: dict) -> dict:
    """Convert a Job Poster contact dict to an Apify-compatible item for batch classification."""
    name_parts = (poster.get("name") or "").split(None, 1)
    return {
        "firstName": name_parts[0] if name_parts else "",
        "lastName": name_parts[1] if len(name_parts) > 1 else "",
        "headline": poster.get("title") or "",
        "linkedinUrl": poster.get("url") or "",
        "currentPosition": poster.get("title") or "",
        "location": "",
        "languages": [],
    }


def resolve_load_more_streams(
    slug: str,
    settings: dict,
    company_url: str,
    get_contact_sample,
) -> dict:
    """Return billable streams and blocked_reason for Load More preflight/pipeline."""
    if not company_url:
        return {"billable_streams": [], "blocked_reason": "missing_company_url"}

    active_recruiters = settings.get("target_recruiters", True)
    active_russian = settings.get("target_russian_speakers", True)
    if not active_recruiters and not active_russian:
        return {"billable_streams": [], "blocked_reason": "no_audience_toggles"}

    stream_defs = [
        ("recruiters", "Recruiters", RECRUITER_SAMPLE_SIZE, active_recruiters),
        ("russian", "Russian Speakers", RUSSIAN_SAMPLE_SIZE, active_russian),
    ]

    billable_streams = []
    exhausted_count = 0
    active_count = 0

    for stream_key, stream_label, profile_count, is_active in stream_defs:
        if not is_active:
            continue
        active_count += 1
        cache = get_contact_sample(slug, stream=stream_key)
        if cache and cache.get("last_fetch_empty"):
            exhausted_count += 1
            continue
        page = (cache.get("pages_fetched", 0) + 1) if cache else 1
        billable_streams.append({
            "stream": stream_label,
            "profile_count": profile_count,
            "page": page,
            "stream_key": stream_key,
        })

    if billable_streams:
        return {"billable_streams": billable_streams, "blocked_reason": None}

    if exhausted_count == active_count and active_count > 0:
        return {"billable_streams": [], "blocked_reason": "all_streams_exhausted"}

    return {"billable_streams": [], "blocked_reason": None}
