"""Tracer-bullet tests for JustApply orchestration."""
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.mark.asyncio
async def test_search_jobs_acquires_rate_limit_for_real_search():
    from src.service.just_apply import search_jobs

    with patch("src.service.just_apply.scrape_limiter.acquire") as mock_acquire, \
         patch("src.service.just_apply.run_search_pipeline", new=AsyncMock(return_value=[])) as mock_pipeline:
        await search_jobs(query="QA", mock_eval=False)

    mock_acquire.assert_called_once()
    mock_pipeline.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_jobs_skips_rate_limit_when_fully_mocked():
    from src.service.just_apply import search_jobs

    with patch.dict(os.environ, {"MOCK_SCRAPER": "true"}), \
         patch("src.service.just_apply.scrape_limiter.acquire") as mock_acquire, \
         patch("src.service.just_apply.run_search_pipeline", new=AsyncMock(return_value=[])):
        await search_jobs(query="QA", mock_eval=True)

    mock_acquire.assert_not_called()


@pytest.mark.asyncio
async def test_mock_eval_run_defaults_to_mock_scraper_and_skips_rate_limit():
    """Regression: a mock-eval run must NOT trigger a real, billable scrape.

    Previously mock_eval=True still hit Bright Data unless the MOCK_SCRAPER env
    was also set, which dumped ~1,800 real jobs into the tracker during a test.
    """
    from src.service.just_apply import search_jobs

    with patch.dict(os.environ, {}, clear=False), \
         patch("src.service.just_apply.scrape_limiter.acquire") as mock_acquire, \
         patch("src.service.just_apply.run_search_pipeline", new=AsyncMock(return_value=[])) as mock_pipeline:
        os.environ.pop("MOCK_SCRAPER", None)
        await search_jobs(query="QA", mock_eval=True)

    mock_acquire.assert_not_called()
    assert mock_pipeline.await_args.kwargs["mock_scraper"] is True


@pytest.mark.asyncio
async def test_explicit_mock_scraper_false_forces_real_scrape_with_mock_eval():
    """An explicit mock_scraper=False overrides the mock_eval default."""
    from src.service.just_apply import search_jobs

    with patch.dict(os.environ, {}, clear=False), \
         patch("src.service.just_apply.scrape_limiter.acquire") as mock_acquire, \
         patch("src.service.just_apply.run_search_pipeline", new=AsyncMock(return_value=[])) as mock_pipeline:
        os.environ.pop("MOCK_SCRAPER", None)
        await search_jobs(query="QA", mock_eval=True, mock_scraper=False)

    mock_acquire.assert_called_once()
    assert mock_pipeline.await_args.kwargs["mock_scraper"] is False


def test_scraper_will_mock_resolution_order():
    from src.service.just_apply import scraper_will_mock

    os.environ.pop("MOCK_SCRAPER", None)
    # 3. falls back to mock_eval when nothing explicit
    assert scraper_will_mock(mock_eval=True) is True
    assert scraper_will_mock(mock_eval=False) is False
    # 2. explicit flag wins over mock_eval
    assert scraper_will_mock(mock_eval=True, mock_scraper=False) is False
    assert scraper_will_mock(mock_eval=False, mock_scraper=True) is True
    # 1. env forces mock regardless
    with patch.dict(os.environ, {"MOCK_SCRAPER": "true"}):
        assert scraper_will_mock(mock_eval=False, mock_scraper=False) is True


def test_parse_remote_types_accepts_comma_string():
    from src.service.just_apply import parse_remote_types

    assert parse_remote_types("remote, hybrid") == ["remote", "hybrid"]


@pytest.mark.asyncio
async def test_complete_enrichment_runs_pipeline_for_enriching_job():
    from src.schemas import Job
    from src.service.just_apply import complete_enrichment

    job = Job(id=7, title="QA", company="Acme", status="enriching")
    enriched = Job(**{**job.model_dump(), "status": "enriched"})

    with patch("src.service.just_apply.get_job", return_value=job), \
         patch("src.service.just_apply.run_enrichment_pipeline", new=AsyncMock(return_value=enriched)) as mock_pipeline, \
         patch("src.service.just_apply.abort_enrichment") as mock_abort:
        result = await complete_enrichment(7)

    mock_pipeline.assert_awaited_once()
    mock_abort.assert_not_called()
    assert result.status == "enriched"


@pytest.mark.asyncio
async def test_complete_enrichment_aborts_when_pipeline_returns_none():
    from src.schemas import Job
    from src.service.just_apply import complete_enrichment

    job = Job(id=7, title="QA", company="Acme", status="enriching")

    with patch("src.service.just_apply.get_job", return_value=job), \
         patch("src.service.just_apply.run_enrichment_pipeline", new=AsyncMock(return_value=None)), \
         patch("src.service.just_apply.abort_enrichment") as mock_abort:
        result = await complete_enrichment(7)

    mock_abort.assert_called_once_with(7)
    assert result is None
