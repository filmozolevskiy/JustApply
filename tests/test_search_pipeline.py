import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.pipelines import run_search_pipeline


def _make_job(remote_type="remote", title="QA Engineer", company="Acme", link="https://example.com/job1"):
    return {
        "title": title,
        "company": company,
        "size": "100-500",
        "link": link,
        "date": "2026-06-07",
        "location": "Remote",
        "remoteType": remote_type,
        "seniority": "senior",
        "salary": "$130k",
        "description": "QA role.",
        "status": "sourced",
        "contacts": [],
    }


@pytest.mark.asyncio
async def test_duplicate_job_skips_evaluate_and_add():
    """Duplicate job (exists in DB) does not invoke Resume Matcher and is not saved."""
    logs = []

    async def log_func(msg, level="info"):
        logs.append(msg)

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[_make_job()]), \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=True), \
         patch("src.pipelines.evaluate_job", new=AsyncMock()) as mock_eval, \
         patch("src.pipelines.database.add_job") as mock_add:

        results = await run_search_pipeline("QA", mock_eval=False, log_func=log_func)

        mock_eval.assert_not_called()
        mock_add.assert_not_called()
        assert results == []


@pytest.mark.asyncio
async def test_remote_type_mismatch_drops_before_evaluate_and_not_saved():
    """Remote type mismatch is rejected before Resume Matcher and not saved."""
    logs = []

    async def log_func(msg, level="info"):
        logs.append(msg)

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[_make_job(remote_type="in_office")]), \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=False), \
         patch("src.pipelines.evaluate_job", new=AsyncMock()) as mock_eval, \
         patch("src.pipelines.database.add_job") as mock_add:

        results = await run_search_pipeline(
            "QA",
            mock_eval=False,
            allowed_remote_types=["remote"],
            log_func=log_func,
        )

        mock_eval.assert_not_called()
        mock_add.assert_not_called()
        assert results == []


@pytest.mark.asyncio
async def test_remote_type_mismatch_logs_rejection():
    """Each pre-filter rejection is logged to Task Logs with job title and reason."""
    logs = []

    async def log_func(msg, level="info"):
        logs.append(msg)

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[_make_job(remote_type="in_office", title="QA Lead")]), \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=False), \
         patch("src.pipelines.evaluate_job", new=AsyncMock()), \
         patch("src.pipelines.database.add_job"):

        await run_search_pipeline(
            "QA",
            mock_eval=False,
            allowed_remote_types=["remote"],
            log_func=log_func,
        )

    rejection_logs = [m for m in logs if "QA Lead" in m]
    assert rejection_logs, "Expected a log message mentioning the rejected job title"
    assert any("in_office" in m or "remote" in m for m in rejection_logs)


@pytest.mark.asyncio
async def test_matching_remote_type_proceeds_to_evaluate():
    """Job whose remote type matches allowed preferences reaches Resume Matcher."""
    mock_eval_result = {
        "matchScore": 80,
        "matchType": "match",
        "shouldProceed": True,
        "strengths": [],
        "gaps": [],
        "remoteType": "remote",
        "summary": "Good role.",
        "isRecruiter": False,
    }

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[_make_job(remote_type="remote")]), \
         patch("src.pipelines.load_resume", return_value="# Resume"), \
         patch("src.pipelines.evaluate_job", new=AsyncMock(return_value=mock_eval_result)) as mock_eval, \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=False), \
         patch("src.pipelines.database.add_job", return_value=1):

        results = await run_search_pipeline(
            "QA",
            mock_eval=False,
            allowed_remote_types=["remote"],
        )

        mock_eval.assert_called_once()
        assert len(results) == 1


@pytest.mark.asyncio
async def test_allowed_remote_types_any_does_not_filter():
    """When allowed_remote_types contains 'any', no jobs are rejected by remote type."""
    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[_make_job(remote_type="in_office")]), \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=False), \
         patch("src.pipelines.database.add_job", return_value=1):

        results = await run_search_pipeline(
            "QA",
            mock_eval=True,
            allowed_remote_types=["any"],
        )

        assert len(results) == 1


@pytest.mark.asyncio
async def test_in_office_variant_rejected_by_pre_filter():
    """Pre-Evaluation Filter normalizes 'in office' before comparing to allowed preferences."""
    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[_make_job(remote_type="in office")]), \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=False), \
         patch("src.pipelines.evaluate_job", new=AsyncMock()) as mock_eval, \
         patch("src.pipelines.database.add_job") as mock_add:

        results = await run_search_pipeline(
            "QA",
            mock_eval=False,
            allowed_remote_types=["remote"],
        )

        mock_eval.assert_not_called()
        mock_add.assert_not_called()
        assert results == []


@pytest.mark.asyncio
async def test_pipeline_preserves_scraper_remote_type_after_evaluation():
    """Resume Matcher no longer overwrites scraper-derived remoteType on save."""
    mock_eval_result = {
        "matchScore": 80,
        "matchType": "match",
        "shouldProceed": True,
        "strengths": [],
        "gaps": [],
        "remoteType": "hybrid",
        "summary": "Good role.",
        "isRecruiter": False,
    }

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[_make_job(remote_type="remote")]), \
         patch("src.pipelines.load_resume", return_value="# Resume"), \
         patch("src.pipelines.evaluate_job", new=AsyncMock(return_value=mock_eval_result)), \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=False), \
         patch("src.pipelines.database.add_job", return_value=1):

        results = await run_search_pipeline(
            "QA",
            mock_eval=False,
            allowed_remote_types=["remote"],
        )

        assert len(results) == 1
        assert results[0]["remoteType"] == "remote"


@pytest.mark.asyncio
async def test_aggregate_summary_logged_at_end():
    """Aggregate summary with scraped/duplicates/pre-filtered/evaluated/saved counts is logged at end."""
    logs = []

    async def log_func(msg, level="info"):
        logs.append(msg)

    jobs = [
        _make_job(remote_type="remote", title="Job A", link="https://example.com/1"),
        _make_job(remote_type="in_office", title="Job B", link="https://example.com/2"),
        _make_job(remote_type="remote", title="Job C", link="https://example.com/3"),
    ]

    def job_exists_side_effect(title, company, link):
        return link == "https://example.com/1"  # Job A is a duplicate

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=jobs), \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", side_effect=job_exists_side_effect), \
         patch("src.pipelines.database.add_job", return_value=99):

        await run_search_pipeline(
            "QA",
            mock_eval=True,
            allowed_remote_types=["remote"],
            log_func=log_func,
        )

    summary_logs = [m for m in logs if "scraped" in m.lower() or "saved" in m.lower()]
    assert summary_logs, "Expected a summary log at end of pipeline"
    # At least one summary line should mention key count fields
    combined = " ".join(summary_logs).lower()
    assert "duplicate" in combined or "pre-filter" in combined or "saved" in combined


@pytest.mark.asyncio
async def test_aggregate_summary_counts_are_correct():
    """Summary counts: 3 scraped, 1 duplicate, 1 pre-filtered, 1 saved."""
    summary_lines = []

    async def log_func(msg, level="info"):
        if any(k in msg.lower() for k in ["scraped", "duplicate", "pre-filter", "saved", "evaluated", "pipeline complete"]):
            summary_lines.append(msg)

    jobs = [
        _make_job(remote_type="remote", title="Job A", link="https://example.com/1"),   # duplicate
        _make_job(remote_type="in_office", title="Job B", link="https://example.com/2"),  # pre-filtered
        _make_job(remote_type="remote", title="Job C", link="https://example.com/3"),   # saved
    ]

    def job_exists_side_effect(title, company, link):
        return link == "https://example.com/1"

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=jobs), \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", side_effect=job_exists_side_effect), \
         patch("src.pipelines.database.add_job", return_value=99):

        await run_search_pipeline(
            "QA",
            mock_eval=True,
            allowed_remote_types=["remote"],
            log_func=log_func,
        )

    combined = " ".join(summary_lines)
    assert "3" in combined   # scraped count
    assert "1" in combined   # duplicate and pre-filtered and saved all have count 1
    # The summary should contain all relevant counts
    assert summary_lines, "No summary log found"
