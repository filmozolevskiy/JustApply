"""Search-orchestration seam: Apify LinkedIn scrape with mocked Actor runner.

No live Actor HTTP. Spec: issue #203.
Parallel region runs: grilled plan (concurrency 5, partial success, start/finish logs).
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import src.db.connection as _db_connection
from src import db as database
from src.core.apify_linkedin_scraper import (
    APIFY_LINKEDIN_RUN_TIMEOUT_SECONDS,
    ApifyLinkedInScrapeError,
    build_apify_linkedin_actor_input,
    map_time_range_to_date_posted,
    scrape_apify_linkedin_jobs,
)
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

    async def fake_runner(*, actor_input):
        calls.append(actor_input)
        return [
            _actor_row(
                link=f"https://www.linkedin.com/jobs/view/{actor_input['location']}",
                location=actor_input["location"],
            )
        ]

    jobs = await scrape_apify_linkedin_jobs(
        query="QA Engineer",
        search_regions=[("US", "California"), ("US", "New York")],
        per_region_limit=25,
        time_range="past_week",
        force_mock=False,
        apify_runner=fake_runner,
    )

    assert len(calls) == 2
    assert {c["location"] for c in calls} == {"California", "New York"}
    assert all(c["limitPerSource"] == 25 for c in calls)
    assert all(c["keywords"] == "QA Engineer" for c in calls)
    assert all(c["datePosted"] == "pastWeek" for c in calls)
    assert all(c["scrapeCompany"] is False for c in calls)
    assert len(jobs) == 2
    assert all(j["companyUrl"].endswith("/acme-corp") for j in jobs)
    assert all(j["status"] == "scraped" for j in jobs)


@pytest.mark.asyncio
async def test_apify_scrape_runs_regions_with_concurrency_cap(monkeypatch):
    """At most 5 Actor runs in flight (default); 6 regions still all complete."""
    monkeypatch.delenv("APIFY_LINKEDIN_MAX_CONCURRENT_RUNS", raising=False)
    regions = [
        ("US", "California"),
        ("US", "Colorado"),
        ("US", "Florida"),
        ("US", "Georgia"),
        ("US", "Illinois"),
        ("US", "Massachusetts"),
    ]
    current = 0
    max_seen = 0
    lock = asyncio.Lock()

    async def fake_runner(*, actor_input):
        nonlocal current, max_seen
        async with lock:
            current += 1
            max_seen = max(max_seen, current)
        await asyncio.sleep(0.05)
        async with lock:
            current -= 1
        return [
            _actor_row(
                link=f"https://www.linkedin.com/jobs/view/{actor_input['location']}",
                location=actor_input["location"],
            )
        ]

    jobs = await scrape_apify_linkedin_jobs(
        query="QA",
        search_regions=regions,
        per_region_limit=10,
        force_mock=False,
        apify_runner=fake_runner,
    )

    assert max_seen <= 5
    assert max_seen >= 2  # must overlap, not pure serial
    assert len(jobs) == 6


@pytest.mark.asyncio
async def test_apify_scrape_env_overrides_concurrency_cap(monkeypatch):
    monkeypatch.setenv("APIFY_LINKEDIN_MAX_CONCURRENT_RUNS", "2")
    regions = [("US", f"R{i}") for i in range(4)]
    current = 0
    max_seen = 0
    lock = asyncio.Lock()

    async def fake_runner(*, actor_input):
        nonlocal current, max_seen
        async with lock:
            current += 1
            max_seen = max(max_seen, current)
        await asyncio.sleep(0.04)
        async with lock:
            current -= 1
        return [
            _actor_row(
                link=f"https://www.linkedin.com/jobs/view/{actor_input['location']}",
                location=actor_input["location"],
            )
        ]

    await scrape_apify_linkedin_jobs(
        query="QA",
        search_regions=regions,
        force_mock=False,
        apify_runner=fake_runner,
    )
    assert max_seen <= 2
    assert max_seen == 2


@pytest.mark.asyncio
async def test_apify_scrape_partial_success_keeps_jobs_and_warns():
    logs: list[tuple[str, str]] = []

    async def log_func(msg: str, level: str = "info"):
        logs.append((level, msg))

    async def fake_runner(*, actor_input):
        loc = actor_input["location"]
        if loc == "Texas":
            raise ApifyLinkedInScrapeError("boom Texas")
        return [
            _actor_row(
                link=f"https://www.linkedin.com/jobs/view/{loc}",
                location=loc,
            )
        ]

    jobs = await scrape_apify_linkedin_jobs(
        query="QA",
        search_regions=[("US", "California"), ("US", "Texas"), ("US", "Virginia")],
        force_mock=False,
        apify_runner=fake_runner,
        log_func=log_func,
    )

    assert len(jobs) == 2
    assert {j["location"] for j in jobs} == {"California", "Virginia"}
    warning_msgs = [m for level, m in logs if level == "warning"]
    assert any("2/3" in m and "Texas" in m for m in warning_msgs)
    # start + finish lines for each region
    info_msgs = [m for level, m in logs if level == "info"]
    assert any("Actor run:" in m and "California" in m for m in info_msgs)
    assert any("succeeded" in m.lower() and "California" in m for m in info_msgs)
    assert any("failed" in m.lower() and "Texas" in m for m in info_msgs)


@pytest.mark.asyncio
async def test_apify_scrape_all_regions_fail_raises():
    async def fake_runner(*, actor_input):
        raise ApifyLinkedInScrapeError(f"fail {actor_input['location']}")

    with pytest.raises(ApifyLinkedInScrapeError, match="all .* failed|All .* failed"):
        await scrape_apify_linkedin_jobs(
            query="QA",
            search_regions=[("US", "California"), ("US", "Texas")],
            force_mock=False,
            apify_runner=fake_runner,
        )


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


def test_actor_input_disables_company_scrape_by_default():
    """Actor schema defaults scrapeCompany=true; we opt out for speed.

    Company scrape is not a separate PPE event (still $0.001/result) but
    adds per-job HTTP and made run 6KVBJoYhRI5tpkEuq take ~455s.
    """
    actor_input = build_apify_linkedin_actor_input(
        keywords="QA",
        location="Quebec",
        limit_per_source=500,
    )
    assert actor_input["scrapeCompany"] is False
    assert actor_input["keywords"] == "QA"
    assert actor_input["location"] == "Quebec"
    assert actor_input["limitPerSource"] == 500
    assert actor_input["datePosted"] == "anyTime"


def test_map_time_range_to_date_posted():
    assert map_time_range_to_date_posted("any") == "anyTime"
    assert map_time_range_to_date_posted("past_24_hours") == "past24Hours"
    assert map_time_range_to_date_posted("past_week") == "pastWeek"
    assert map_time_range_to_date_posted("past_month") == "pastMonth"
    assert map_time_range_to_date_posted("Past Week") == "pastWeek"


def test_actor_input_maps_board_filters_onto_apify_fields():
    """Send every board filter Apify can still express after LinkedIn AI search."""
    actor_input = build_apify_linkedin_actor_input(
        keywords="QA",
        location="Quebec",
        limit_per_source=100,
        time_range="past_month",
        remote_types=["remote", "hybrid"],
        seniorities=["senior"],
        employment_types=["Full-time"],
    )
    assert actor_input["datePosted"] == "pastMonth"
    assert actor_input["scrapeCompany"] is False
    assert actor_input["autoConvertToAiSearch"] is True
    # LinkedIn dropped separate experience/job-type/workplace URL filters;
    # Actor expects those terms in keywords (same idea as autoConvertToAiSearch).
    assert actor_input["keywords"] == "QA remote hybrid senior Full-time"
    assert "datePosted" in actor_input
    assert "companyIds" not in actor_input or actor_input.get("companyIds") == []


def test_run_timeout_covers_observed_successful_actor_duration():
    """Client must wait longer than live SUCCEEDED run 6KVBJoYhRI5tpkEuq (~455s)."""
    assert APIFY_LINKEDIN_RUN_TIMEOUT_SECONDS >= 600.0
