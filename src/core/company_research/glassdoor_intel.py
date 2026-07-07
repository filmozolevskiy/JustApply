"""Glassdoor employer intel via Apify (sian.agency/glassdoor-data-scraper)."""

from __future__ import annotations

import os
import re
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

APIFY_API_BASE = "https://api.apify.com/v2"
ACTOR_ID = "sian.agency~glassdoor-data-scraper"

ApifyRunner = Callable[..., Awaitable[list[dict[str, Any]]]]


class GlassdoorIntelError(Exception):
    pass


class GlassdoorInfrastructureError(GlassdoorIntelError):
    pass


async def run_apify_glassdoor_operation(
    client: Any,
    *,
    api_token: str,
    actor_input: dict[str, Any],
    timeout_seconds: float = 300.0,
    poll_interval: float = 0.01,
) -> list[dict[str, Any]]:
    run_url = f"{APIFY_API_BASE}/acts/{ACTOR_ID}/runs"
    params = {"token": api_token}
    headers = {"Content-Type": "application/json"}

    resp = await client.post(run_url, params=params, headers=headers, json=actor_input)
    if resp.status_code not in (200, 201):
        raise GlassdoorInfrastructureError(
            f"Apify trigger failed for {actor_input.get('operation')}: "
            f"HTTP {resp.status_code} — {resp.text[:300]}"
        )

    run_id = resp.json().get("data", {}).get("id")
    if not run_id:
        raise GlassdoorInfrastructureError("Apify did not return a run ID.")

    status_url = f"{APIFY_API_BASE}/actor-runs/{run_id}"
    start_time = time.monotonic()
    dataset_id: str | None = None

    while True:
        if time.monotonic() - start_time >= timeout_seconds:
            raise GlassdoorInfrastructureError(f"Apify run {run_id} timed out after {timeout_seconds}s")

        await _sleep(poll_interval)
        status_resp = await client.get(status_url, params=params)
        if status_resp.status_code != 200:
            continue

        run_data = status_resp.json().get("data", {})
        status = run_data.get("status")
        if status == "SUCCEEDED":
            dataset_id = run_data.get("defaultDatasetId")
            break
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            raise GlassdoorInfrastructureError(f"Apify run {run_id} ended with status: {status}")

    if not dataset_id:
        raise GlassdoorInfrastructureError("Apify run succeeded but returned no dataset ID.")

    dataset_url = f"{APIFY_API_BASE}/datasets/{dataset_id}/items"
    data_resp = await client.get(dataset_url, params={**params, "format": "json"})
    if data_resp.status_code != 200:
        raise GlassdoorInfrastructureError(f"Apify dataset fetch failed: HTTP {data_resp.status_code}")

    items = data_resp.json()
    if not isinstance(items, list):
        raise GlassdoorInfrastructureError("Apify dataset response was not a JSON list.")
    return items


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


def _first_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _slug_tokens(value: str) -> set[str]:
    cleaned = re.sub(r"[^\w\s-]", "", value.lower())
    tokens = set(cleaned.replace("-", " ").split())
    tokens.discard("")
    return tokens


def _row_name(row: dict[str, Any]) -> str:
    return str(_first_value(row, "companyName", "name", "shortName") or "")


def _pick_company_match(
    company_name: str,
    rows: list[dict[str, Any]],
    linkedin_slug: str = "",
) -> dict[str, Any]:
    if not rows:
        raise GlassdoorIntelError(f"No Glassdoor companies found for '{company_name}'.")

    target = company_name.strip().lower()
    linkedin_tokens = _slug_tokens(linkedin_slug.replace("-", " ")) if linkedin_slug else set()

    exact = [row for row in rows if _row_name(row).lower() == target]
    if exact:
        return _tie_break_candidates(exact, linkedin_tokens)

    substring = [
        row
        for row in rows
        if target in _row_name(row).lower() or _row_name(row).lower() in target
    ]
    if substring:
        return _tie_break_candidates(substring, linkedin_tokens)

    if linkedin_tokens:
        scored = sorted(
            rows,
            key=lambda row: len(_slug_tokens(_row_name(row)) & linkedin_tokens),
            reverse=True,
        )
        if scored and len(_slug_tokens(_row_name(scored[0])) & linkedin_tokens) > 0:
            return scored[0]

    return rows[0]


def _tie_break_candidates(
    candidates: list[dict[str, Any]],
    linkedin_tokens: set[str],
) -> dict[str, Any]:
    if len(candidates) == 1 or not linkedin_tokens:
        return candidates[0]
    scored = sorted(
        candidates,
        key=lambda row: len(_slug_tokens(_row_name(row)) & linkedin_tokens),
        reverse=True,
    )
    return scored[0]


def _format_percent(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip().replace("%", "")
        if not cleaned:
            return None
        value = float(cleaned)
    if isinstance(value, int | float):
        if 0 <= value <= 1:
            return round(value * 100, 1)
        return round(float(value), 1)
    return None


def _summarize_interviews(rows: list[dict[str, Any]], job_title: str) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    title_lower = job_title.lower()

    for row in rows:
        row_title = str(_first_value(row, "jobTitle", "jobTitleText", "title") or "")
        process = _first_value(row, "processDescription", "process", "description", "reviewSummary")
        if not process:
            continue
        if title_lower not in row_title.lower() and row_title:
            continue
        summaries.append(
            {
                "jobTitle": row_title or job_title,
                "difficulty": _first_value(row, "difficulty", "interviewDifficulty"),
                "outcome": _first_value(row, "outcome", "offer", "interviewOutcome"),
                "processSummary": str(process).strip()[:500],
            }
        )

    if summaries:
        return summaries[:3]

    for row in rows:
        process = _first_value(row, "processDescription", "process", "description", "reviewSummary")
        if not process:
            continue
        summaries.append(
            {
                "jobTitle": _first_value(row, "jobTitle", "jobTitleText", "title") or job_title,
                "difficulty": _first_value(row, "difficulty", "interviewDifficulty"),
                "outcome": _first_value(row, "outcome", "offer", "interviewOutcome"),
                "processSummary": str(process).strip()[:500],
            }
        )
        if len(summaries) >= 3:
            break
    return summaries


def normalize_salary_row(row: dict[str, Any], job_title: str) -> dict[str, Any] | None:
    if row.get("status") == "error":
        return None
    median = _first_value(row, "medianBaseSalary", "basePay", "baseSalary", "payMedian")
    if median is None:
        return None
    return {
        "medianBaseSalary": median,
        "currency": _first_value(row, "currency", "payCurrency") or "USD",
        "sampleSize": _first_value(row, "numSalaries", "salaryCount", "count"),
    }


def parse_overview_row(overview_rows: list[dict[str, Any]]) -> dict[str, Any]:
    overview = overview_rows[0] if overview_rows else {}
    review_count = _first_value(
        overview,
        "reviewCount",
        "numReviews",
        "totalReviewCount",
        "numberOfReviews",
        "reviewsCount",
    )
    rating = _first_value(overview, "rating", "overallRating", "ratingsOverall", "companyRating")
    recommend = _format_percent(
        _first_value(
            overview,
            "recommendToFriendPercent",
            "recommendToFriendRating",
            "recommendPercent",
            "percentRecommendToFriend",
            "ratingRecommendToFriend",
        )
    )
    company_size = _first_value(overview, "size", "companySize", "detailsSize", "employeeSize")
    return {
        "companySize": company_size,
        "rating": rating,
        "reviewCount": review_count,
        "recommendPercent": recommend,
    }


def build_job_company_research_snapshot(
    *,
    glassdoor_company_id: str,
    matched_name: str,
    overview: dict[str, Any],
    glassdoor_job_title: str,
    salary: dict[str, Any] | None,
    interviews: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "glassdoorCompanyId": glassdoor_company_id,
        "matchedName": matched_name,
        "companySize": overview.get("companySize"),
        "rating": overview.get("rating"),
        "reviewCount": overview.get("reviewCount"),
        "recommendPercent": overview.get("recommendPercent"),
        "glassdoorJobTitle": glassdoor_job_title,
        "salary": salary,
        "interviews": interviews,
        "fetchedAt": datetime.now(UTC).isoformat(),
    }


def format_activity_log_message(snapshot: dict[str, Any]) -> str:
    rating = snapshot.get("rating")
    rating_str = f"{rating}★" if rating is not None else "n/a"
    recommend = snapshot.get("recommendPercent")
    if recommend is not None:
        recommend_display = int(recommend) if recommend == int(recommend) else recommend
        recommend_str = f"{recommend_display}% recommend"
    else:
        recommend_str = "recommend n/a"
    title = snapshot.get("glassdoorJobTitle") or "role"
    salary = snapshot.get("salary")
    if salary and salary.get("medianBaseSalary") is not None:
        salary_str = f"{title} salary ${salary.get('medianBaseSalary')}"
    else:
        salary_str = f"{title} salary n/a"
    return f"Company research · {rating_str} · {recommend_str} · {salary_str}"


async def default_apify_runner(
    operation: str,
    *,
    company_name: str = "",
    company_id: str = "",
    job_title: str = "",
    max_interview_pages: int = 2,
) -> list[dict[str, Any]]:
    import httpx

    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        raise GlassdoorInfrastructureError("APIFY_API_TOKEN not set in .env")

    actor_input: dict[str, Any] = {"operation": operation}
    if operation == "companySearch":
        actor_input["query"] = company_name
    elif operation == "companyOverview":
        actor_input["companyId"] = company_id
    elif operation == "companySalaries":
        actor_input["companyId"] = company_id
        actor_input["jobTitle"] = job_title
    elif operation == "companyInterviews":
        actor_input.update(
            {
                "companyId": company_id,
                "jobTitle": job_title,
                "maxPages": max_interview_pages,
                "interviewSort": "POPULAR",
            }
        )
    else:
        raise GlassdoorIntelError(f"Unknown Glassdoor operation: {operation}")

    async with httpx.AsyncClient(timeout=120.0) as client:
        return await run_apify_glassdoor_operation(
            client,
            api_token=api_token,
            actor_input=actor_input,
        )
