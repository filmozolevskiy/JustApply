"""Search-orchestration seam: Source Platform routing and unsupported rejection.

Mocks scrape providers — no live Bright Data or Apify calls.
"""

from unittest.mock import AsyncMock, patch

import pytest
import src.db.connection as _db_connection
from fastapi.testclient import TestClient
from src import db as database
from src.core.source_platform import (
    DEFAULT_SOURCE_PLATFORM,
    UnsupportedSourcePlatformError,
    validate_source_platform,
)
from src.pipelines import run_search_pipeline
from src.service.just_apply import search_jobs


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MOCK_SCRAPER", "true")
    test_db = tmp_path / "test_just_apply.db"
    test_db_str = str(test_db)
    monkeypatch.setattr(_db_connection, "DB_PATH", test_db_str)
    database.init_db(test_db_str)
    yield test_db_str


@pytest.fixture
def client():
    """Build a client against the currently loaded server module.

    ``test_server_lifecycle`` reloads ``src.web.server``; a module-level
    TestClient can hold a stale app after that.
    """
    import src.web.server as server_mod

    return TestClient(server_mod.app)


def _make_job():
    return {
        "title": "QA Engineer",
        "company": "Acme",
        "size": "100-500",
        "link": "https://example.com/job1",
        "date": "2026-06-07",
        "location": "Remote",
        "remoteType": "remote",
        "seniority": "senior",
        "salary": "$130k",
        "description": "QA role.",
        "status": "scraped",
        "contacts": [],
    }


def _valid_payload(**overrides):
    payload = {
        "query": "QA Engineer",
        "search_regions": [{"country": "US", "region": "California"}],
        "per_region_limit": 200,
        "platform": "brightdata_linkedin",
        "active_resume": "qa.md",
        "mock_eval": True,
        "remote_type": "any",
        "seniority": "any",
        "salary": "",
        "company_size": "any",
        "countries": "us",
        "time_range": "any",
    }
    payload.update(overrides)
    return payload


def test_validate_accepts_brightdata_linkedin():
    assert validate_source_platform("brightdata_linkedin") == "brightdata_linkedin"
    assert validate_source_platform(None) == DEFAULT_SOURCE_PLATFORM
    assert validate_source_platform("") == DEFAULT_SOURCE_PLATFORM


def test_validate_accepts_apify_linkedin():
    assert validate_source_platform("apify_linkedin") == "apify_linkedin"


@pytest.mark.parametrize(
    "platform",
    ["apify_indeed", "apify_glassdoor", "unknown_vendor", "linkedin"],
)
def test_validate_rejects_unsupported_platforms(platform):
    with pytest.raises(UnsupportedSourcePlatformError, match="unsupported|not supported"):
        validate_source_platform(platform)


@pytest.mark.asyncio
async def test_pipeline_brightdata_routes_to_linkedin_scraper():
    """brightdata_linkedin keeps the existing Bright Data scrape path."""
    with patch(
        "src.pipelines.scrape_linkedin_jobs",
        new=AsyncMock(return_value=[_make_job()]),
    ) as mock_scrape, patch(
        "src.pipelines.scrape_apify_linkedin_jobs",
        new=AsyncMock(return_value=[_make_job()]),
    ) as mock_apify, patch("src.pipelines.database.init_db"), patch(
        "src.pipelines.database.job_exists", return_value=False
    ), patch("src.pipelines.database.add_job", return_value=1), patch(
        "src.pipelines.submit_batch_evaluation", new=AsyncMock()
    ):
        results = await run_search_pipeline(
            "QA",
            platform="brightdata_linkedin",
            mock_eval=True,
        )

        mock_scrape.assert_awaited_once()
        mock_apify.assert_not_called()
        assert len(results) == 1


@pytest.mark.asyncio
async def test_pipeline_apify_linkedin_routes_to_apify_scraper():
    """apify_linkedin scrapes via Apify path and saves Scraped jobs."""
    with patch(
        "src.pipelines.scrape_linkedin_jobs",
        new=AsyncMock(return_value=[_make_job()]),
    ) as mock_bd, patch(
        "src.pipelines.scrape_apify_linkedin_jobs",
        new=AsyncMock(return_value=[_make_job()]),
    ) as mock_apify, patch("src.pipelines.database.init_db"), patch(
        "src.pipelines.database.job_exists", return_value=False
    ), patch("src.pipelines.database.add_job", return_value=42) as mock_add, patch(
        "src.pipelines.submit_batch_evaluation", new=AsyncMock()
    ) as mock_batch:
        results = await run_search_pipeline(
            "QA",
            platform="apify_linkedin",
            mock_eval=True,
            mock_scraper=True,
        )

        mock_apify.assert_awaited_once()
        assert mock_apify.await_args.kwargs.get("force_mock") is True
        mock_bd.assert_not_called()
        mock_add.assert_called_once()
        # mock_eval skips batch submit — path still saves Scraped jobs.
        mock_batch.assert_not_awaited()
        assert len(results) == 1
        assert results[0]["status"] == "scraped"


@pytest.mark.asyncio
async def test_pipeline_apify_linkedin_submits_batch_when_not_mock_eval():
    """Non-mock eval still uses the shared batch evaluation path after Apify scrape."""
    with patch(
        "src.pipelines.scrape_apify_linkedin_jobs",
        new=AsyncMock(return_value=[_make_job()]),
    ), patch("src.pipelines.database.init_db"), patch(
        "src.pipelines.database.job_exists", return_value=False
    ), patch("src.pipelines.database.add_job", return_value=7), patch(
        "src.pipelines.load_resume", return_value="resume text"
    ), patch(
        "src.pipelines.submit_batch_evaluation",
        new=AsyncMock(return_value=[]),
    ) as mock_batch:
        results = await run_search_pipeline(
            "QA",
            platform="apify_linkedin",
            mock_eval=False,
            mock_scraper=True,
        )

        mock_batch.assert_awaited_once()
        assert len(results) == 1
        assert results[0]["status"] == "scraped"


@pytest.mark.asyncio
async def test_pipeline_default_platform_is_brightdata():
    with patch(
        "src.pipelines.scrape_linkedin_jobs",
        new=AsyncMock(return_value=[]),
    ) as mock_scrape, patch(
        "src.pipelines.scrape_apify_linkedin_jobs",
        new=AsyncMock(return_value=[]),
    ) as mock_apify, patch("src.pipelines.database.init_db"):
        await run_search_pipeline("QA", mock_eval=True)

        mock_scrape.assert_awaited_once()
        mock_apify.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "platform",
    ["apify_indeed", "apify_glassdoor", "totally_fake"],
)
async def test_pipeline_rejects_unsupported_without_calling_scraper(platform):
    with patch(
        "src.pipelines.scrape_linkedin_jobs",
        new=AsyncMock(return_value=[_make_job()]),
    ) as mock_scrape, patch(
        "src.pipelines.scrape_apify_linkedin_jobs",
        new=AsyncMock(return_value=[_make_job()]),
    ) as mock_apify:
        with pytest.raises(UnsupportedSourcePlatformError, match=platform):
            await run_search_pipeline("QA", platform=platform, mock_eval=True)

        mock_scrape.assert_not_called()
        mock_apify.assert_not_called()


@pytest.mark.asyncio
async def test_search_jobs_forwards_platform_and_rejects_unsupported():
    with patch(
        "src.service.just_apply.run_search_pipeline",
        new=AsyncMock(return_value=[]),
    ) as mock_pipeline:
        await search_jobs(query="QA", platform="brightdata_linkedin", rate_limit=False)
        assert mock_pipeline.await_args.kwargs["platform"] == "brightdata_linkedin"

    with patch(
        "src.service.just_apply.run_search_pipeline",
        new=AsyncMock(return_value=[]),
    ) as mock_pipeline:
        await search_jobs(query="QA", platform="apify_linkedin", rate_limit=False)
        assert mock_pipeline.await_args.kwargs["platform"] == "apify_linkedin"

    with patch(
        "src.service.just_apply.run_search_pipeline",
        new=AsyncMock(return_value=[]),
    ) as mock_pipeline:
        with pytest.raises(UnsupportedSourcePlatformError):
            await search_jobs(query="QA", platform="apify_indeed", rate_limit=False)
        mock_pipeline.assert_not_called()


def test_api_search_rejects_reserved_and_unknown_platforms(client):
    import src.web.server as server_mod

    for platform in ("apify_indeed", "apify_glassdoor", "unknown_x"):
        with patch.object(server_mod, "run_scraping_task"):
            response = client.post("/api/search", json=_valid_payload(platform=platform))
        assert response.status_code == 422, platform
        message = response.json()["message"].lower()
        assert "unsupported" in message or "not supported" in message
        assert platform in response.json()["message"]


def test_api_search_accepts_brightdata_linkedin(client):
    import src.web.server as server_mod

    with patch.object(server_mod, "run_scraping_task"):
        response = client.post("/api/search", json=_valid_payload())
    assert response.status_code == 200
    assert response.json()["status"] == "triggered"


def test_api_search_accepts_apify_linkedin(client):
    import src.web.server as server_mod

    with patch.object(server_mod, "run_scraping_task"):
        response = client.post(
            "/api/search",
            json=_valid_payload(platform="apify_linkedin"),
        )
    assert response.status_code == 200
    assert response.json()["status"] == "triggered"
    task_id = response.json()["task_id"]
    assert server_mod.active_tasks[task_id].params["platform"] == "apify_linkedin"


def test_api_search_forwards_platform_into_task_params(client):
    import src.web.server as server_mod

    with patch.object(server_mod, "run_scraping_task"):
        response = client.post(
            "/api/search",
            json=_valid_payload(platform="brightdata_linkedin"),
        )
    assert response.status_code == 200
    task_id = response.json()["task_id"]
    assert server_mod.active_tasks[task_id].params["platform"] == "brightdata_linkedin"


@pytest.mark.asyncio
async def test_run_scraping_task_passes_platform_to_search_jobs():
    import src.web.server as server_mod

    task_id = "platform-forward-test"
    server_mod.active_tasks[task_id] = server_mod.TaskState(
        {
            "query": "QA",
            "platform": "brightdata_linkedin",
            "active_resume": "qa.md",
            "mock_eval": True,
            "search_regions": [("US", "California")],
            "per_region_limit": 25,
        }
    )
    try:
        with patch.object(
            server_mod,
            "search_jobs",
            new=AsyncMock(return_value=[]),
        ) as mock_search:
            await server_mod.run_scraping_task(task_id)
            assert mock_search.await_args.kwargs["platform"] == "brightdata_linkedin"
    finally:
        server_mod.active_tasks.pop(task_id, None)
