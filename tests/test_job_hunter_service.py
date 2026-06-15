"""Tracer-bullet tests for JobHunterService orchestration."""
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.mark.asyncio
async def test_search_jobs_acquires_rate_limit_for_real_search():
    from src.service.job_hunter import search_jobs

    with patch("src.service.job_hunter.scrape_limiter.acquire") as mock_acquire, \
         patch("src.service.job_hunter.run_search_pipeline", new=AsyncMock(return_value=[])) as mock_pipeline:
        await search_jobs(query="QA", mock_eval=False)

    mock_acquire.assert_called_once()
    mock_pipeline.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_jobs_skips_rate_limit_when_fully_mocked():
    from src.service.job_hunter import search_jobs

    with patch.dict(os.environ, {"MOCK_SCRAPER": "true"}), \
         patch("src.service.job_hunter.scrape_limiter.acquire") as mock_acquire, \
         patch("src.service.job_hunter.run_search_pipeline", new=AsyncMock(return_value=[])):
        await search_jobs(query="QA", mock_eval=True)

    mock_acquire.assert_not_called()


def test_parse_remote_types_accepts_comma_string():
    from src.service.job_hunter import parse_remote_types

    assert parse_remote_types("remote, hybrid") == ["remote", "hybrid"]


@pytest.mark.asyncio
async def test_complete_enrichment_runs_pipeline_for_enriching_job():
    from src.service.job_hunter import complete_enrichment

    job = {"id": 7, "title": "QA", "company": "Acme", "status": "enriching"}
    enriched = {**job, "status": "enriched", "contacts": []}

    with patch("src.service.job_hunter.get_job", return_value=job), \
         patch("src.service.job_hunter.run_enrichment_pipeline", new=AsyncMock(return_value=enriched)) as mock_pipeline, \
         patch("src.service.job_hunter.abort_enrichment") as mock_abort:
        result = await complete_enrichment(7)

    mock_pipeline.assert_awaited_once()
    mock_abort.assert_not_called()
    assert result["status"] == "enriched"


@pytest.mark.asyncio
async def test_complete_enrichment_aborts_when_pipeline_returns_none():
    from src.service.job_hunter import complete_enrichment

    job = {"id": 7, "title": "QA", "company": "Acme", "status": "enriching"}

    with patch("src.service.job_hunter.get_job", return_value=job), \
         patch("src.service.job_hunter.run_enrichment_pipeline", new=AsyncMock(return_value=None)), \
         patch("src.service.job_hunter.abort_enrichment") as mock_abort:
        result = await complete_enrichment(7)

    mock_abort.assert_called_once_with(7)
    assert result is None
