"""Apify LinkedIn job-listing scrape via curious_coder/linkedin-jobs-scraper.

Normalizes Actor rows into the same Job shape as Bright Data, then applies the
shared company-size / Employment Type post-filters. Injectable runner keeps
tests free of live Actor HTTP.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from .pre_evaluation import normalize_remote_type
from .scraper import match_company_size, match_employment_type, parse_employment_types

APIFY_API_BASE = "https://api.apify.com/v2"
# Apify API path form of curious_coder/linkedin-jobs-scraper
ACTOR_ID = "curious_coder~linkedin-jobs-scraper"
# Per-region client poll budget. Live run 6KVBJoYhRI5tpkEuq SUCCEEDED in ~455s
# with Actor default scrapeCompany=true; Bright Data waits 10 minutes.
APIFY_LINKEDIN_RUN_TIMEOUT_SECONDS = 900.0
# Max concurrent Actor runs across Search Regions (env override allowed).
APIFY_LINKEDIN_MAX_CONCURRENT_RUNS_DEFAULT = 5
_APIFY_LINKEDIN_MAX_CONCURRENT_RUNS_ENV = "APIFY_LINKEDIN_MAX_CONCURRENT_RUNS"

# Board time_range → Actor datePosted enum (LinkedIn still supports these as URL filters).
_DATE_POSTED_BY_TIME_RANGE = {
    "any": "anyTime",
    "anytime": "anyTime",
    "past_24_hours": "past24Hours",
    "past 24 hours": "past24Hours",
    "past_week": "pastWeek",
    "past week": "pastWeek",
    "past_month": "pastMonth",
    "past month": "pastMonth",
}

ApifyLinkedInRunner = Callable[..., Awaitable[list[dict[str, Any]]]]


class ApifyLinkedInScrapeError(Exception):
    """Raised when an Apify LinkedIn listing run cannot complete."""


def resolve_apify_linkedin_max_concurrent_runs(
    env: dict[str, str] | None = None,
) -> int:
    """Return concurrency cap for parallel Search Region Actor runs (min 1)."""
    source = env if env is not None else os.environ
    raw = source.get(_APIFY_LINKEDIN_MAX_CONCURRENT_RUNS_ENV)
    if raw is None or str(raw).strip() == "":
        return APIFY_LINKEDIN_MAX_CONCURRENT_RUNS_DEFAULT
    try:
        value = int(str(raw).strip())
    except ValueError:
        return APIFY_LINKEDIN_MAX_CONCURRENT_RUNS_DEFAULT
    return max(1, value)


def map_time_range_to_date_posted(time_range: str | None) -> str:
    """Map board/Bright Data time_range values to Actor datePosted enum."""
    if not time_range:
        return "anyTime"
    normalized = str(time_range).strip().lower().replace("-", " ").replace("_", " ")
    compact = normalized.replace(" ", "_")
    return _DATE_POSTED_BY_TIME_RANGE.get(
        compact,
        _DATE_POSTED_BY_TIME_RANGE.get(normalized, "anyTime"),
    )


def _keyword_filter_terms(
    *,
    remote_types: list[str] | None,
    seniorities: list[str] | None,
    employment_types: list[str] | None,
) -> list[str]:
    """Terms LinkedIn no longer exposes as URL filters — fold into keywords."""
    terms: list[str] = []

    remotes = [str(t).strip().lower() for t in (remote_types or []) if t]
    if remotes and "any" not in remotes:
        for remote in remotes:
            if remote == "in_office":
                terms.append("on-site")
            else:
                terms.append(remote)

    seniors = [str(s).strip().lower() for s in (seniorities or []) if s]
    if seniors and "any" not in seniors:
        for seniority in seniors:
            if seniority == "mid":
                terms.append("mid-level")
            else:
                terms.append(seniority)

    # Bright Data only sends job_type when exactly one Employment Type is selected.
    employments = [str(e).strip() for e in (employment_types or []) if e]
    employments = [e for e in employments if e.lower() != "any"]
    if len(employments) == 1:
        terms.append(employments[0])

    return terms


def build_apify_linkedin_actor_input(
    *,
    keywords: str,
    location: str,
    limit_per_source: int,
    time_range: str | None = "any",
    remote_types: list[str] | None = None,
    seniorities: list[str] | None = None,
    employment_types: list[str] | None = None,
) -> dict[str, Any]:
    """Build Actor input for one Search Region.

    Explicitly sets scrapeCompany=False: the Actor schema defaults it to True,
    which adds per-job company HTTP (slower). PPE is still $0.001 per dataset
    result either way — company scrape is not a separate charge event.

    datePosted is a real LinkedIn AI-search URL filter. Experience / job type /
    workplace were removed as separate LinkedIn filters (Aug 2026); we append
    selected board prefs into keywords (Actor's autoConvertToAiSearch pattern).
    """
    extra = _keyword_filter_terms(
        remote_types=remote_types,
        seniorities=seniorities,
        employment_types=employment_types,
    )
    query = str(keywords or "").strip()
    if extra:
        query = " ".join([query, *extra]).strip() if query else " ".join(extra)

    return {
        "keywords": query,
        "location": location,
        "limitPerSource": limit_per_source,
        "datePosted": map_time_range_to_date_posted(time_range),
        "scrapeCompany": False,
        "autoConvertToAiSearch": True,
    }


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text).strip()


def _derive_remote_type(row: dict[str, Any]) -> str:
    workplace = row.get("workplaceTypes") or row.get("workplaceType") or []
    if isinstance(workplace, str):
        tokens = [workplace]
    elif isinstance(workplace, list):
        tokens = [str(t) for t in workplace]
    else:
        tokens = []
    joined = " ".join(tokens).lower()
    location = str(row.get("location") or "").lower()

    if "remote" in joined or "remote" in location:
        return normalize_remote_type("remote")
    if "hybrid" in joined or "hybrid" in location:
        return normalize_remote_type("hybrid")
    if joined or location:
        return normalize_remote_type("in_office")
    return normalize_remote_type("")


def _derive_seniority(title: str, seniority_level: str) -> str:
    title_lower = (title or "").lower()
    raw = (seniority_level or "").lower()
    haystack = f"{raw} {title_lower}"
    if any(
        term in haystack
        for term in ("sr", "senior", "lead", "principal", "staff", "manager", "director", "mid-senior")
    ):
        return "senior"
    if any(term in haystack for term in ("jr", "junior", "entry", "intern", "associate")):
        return "junior"
    return "mid"


def _format_salary(row: dict[str, Any]) -> str:
    salary = row.get("salary")
    if isinstance(salary, str) and salary.strip():
        return salary.strip()
    if isinstance(salary, int | float):
        return str(salary)

    info = row.get("salaryInfo")
    if isinstance(info, str) and info.strip():
        return info.strip()
    if isinstance(info, list):
        parts = [str(p).strip() for p in info if p not in (None, "")]
        return " - ".join(parts) if parts else ""
    if isinstance(info, dict):
        return str(info.get("text") or info.get("salary") or "").strip()
    return ""


def _format_size(row: dict[str, Any]) -> str:
    size = row.get("companyEmployeesCount")
    if size is None or size == "":
        return ""
    return str(size)


def _format_date(row: dict[str, Any]) -> str:
    posted = row.get("postedAt")
    if isinstance(posted, str) and posted.strip():
        return posted.strip()
    ts = row.get("postedAtTimestamp")
    if ts is None or ts == "":
        return ""
    return str(ts)


def normalize_apify_linkedin_job(row: dict[str, Any]) -> dict:
    """Map a curious_coder LinkedIn Actor row into the Bright Data–equivalent Job shape."""
    if not isinstance(row, dict):
        row = {}

    title = str(row.get("title") or "").strip()
    company = str(row.get("companyName") or row.get("company") or "").strip()
    company_url = str(row.get("companyLinkedinUrl") or row.get("companyUrl") or "").strip()
    link = str(row.get("link") or row.get("url") or "").strip()
    location = str(row.get("location") or "").strip()
    employment_type = str(row.get("employmentType") or "").strip()
    description = str(row.get("descriptionText") or "").strip()
    if not description:
        description = _strip_html(str(row.get("descriptionHtml") or ""))

    seniority_level = str(row.get("seniorityLevel") or row.get("seniority") or "")
    seniority = _derive_seniority(title, seniority_level)
    remote_type = _derive_remote_type(row)

    contacts: list[dict[str, Any]] = []
    poster_name = row.get("jobPosterName")
    poster_url = row.get("jobPosterProfileUrl")
    if poster_name or poster_url:
        contacts.append(
            {
                "name": str(poster_name or "").strip(),
                "title": str(row.get("jobPosterTitle") or "Recruiter").strip() or "Recruiter",
                "url": str(poster_url or "").strip(),
                "contacted": False,
                "russian_speaker": False,
                "is_job_poster": True,
            }
        )

    return {
        "title": title,
        "company": company,
        "companyUrl": company_url,
        "size": _format_size(row),
        "link": link,
        "date": _format_date(row),
        "location": location,
        "remoteType": remote_type,
        "seniority": seniority,
        "employmentType": employment_type,
        "salary": _format_salary(row),
        "description": description,
        "status": "scraped",
        "contacts": contacts,
    }


async def run_apify_linkedin_actor(
    client: Any,
    *,
    api_token: str,
    actor_input: dict[str, Any],
    timeout_seconds: float = APIFY_LINKEDIN_RUN_TIMEOUT_SECONDS,
    poll_interval: float = 5.0,
) -> list[dict[str, Any]]:
    """Start one Actor run, poll to completion, return dataset items."""
    run_url = f"{APIFY_API_BASE}/acts/{ACTOR_ID}/runs"
    params = {"token": api_token}
    headers = {"Content-Type": "application/json"}

    resp = await client.post(run_url, params=params, headers=headers, json=actor_input)
    if resp.status_code not in (200, 201):
        raise ApifyLinkedInScrapeError(
            f"Apify LinkedIn trigger failed: HTTP {resp.status_code} — {resp.text[:300]}"
        )

    run_id = resp.json().get("data", {}).get("id")
    if not run_id:
        raise ApifyLinkedInScrapeError("Apify LinkedIn did not return a run ID.")

    status_url = f"{APIFY_API_BASE}/actor-runs/{run_id}"
    start_time = time.monotonic()
    dataset_id: str | None = None

    while True:
        if time.monotonic() - start_time >= timeout_seconds:
            raise ApifyLinkedInScrapeError(
                f"Apify LinkedIn run {run_id} timed out after {timeout_seconds}s"
            )

        await asyncio.sleep(poll_interval)
        status_resp = await client.get(status_url, params=params)
        if status_resp.status_code != 200:
            continue

        run_data = status_resp.json().get("data", {})
        status = run_data.get("status")
        if status == "SUCCEEDED":
            dataset_id = run_data.get("defaultDatasetId")
            break
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            raise ApifyLinkedInScrapeError(f"Apify LinkedIn run {run_id} ended with status: {status}")

    if not dataset_id:
        raise ApifyLinkedInScrapeError("Apify LinkedIn run succeeded but returned no dataset ID.")

    dataset_url = f"{APIFY_API_BASE}/datasets/{dataset_id}/items"
    data_resp = await client.get(dataset_url, params={**params, "format": "json"})
    if data_resp.status_code != 200:
        raise ApifyLinkedInScrapeError(
            f"Apify LinkedIn dataset fetch failed: HTTP {data_resp.status_code}"
        )

    items = data_resp.json()
    if not isinstance(items, list):
        raise ApifyLinkedInScrapeError("Apify LinkedIn dataset response was not a JSON list.")
    return items


async def default_apify_linkedin_runner(
    *,
    actor_input: dict[str, Any],
) -> list[dict[str, Any]]:
    """Live Actor runner: one call for one Search Region."""
    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        raise ApifyLinkedInScrapeError("APIFY_API_TOKEN not set in .env")

    async with httpx.AsyncClient(timeout=120.0) as client:
        return await run_apify_linkedin_actor(
            client,
            api_token=api_token,
            actor_input=actor_input,
            timeout_seconds=APIFY_LINKEDIN_RUN_TIMEOUT_SECONDS,
        )


async def _scrape_apify_linkedin_mock(query: str, location: str, log) -> list[dict[str, Any]]:
    await log("Initializing Apify LinkedIn Mock API...", "info")
    await asyncio.sleep(0.05)
    await log(f"Mock Apify LinkedIn scrape for '{query}' in '{location}'", "info")
    return [
        {
            "title": f"Senior {query}",
            "companyName": "ScaleLabs Inc.",
            "companyLinkedinUrl": "https://www.linkedin.com/company/scalelabs",
            "companyEmployeesCount": 750,
            "link": "https://linkedin.com/jobs/apify-mock-991",
            "postedAt": "2026-06-07",
            "location": location,
            "employmentType": "Full-time",
            "salary": "$145k - $175k",
            "descriptionText": (
                f"We are seeking a senior practitioner in {query} to lead our "
                "automation pipelines. Remote friendly."
            ),
            "seniorityLevel": "senior",
            "workplaceTypes": ["Remote"],
            "jobPosterName": "Sarah Jenkins",
            "jobPosterTitle": "Recruiting Director",
            "jobPosterProfileUrl": "https://linkedin.com/in/sarah-jenkins-mocked",
        },
        {
            "title": f"Lead {query} Developer",
            "companyName": "BrightFlow Co.",
            "companyLinkedinUrl": "https://www.linkedin.com/company/brightflow",
            "companyEmployeesCount": 150,
            "link": "https://linkedin.com/jobs/apify-mock-992",
            "postedAt": "2026-06-07",
            "location": location,
            "employmentType": "Contract",
            "salary": "$160k - $190k",
            "descriptionText": f"Lead development for {query} streams.",
            "seniorityLevel": "senior",
            "workplaceTypes": ["Hybrid"],
        },
        {
            "title": f"Junior {query} Assistant",
            "companyName": "WebStart LLC",
            "companyEmployeesCount": 25,
            "link": "https://linkedin.com/jobs/apify-mock-993",
            "postedAt": "2026-06-07",
            "location": "San Francisco, CA",
            "employmentType": "Part-time",
            "salary": "$70k - $90k",
            "descriptionText": f"Entry level tasks regarding {query}.",
            "seniorityLevel": "junior",
            "workplaceTypes": ["On-site"],
        },
    ]


async def _scrape_apify_linkedin_regions_parallel(
    *,
    query: str,
    search_regions: list[tuple[str, str]],
    per_region_limit: int,
    time_range: str,
    remote_types: list | None,
    seniorities: list | None,
    employment_types: list | None,
    runner: ApifyLinkedInRunner,
    log,
    max_concurrent: int,
) -> list[dict[str, Any]]:
    """Run one Actor call per Search Region with a concurrency cap.

    Keeps results when at least one region succeeds; raises only if all fail.
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    total = len(search_regions)
    successes = 0
    failures: list[tuple[str, str]] = []
    raw_jobs: list[dict[str, Any]] = []
    collect_lock = asyncio.Lock()

    async def run_one(region_label: str) -> None:
        nonlocal successes
        actor_input = build_apify_linkedin_actor_input(
            keywords=query,
            location=region_label,
            limit_per_source=per_region_limit,
            time_range=time_range,
            remote_types=remote_types,
            seniorities=seniorities,
            employment_types=employment_types,
        )
        await log(
            f"Apify LinkedIn Actor run: keywords={actor_input['keywords']!r} "
            f"location={region_label!r} datePosted={actor_input['datePosted']!r} "
            f"limitPerSource={per_region_limit}",
            "info",
        )
        try:
            async with semaphore:
                region_rows = await runner(actor_input=actor_input)
        except Exception as exc:
            reason = str(exc) or exc.__class__.__name__
            async with collect_lock:
                failures.append((region_label, reason))
            await log(
                f"Apify LinkedIn Actor run failed: location={region_label!r} ({reason})",
                "info",
            )
            return

        async with collect_lock:
            successes += 1
            raw_jobs.extend(region_rows)
        await log(
            f"Apify LinkedIn Actor run succeeded: location={region_label!r} "
            f"({len(region_rows)} listings)",
            "info",
        )

    await asyncio.gather(*(run_one(region) for _country, region in search_regions))

    if successes == 0:
        detail = "; ".join(f"{loc} ({reason})" for loc, reason in failures) or "unknown"
        raise ApifyLinkedInScrapeError(
            f"All {total} Apify LinkedIn Search Region run(s) failed: {detail}"
        )

    if failures:
        failed_summary = ", ".join(f"{loc} ({reason})" for loc, reason in failures)
        await log(
            f"Apify LinkedIn: {successes}/{total} regions OK; failed: {failed_summary}",
            "warning",
        )

    return raw_jobs


async def scrape_apify_linkedin_jobs(
    query: str,
    location: str = "Remote",
    search_regions: list[tuple[str, str]] | None = None,
    per_region_limit: int = 200,
    remote_types: list | str | None = None,
    seniorities: list | str | None = None,
    company_sizes: list | str | None = None,
    employment_types: list | str | None = None,
    countries: list | str | None = None,
    time_range: str = "any",
    log_func=None,
    force_mock: bool = False,
    apify_runner: ApifyLinkedInRunner | None = None,
) -> list:
    """Scrape LinkedIn listings via Apify (or mock), normalize, and post-filter."""

    async def log(msg: str, level: str = "info"):
        if log_func:
            if inspect.iscoroutinefunction(log_func):
                await log_func(msg, level)
            else:
                log_func(msg, level)

    mock_scraper = force_mock or os.getenv("MOCK_SCRAPER", "false").lower() == "true"
    runner = apify_runner or default_apify_linkedin_runner

    if remote_types and isinstance(remote_types, str):
        remote_types = [t.strip().lower() for t in remote_types.split(",") if t.strip()]
    if seniorities and isinstance(seniorities, str):
        seniorities = [s.strip().lower() for s in seniorities.split(",") if s.strip()]
    if company_sizes and isinstance(company_sizes, str):
        company_sizes = [c.strip().lower() for c in company_sizes.split(",") if c.strip()]
    remote_types = remote_types or ["any"]
    seniorities = seniorities or ["any"]
    company_sizes = company_sizes or ["any"]
    employment_types = parse_employment_types(employment_types)
    time_range = time_range or "any"

    if countries and isinstance(countries, str):
        countries = [c.strip().lower() for c in countries.split(",") if c.strip()]
    elif countries and isinstance(countries, list):
        countries = [str(c).lower() for c in countries]
    countries = countries or ["us"]

    if search_regions is None:
        search_regions = [(c.upper(), location) for c in countries]

    if mock_scraper:
        mock_location = search_regions[0][1] if search_regions else location
        raw_jobs = await _scrape_apify_linkedin_mock(query, mock_location, log)
    else:
        if apify_runner is None and not os.getenv("APIFY_API_TOKEN"):
            raise ApifyLinkedInScrapeError(
                "APIFY_API_TOKEN environment variable is missing. "
                "Please configure it in your .env file or enable mock mode."
            )
        max_concurrent = resolve_apify_linkedin_max_concurrent_runs()
        await log(
            f"Starting Apify LinkedIn scrape for {len(search_regions)} Search Region(s) "
            f"(concurrency={max_concurrent})...",
            "info",
        )
        raw_jobs = await _scrape_apify_linkedin_regions_parallel(
            query=query,
            search_regions=search_regions,
            per_region_limit=per_region_limit,
            time_range=time_range,
            remote_types=remote_types,
            seniorities=seniorities,
            employment_types=employment_types,
            runner=runner,
            log=log,
            max_concurrent=max_concurrent,
        )
        await log(f"Apify LinkedIn returned {len(raw_jobs)} raw listings.", "info")

    await log(f"Processing and filtering {len(raw_jobs)} Apify LinkedIn results...", "info")
    filtered_jobs: list[dict] = []
    for raw_job in raw_jobs:
        if not isinstance(raw_job, dict):
            continue
        normalized = normalize_apify_linkedin_job(raw_job)

        if "any" not in company_sizes and not match_company_size(normalized["size"], company_sizes):
            await log(
                f"Skipping '{normalized['title']}': Company Size '{normalized['size']}' "
                f"does not match {company_sizes}",
                "info",
            )
            continue

        if not match_employment_type(normalized.get("employmentType", ""), employment_types):
            await log(
                f"Skipping '{normalized['title']}': Employment Type "
                f"'{normalized.get('employmentType') or 'unknown'}' does not match "
                f"{employment_types}",
                "info",
            )
            continue

        filtered_jobs.append(normalized)

    await log(
        f"Apify LinkedIn filtering complete. Yielded {len(filtered_jobs)} matching listings.",
        "success",
    )
    return filtered_jobs
