#!/usr/bin/env python3
"""One-off probe: inspect Bright Data raw job fields (size-related). Limited scrape."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

SIZE_KEYS = (
    "company_size",
    "size",
    "companySize",
    "employees",
    "employee_count",
    "num_employees",
    "organization_size",
    "company_employees",
    "company_size_range",
)


async def main() -> int:
    from src.core.scraper import normalize_brightdata_job, _scrape_linkedin_jobs_real

    api_key = os.getenv("BRIGHTDATA_API_KEY")
    scraper_id = os.getenv("BRIGHTDATA_JOB_SCRAPER_ID", "gd_lpfll7v5hcqtkxl6l")
    if not api_key:
        print("BRIGHTDATA_API_KEY missing")
        return 1

    logs: list[str] = []

    async def log(msg: str, _level: str = "info") -> None:
        logs.append(msg)
        print(f"[{_level}] {msg}")

    print("Triggering limited Bright Data scrape: keyword='QA', location='Montreal', CA, past 24 hours")
    raw_jobs = await _scrape_linkedin_jobs_real(
        query="QA",
        location="Montreal",
        countries=["CA"],
        time_range="past 24 hours",
        api_key=api_key,
        scraper_id=scraper_id,
        log=log,
    )

    print(f"\nRaw jobs returned: {len(raw_jobs)}")
    sample = raw_jobs[:5]
    for i, job in enumerate(sample, 1):
        print(f"\n--- Job {i} keys ({len(job)} total) ---")
        print(sorted(job.keys()))
        size_hits = {k: job.get(k) for k in SIZE_KEYS if job.get(k) not in (None, "")}
        other_size = {
            k: v
            for k, v in job.items()
            if any(token in k.lower() for token in ("size", "employee", "staff", "headcount"))
            and v not in (None, "")
        }
        print("Known size keys:", size_hits or "(none)")
        print("Other size-like keys:", other_size or "(none)")
        normalized = normalize_brightdata_job(job)
        print(
            "Normalized:",
            json.dumps(
                {
                    "title": normalized.get("title"),
                    "company": normalized.get("company"),
                    "size": normalized.get("size"),
                    "companyUrl": normalized.get("companyUrl"),
                },
                ensure_ascii=False,
            ),
        )

    with_size = sum(1 for j in raw_jobs if normalize_brightdata_job(j).get("size"))
    print(f"\nSummary: {with_size}/{len(raw_jobs)} jobs have normalized size after mapping")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
