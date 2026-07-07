#!/usr/bin/env python3
"""Fetch Glassdoor company intel via Apify — thin CLI wrapper around core module."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from src.core.company_research.glassdoor_intel import (  # noqa: E402
    GlassdoorIntelError,
    _summarize_interviews,
    build_job_company_research_snapshot,
    default_apify_runner,
    normalize_salary_row,
    parse_overview_row,
    _pick_company_match,
)


def _print_report(report: dict) -> None:
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print()
    print("--- Summary ---")
    print(f"Company: {report.get('matchedName') or report.get('company')}")
    print(f"Size: {report.get('companySize') or 'n/a'}")
    print(f"Rating: {report.get('rating') or 'n/a'} based on {report.get('reviewCount') or 'n/a'} reviews")
    print(f"Recommend: {report.get('recommendPercent') or 'n/a'}%")
    salary = report.get("salary") or {}
    title = report.get("glassdoorJobTitle") or "n/a"
    if salary.get("medianBaseSalary") is not None:
        print(f"Base salary ({title}): {salary.get('medianBaseSalary')} {salary.get('currency')}")
    else:
        print(f"Base salary ({title}): n/a")
    interviews = report.get("interviews") or []
    if interviews:
        print("Interview process:")
        for item in interviews:
            print(f"  - {item.get('jobTitle')}: {item.get('processSummary')}")
    else:
        print("Interview process: n/a")


async def fetch_glassdoor_intel(
    company_name: str,
    job_title: str,
    *,
    max_interview_pages: int = 2,
) -> dict:
    search_rows = await default_apify_runner("companySearch", company_name=company_name)
    match = _pick_company_match(company_name, search_rows)
    company_id = str(match.get("companyId") or match.get("id") or match.get("employerId") or "")
    if not company_id:
        raise GlassdoorIntelError(f"Could not resolve Glassdoor company ID for '{company_name}'.")
    matched_name = str(
        match.get("companyName") or match.get("name") or match.get("shortName") or company_name
    )

    overview_rows = await default_apify_runner("companyOverview", company_id=company_id)
    salary_rows = await default_apify_runner(
        "companySalaries",
        company_id=company_id,
        job_title=job_title,
    )
    interview_rows = await default_apify_runner(
        "companyInterviews",
        company_id=company_id,
        job_title=job_title,
        max_interview_pages=max_interview_pages,
    )

    overview = parse_overview_row(overview_rows)
    salary = None
    for row in salary_rows:
        salary = normalize_salary_row(row, job_title)
        if salary:
            break
    interviews = _summarize_interviews(interview_rows, job_title)

    snapshot = build_job_company_research_snapshot(
        glassdoor_company_id=company_id,
        matched_name=matched_name,
        overview=overview,
        glassdoor_job_title=job_title,
        salary=salary,
        interviews=interviews,
    )
    return {"company": company_name, **snapshot}


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
