"""Search-orchestration seam: Apify LinkedIn scrape with mocked Actor runner.

No live Actor HTTP. Spec: issue #203.
"""

from unittest.mock import AsyncMock, patch

import pytest
import src.db.connection as _db_connection
from src import db as database
from src.core.apify_linkedin_scraper import scrape_apify_linkedin_jobs
from src.pipelines import run_search_pipeline
from src.rate_limiter import RateLimitError
from src.service.just_apply import acquire_scrape_slot, search_jobs


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MOCK_SCRAPER", "false")
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    test_db = tmp_path / "test_just_apply.db"
    test_db_str = str(test_db)
    monkeypatch.setattr(_db_connection, "DB_PATH", test_db_str)
    database.init_db(test_db_str)
    yield test_db_str


def _actor_row(**overrides):
    row = {
        "title": "Senior QA Engineer",
        "companyName": "Acme Corp",
        "companyLinkedinUrl": "https://www.linkedin.com/company/acme-corp",
        "companyEmployeesCount": 200,
        "link": "https://www.linkedin.com/jobs/view/111",
        "postedAt": "2026-08-01",
        "location": "California",
        "employmentType": "Full-time",
        "salary": "$140k",
        "descriptionText": "QA role.",
        "seniorityLevel": "senior",
        "workplaceTypes": ["Remote"],
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_apify_scrape_calls_runner_once_per_search_region():
    calls: list[dict] = []

    async def fake_runner(*, keywords, location, limit_per_source):
        calls.append(
            {
                "keywords": keywords,
                "location": location,
                "limit_per_source": limit_per_source,
            }
        )
        return [
            _actor_row(
                link=f"https://www.linkedin.com/jobs/view/{location}",
                location=location,
            )
        ]

    jobs = await scrape_apify_linkedin_jobs(
        query="QA Engineer",
        search_regions=[("US", "California"), ("US", "New York")],
        per_region_limit=25,
        force_mock=False,
        apify_runner=fake_runner,
    )

    assert len(calls) == 2
    assert calls[0]["location"] == "California"
    assert calls[1]["location"] == "New York"
    assert calls[0]["limit_per_source"] == 25
    assert calls[0]["keywords"] == "QA Engineer"
    assert len(jobs) == 2
    assert all(j["companyUrl"].endswith("/acme-corp") for j in jobs)
    assert all(j["status"] == "scraped" for j in jobs)


@pytest.mark.asyncio
async def test_apify_mock_scrape_makes_no_runner_call(monkeypatch):
    monkeypatch.setenv("MOCK_SCRAPER", "true")
    runner = AsyncMock(return_value=[_actor_row()])

    jobs = await scrape_apify_linkedin_jobs(
        query="QA",
        search_regions=[("US", "California")],
        force_mock=True,
        apify_runner=runner,
    )

    runner.assert_not_called()
    assert len(jobs) >= 1
    assert jobs[0]["status"] == "scraped"


@pytest.mark.asyncio
async def test_pipeline_apify_mock_never_calls_default_runner():
    with patch(
        "src.core.apify_linkedin_scraper.default_apify_linkedin_runner",
        new=AsyncMock(side_effect=AssertionError("live Actor must not run")),
    ), patch("src.pipelines.database.init_db"), patch(
        "src.pipelines.database.job_exists", return_value=False
    ), patch("src.pipelines.database.add_job", return_value=1), patch(
        "src.pipelines.submit_batch_evaluation", new=AsyncMock()
    ):
        results = await run_search_pipeline(
            "QA",
            platform="apify_linkedin",
            mock_eval=True,
            mock_scraper=True,
            search_regions=[("US", "California")],
            company_sizes="any",
        )

    assert len(results) >= 1
    assert results[0]["status"] == "scraped"


@pytest.mark.asyncio
async def test_search_jobs_rate_limits_billable_apify_scrape(monkeypatch):
    monkeypatch.delenv("MOCK_SCRAPER", raising=False)

    with patch(
        "src.service.just_apply.scrape_limiter.acquire",
        side_effect=RateLimitError("rate limited"),
    ):
        with pytest.raises(RateLimitError):
            await search_jobs(
                query="QA",
                platform="apify_linkedin",
                mock_eval=False,
                mock_scraper=False,
                rate_limit=True,
            )


def test_acquire_scrape_slot_skips_when_mocking(monkeypatch):
    monkeypatch.delenv("MOCK_SCRAPER", raising=False)
    with patch("src.service.just_apply.scrape_limiter.acquire") as acquire:
        acquire_scrape_slot(mock_eval=True, mock_scraper=None)
        acquire.assert_not_called()

        acquire_scrape_slot(mock_eval=False, mock_scraper=True)
        acquire.assert_not_called()

        acquire_scrape_slot(mock_eval=False, mock_scraper=False)
        acquire.assert_called_once()
