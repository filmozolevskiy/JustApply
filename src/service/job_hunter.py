"""Application orchestration for CLI and Kanban Dashboard adapters."""

from __future__ import annotations

import inspect
import os
from typing import Awaitable, Callable

from ..schemas import Job

from ..db import get_job, get_jobs, init_db
from ..pipelines import run_enrichment_pipeline, run_search_pipeline, run_reassess_pipeline
from ..core.enrichment.coordinator import abort_enrichment, begin_enrichment
from ..rate_limiter import RateLimitError, scrape_limiter

LogFunc = Callable[[str, str], None] | Callable[[str, str], Awaitable[None]]


def parse_remote_types(remote_type) -> list[str]:
    """Normalize dashboard/CLI remote-type params for the search pipeline."""
    if isinstance(remote_type, str):
        return [t.strip().lower() for t in remote_type.split(",") if t.strip()]
    if isinstance(remote_type, list):
        return [t.lower() for t in remote_type if t]
    return ["any"]


def acquire_scrape_slot(mock_eval: bool) -> None:
    """Acquire the scrape rate limiter when a real Bright Data run is expected."""
    is_mock_scraper = os.getenv("MOCK_SCRAPER", "false").lower() == "true"
    is_real = (not mock_eval) or (not is_mock_scraper)
    if is_real:
        scrape_limiter.acquire()


async def search_jobs(
    *,
    query: str,
    location: str = "Remote",
    active_resume: str = "general_cv.md",
    mock_eval: bool = False,
    allowed_remote_types: list | None = None,
    seniorities: str = "any",
    company_sizes: str = "any",
    countries: str = "us",
    time_range: str = "any",
    log_func=None,
    job_saved_func=None,
    rate_limit: bool = True,
) -> list:
    """Run Search & Evaluation Pipeline with shared rate-limit gating."""
    if rate_limit:
        acquire_scrape_slot(mock_eval)
    return await run_search_pipeline(
        query=query,
        location=location,
        active_resume=active_resume,
        mock_eval=mock_eval,
        allowed_remote_types=allowed_remote_types,
        seniorities=seniorities,
        company_sizes=company_sizes,
        countries=countries,
        time_range=time_range,
        log_func=log_func,
        job_saved_func=job_saved_func,
    )


async def complete_enrichment(
    job_id: int,
    *,
    log_func=None,
) -> Job | None:
    """Finish enrichment for a job already in the enriching lane."""
    job = get_job(job_id)
    if not job:
        abort_enrichment(job_id)
        return None

    try:
        updated = await run_enrichment_pipeline(job, log_func=log_func)
    except Exception:
        abort_enrichment(job_id)
        raise
    if not updated:
        abort_enrichment(job_id)
        return None
    return updated


async def reassess_job(
    job_id: int,
    *,
    active_resume: str = "general_cv.md",
    log_func=None,
) -> Job:
    """Re-run Resume Matcher on a single existing job."""
    init_db()
    return await run_reassess_pipeline(job_id, active_resume=active_resume, log_func=log_func)


async def reassess_all_jobs(
    *,
    active_resume: str = "general_cv.md",
    archived_filter: str = "active",
    log_func=None,
) -> list[Job]:
    """Re-run Resume Matcher on every job in the given archive filter."""
    init_db()
    jobs = get_jobs(archived_filter=archived_filter)
    updated = []
    for job in jobs:
        try:
            result = await run_reassess_pipeline(
                job.id, active_resume=active_resume, log_func=log_func
            )
            updated.append(result)
        except ValueError as e:
            if log_func:
                msg = f"Skipped job id={job.id}: {e}"
                if inspect.iscoroutinefunction(log_func):
                    await log_func(msg, "warning")
                else:
                    log_func(msg, "warning")
    return updated


async def promote_sourced_jobs(log_func=None) -> list:
    """Enrich all Found jobs that passed Resume Matcher."""
    init_db()
    to_promote = [
        j for j in get_jobs()
        if j.shouldProceed and j.status == "found"
    ]

    promoted = []
    for job in to_promote:
        began = begin_enrichment(job.id)
        if not began:
            promoted.append(job)
            continue
        enriched = await complete_enrichment(job.id, log_func=log_func)
        promoted.append(enriched if enriched else job)
    return promoted


__all__ = [
    "RateLimitError",
    "acquire_scrape_slot",
    "begin_enrichment",
    "complete_enrichment",
    "parse_remote_types",
    "promote_sourced_jobs",
    "reassess_all_jobs",
    "reassess_job",
    "search_jobs",
]
