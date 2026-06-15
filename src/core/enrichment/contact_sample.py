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


APIFY_API_BASE = "https://api.apify.com/v2"
ACTOR_ID = "harvestapi~linkedin-company-employees"
CONTACT_SAMPLE_SIZE = 25

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
        await log("APIFY_API_TOKEN not set, skipping Apify sourcing.", "warning")
        return []

    actor_input = {"companies": [company_url], "maxItems": CONTACT_SAMPLE_SIZE}

    run_url = f"{APIFY_API_BASE}/acts/{ACTOR_ID}/runs"
    params = {"token": api_token}
    headers = {"Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(run_url, params=params, headers=headers, json=actor_input)
        if resp.status_code not in (200, 201):
            await log(f"Apify trigger failed: HTTP {resp.status_code}", "error")
            return []

        run_id = resp.json().get("data", {}).get("id")
        if not run_id:
            await log("Apify did not return a run ID.", "error")
            return []

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
                return []

        dataset_url = f"{APIFY_API_BASE}/datasets/{dataset_id}/items"
        data_resp = await client.get(dataset_url, params={**params, "format": "json"})
        if data_resp.status_code != 200:
            await log(f"Apify dataset fetch error: HTTP {data_resp.status_code}", "error")
            return []

        items = data_resp.json()
        await log(f"Apify returned {len(items)} employees for {label}.", "info")
        return items


async def _run_apify_for_slug(
    slug: str,
    log_func=None,
    timeout_seconds: float = 300.0,
    poll_interval: float = 5.0,
) -> list:
    """Fetch up to CONTACT_SAMPLE_SIZE employees for one LinkedIn company slug via Apify."""
    company_url = f"https://www.linkedin.com/company/{slug}/"
    return await _fetch_apify_employees_at_url(
        company_url,
        label=f"slug '{slug}'",
        log_func=log_func,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
    )


async def _run_apify_for_company_page(
    company_url: str,
    log_func=None,
    timeout_seconds: float = 300.0,
    poll_interval: float = 5.0,
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
    )


async def _run_apify_actor(
    company: str,
    log_func=None,
    timeout_seconds: float = 300.0,
    poll_interval: float = 5.0,
    company_url: str | None = None,
) -> list:
    """Fetch employees via Apify, preferring Bright Data company_url then slug variants."""

    async def log(msg, level="info"):
        if log_func:
            if inspect.iscoroutinefunction(log_func):
                await log_func(msg, level)
            else:
                log_func(msg, level)

    if company_url:
        try:
            items = await _run_apify_for_company_page(
                company_url,
                log_func=log_func,
                timeout_seconds=timeout_seconds,
                poll_interval=poll_interval,
            )
        except ApifyTimeoutError:
            raise
        if items:
            return items
        await log("No employees at Bright Data company URL; trying name-based slug variants.", "info")

    candidates = company_slug_candidates(company)
    if not candidates:
        await log("No company name for Apify sourcing.", "warning")
        return []

    last_error = None
    for slug in candidates:
        try:
            items = await _run_apify_for_slug(
                slug,
                log_func=log_func,
                timeout_seconds=timeout_seconds,
                poll_interval=poll_interval,
            )
        except ApifyTimeoutError as exc:
            last_error = exc
            raise
        if items:
            if slug != candidates[0]:
                await log(f"Resolved LinkedIn company slug '{slug}' for '{company}'.", "info")
            return items
        if len(candidates) > 1:
            await log(f"No employees for slug '{slug}'; trying next variant.", "info")

    if last_error:
        raise last_error
    return []


def company_cache_slug(company: str, company_url: str = "") -> str:
    """Return the cache key slug for a company's Contact Sample."""
    slug = linkedin_company_slug_from_url(company_url)
    if slug:
        return slug
    return normalize_company_slug(company)


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
