#!/usr/bin/env python3
"""Fetch Glassdoor company intel via Apify (sian.agency/glassdoor-data-scraper)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

APIFY_API_BASE = "https://api.apify.com/v2"
ACTOR_ID = "sian.agency~glassdoor-data-scraper"


class GlassdoorIntelError(Exception):
    pass


async def _run_apify_operation(
    client: Any,
    *,
    api_token: str,
    actor_input: dict[str, Any],
    timeout_seconds: float = 300.0,
    poll_interval: float = 5.0,
) -> list[dict[str, Any]]:
    run_url = f"{APIFY_API_BASE}/acts/{ACTOR_ID}/runs"
    params = {"token": api_token}
    headers = {"Content-Type": "application/json"}

    resp = await client.post(run_url, params=params, headers=headers, json=actor_input)
    if resp.status_code not in (200, 201):
        raise GlassdoorIntelError(
            f"Apify trigger failed for {actor_input.get('operation')}: HTTP {resp.status_code} — {resp.text[:300]}"
        )

    run_id = resp.json().get("data", {}).get("id")
    if not run_id:
        raise GlassdoorIntelError("Apify did not return a run ID.")

    status_url = f"{APIFY_API_BASE}/actor-runs/{run_id}"
    start_time = time.monotonic()
    dataset_id: str | None = None

    while True:
        if time.monotonic() - start_time >= timeout_seconds:
            raise GlassdoorIntelError(f"Apify run {run_id} timed out after {timeout_seconds}s")

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
            raise GlassdoorIntelError(f"Apify run {run_id} ended with status: {status}")

    if not dataset_id:
        raise GlassdoorIntelError("Apify run succeeded but returned no dataset ID.")

    dataset_url = f"{APIFY_API_BASE}/datasets/{dataset_id}/items"
    data_resp = await client.get(dataset_url, params={**params, "format": "json"})
    if data_resp.status_code != 200:
        raise GlassdoorIntelError(f"Apify dataset fetch failed: HTTP {data_resp.status_code}")

    items = data_resp.json()
    if not isinstance(items, list):
        raise GlassdoorIntelError("Apify dataset response was not a JSON list.")
    return items


def _first_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _pick_company_match(company_name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise GlassdoorIntelError(f"No Glassdoor companies found for '{company_name}'.")

    target = company_name.strip().lower()
    for row in rows:
        name = str(_first_value(row, "companyName", "name", "shortName") or "").lower()
        if name == target:
            return row

    for row in rows:
        name = str(_first_value(row, "companyName", "name", "shortName") or "").lower()
        if target in name or name in target:
            return row

    return rows[0]


def _format_percent(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip().replace("%", "")
        if not cleaned:
            return None
        value = float(cleaned)
    if isinstance(value, (int, float)):
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


def _build_report(
    *,
    company_name: str,
    job_title: str,
    company_id: str,
    matched_name: str | None,
    overview_rows: list[dict[str, Any]],
    salary_rows: list[dict[str, Any]],
    interview_rows: list[dict[str, Any]],
) -> dict[str, Any]:
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

    salary = None
    for row in salary_rows:
        if row.get("status") == "error":
            continue
        salary = {
            "jobTitle": _first_value(row, "jobTitle", "jobTitleText", "title") or job_title,
            "medianBaseSalary": _first_value(row, "medianBaseSalary", "basePay", "baseSalary", "payMedian"),
            "medianTotalSalary": _first_value(row, "medianSalary", "totalPay", "salaryMedian"),
            "currency": _first_value(row, "currency", "payCurrency") or "USD",
            "sampleSize": _first_value(row, "numSalaries", "salaryCount", "count"),
        }
        break

    return {
        "company": company_name,
        "glassdoorCompanyId": company_id,
        "matchedCompanyName": matched_name,
        "companySize": company_size,
        "rating": {
            "overall": rating,
            "reviewCount": review_count,
        },
        "recommendPercent": recommend,
        "salary": salary,
        "interviews": _summarize_interviews(interview_rows, job_title),
        "sources": {
            "overviewRows": len(overview_rows),
            "salaryRows": len(salary_rows),
            "interviewRows": len(interview_rows),
        },
    }


async def fetch_glassdoor_intel(
    company_name: str,
    job_title: str,
    *,
    max_interview_pages: int = 2,
) -> dict[str, Any]:
    import httpx

    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        raise GlassdoorIntelError("APIFY_API_TOKEN not set in .env")

    async with httpx.AsyncClient(timeout=120.0) as client:
        search_rows = await _run_apify_operation(
            client,
            api_token=api_token,
            actor_input={"operation": "companySearch", "query": company_name},
        )
        match = _pick_company_match(company_name, search_rows)
        company_id = str(_first_value(match, "companyId", "id", "employerId") or "")
        if not company_id:
            raise GlassdoorIntelError(f"Could not resolve Glassdoor company ID for '{company_name}'.")
        matched_name = _first_value(match, "companyName", "name", "shortName")

        overview_rows = await _run_apify_operation(
            client,
            api_token=api_token,
            actor_input={"operation": "companyOverview", "companyId": company_id},
        )
        salary_rows = await _run_apify_operation(
            client,
            api_token=api_token,
            actor_input={
                "operation": "companySalaries",
                "companyId": company_id,
                "jobTitle": job_title,
            },
        )
        interview_rows = await _run_apify_operation(
            client,
            api_token=api_token,
            actor_input={
                "operation": "companyInterviews",
                "companyId": company_id,
                "jobTitle": job_title,
                "maxPages": max_interview_pages,
                "interviewSort": "POPULAR",
            },
        )

    return _build_report(
        company_name=company_name,
        job_title=job_title,
        company_id=company_id,
        matched_name=str(matched_name) if matched_name else None,
        overview_rows=overview_rows,
        salary_rows=salary_rows,
        interview_rows=interview_rows,
    )


def _print_report(report: dict[str, Any]) -> None:
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print()
    print("--- Summary ---")
    print(f"Company: {report.get('matchedCompanyName') or report.get('company')}")
    print(f"Size: {report.get('companySize') or 'n/a'}")
    rating = report.get("rating") or {}
    print(f"Rating: {rating.get('overall') or 'n/a'} based on {rating.get('reviewCount') or 'n/a'} reviews")
    print(f"Recommend: {report.get('recommendPercent') or 'n/a'}%")
    salary = report.get("salary") or {}
    if salary.get("medianBaseSalary") is not None:
        print(
            f"Base salary ({salary.get('jobTitle')}): "
            f"{salary.get('medianBaseSalary')} {salary.get('currency')}"
        )
    else:
        print(f"Base salary ({report.get('salary', {}).get('jobTitle', 'n/a')}): n/a")
    interviews = report.get("interviews") or []
    if interviews:
        print("Interview process:")
        for item in interviews:
            print(f"  - {item.get('jobTitle')}: {item.get('processSummary')}")
    else:
        print("Interview process: n/a")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Glassdoor company intel via Apify.")
    parser.add_argument("--company", required=True, help="Company name to look up on Glassdoor")
    parser.add_argument(
        "--job-title",
        default="QA Engineer",
        help="Job title for salary and interview lookup (default: QA Engineer)",
    )
    parser.add_argument(
        "--max-interview-pages",
        type=int,
        default=2,
        help="Pages of interview results to fetch (default: 2)",
    )
    args = parser.parse_args()

    try:
        report = await fetch_glassdoor_intel(
            args.company,
            args.job_title,
            max_interview_pages=args.max_interview_pages,
        )
    except GlassdoorIntelError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
