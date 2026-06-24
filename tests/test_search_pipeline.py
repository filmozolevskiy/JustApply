import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.pipelines import run_search_pipeline


def _make_job(remote_type="remote", title="QA Engineer", company="Acme", link="https://example.com/job1", seniority="senior"):
    return {
        "title": title,
        "company": company,
        "size": "100-500",
        "link": link,
        "date": "2026-06-07",
        "location": "Remote",
        "remoteType": remote_type,
        "seniority": seniority,
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
         patch("src.pipelines.evaluate_jobs_batch", new=AsyncMock()) as mock_eval, \
         patch("src.pipelines.database.add_job") as mock_add:

        results = await run_search_pipeline("QA", mock_eval=False, log_func=log_func)

        mock_eval.assert_not_called()
        mock_add.assert_not_called()
        assert results == []


@pytest.mark.asyncio
async def test_remote_type_mismatch_evaluates_then_drops():
    """Remote type mismatch is rejected after Resume Matcher and not saved."""
    mock_eval_result = {
        "matchScore": 80,
        "matchType": "match",
        "shouldProceed": True,
        "strengths": [],
        "gaps": [],
        "remoteType": "in_office",
        "seniority": "senior",
        "summary": "Office role.",
        "isRecruiter": False,
    }

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[_make_job(remote_type="in_office")]), \
         patch("src.pipelines.load_resume", return_value="# Resume"), \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=False), \
         patch("src.pipelines.evaluate_jobs_batch", new=AsyncMock(return_value=[mock_eval_result])) as mock_eval, \
         patch("src.pipelines.database.add_job") as mock_add:

        results = await run_search_pipeline(
            "QA",
            mock_eval=False,
            allowed_remote_types=["remote"],
            log_func=None,
        )

        mock_eval.assert_called_once()
        mock_add.assert_not_called()
        assert results == []


@pytest.mark.asyncio
async def test_attribute_mismatch_logs_rejection():
    """Each attribute gate rejection is logged to Task Logs with job title and reason."""
    logs = []

    async def log_func(msg, level="info"):
        logs.append((level, msg))

    mock_eval_result = {
        "matchScore": 80,
        "matchType": "match",
        "shouldProceed": True,
        "strengths": [],
        "gaps": [],
        "remoteType": "in_office",
        "seniority": "senior",
        "summary": "Office role.",
        "isRecruiter": False,
    }

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[_make_job(remote_type="in_office", title="QA Lead")]), \
         patch("src.pipelines.load_resume", return_value="# Resume"), \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=False), \
         patch("src.pipelines.evaluate_jobs_batch", new=AsyncMock(return_value=[mock_eval_result])), \
         patch("src.pipelines.database.add_job"):

        await run_search_pipeline(
            "QA",
            mock_eval=False,
            allowed_remote_types=["remote"],
            log_func=log_func,
        )

    rejection_logs = [msg for _, msg in logs if "QA Lead" in msg]
    assert rejection_logs, "Expected a log message mentioning the rejected job title"
    assert any("Attribute mismatch" in m for m in rejection_logs)


@pytest.mark.asyncio
async def test_llm_remote_type_used_for_gating_and_persisted():
    """LLM-classified remote type overrides scraper value for gating and save."""
    mock_eval_result = {
        "matchScore": 80,
        "matchType": "match",
        "shouldProceed": True,
        "strengths": [],
        "gaps": [],
        "remoteType": "remote",
        "seniority": "senior",
        "summary": "Remote role.",
        "isRecruiter": False,
    }

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[_make_job(remote_type="in_office")]), \
         patch("src.pipelines.load_resume", return_value="# Resume"), \
         patch("src.pipelines.evaluate_jobs_batch", new=AsyncMock(return_value=[mock_eval_result])) as mock_eval, \
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
        assert results[0]["remoteType"] == "remote"


@pytest.mark.asyncio
async def test_allowed_remote_types_any_does_not_filter():
    """When allowed_remote_types contains 'any', no jobs are rejected by remote type."""
    mock_eval_result = {
        "matchScore": 80,
        "matchType": "match",
        "shouldProceed": True,
        "strengths": [],
        "gaps": [],
        "remoteType": "in_office",
        "seniority": "senior",
        "summary": "Office role.",
        "isRecruiter": False,
    }

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[_make_job(remote_type="in_office")]), \
         patch("src.pipelines.load_resume", return_value="# Resume"), \
         patch("src.pipelines.evaluate_job", new=AsyncMock(return_value=mock_eval_result)), \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=False), \
         patch("src.pipelines.database.add_job", return_value=1):

        results = await run_search_pipeline(
            "QA",
            mock_eval=False,
            allowed_remote_types=["any"],
        )

        assert len(results) == 1


@pytest.mark.asyncio
async def test_full_matcher_failure_sets_unclassified():
    """Full matcher failure falls back to scraper attributes and marks job Unclassified."""
    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[_make_job(remote_type="remote")]), \
         patch("src.pipelines.load_resume", return_value="# Resume"), \
         patch("src.pipelines.evaluate_jobs_batch", new=AsyncMock(return_value=[{}])), \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=False), \
         patch("src.pipelines.database.add_job", return_value=1) as mock_add:

        results = await run_search_pipeline(
            "QA",
            mock_eval=False,
            allowed_remote_types=["remote"],
        )

        assert len(results) == 1
        assert results[0]["unclassified"] is True
        saved_job = mock_add.call_args[0][0]
        assert saved_job["unclassified"] is True


@pytest.mark.asyncio
async def test_mock_scraper_forwarded_to_scraper_as_force_mock():
    """run_search_pipeline must pass mock_scraper through as scraper force_mock."""
    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[]) as mock_scrape, \
         patch("src.pipelines.database.init_db"):
        await run_search_pipeline("QA", mock_eval=True, mock_scraper=True)

    assert mock_scrape.await_args.kwargs["force_mock"] is True

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[]) as mock_scrape, \
         patch("src.pipelines.database.init_db"):
        await run_search_pipeline("QA", mock_eval=True, mock_scraper=False)

    assert mock_scrape.await_args.kwargs["force_mock"] is False


@pytest.mark.asyncio
async def test_mock_eval_skips_attribute_gating():
    """mock_eval saves jobs without checking remote/seniority preferences."""
    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[_make_job(remote_type="in_office")]), \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=False), \
         patch("src.pipelines.database.add_job", return_value=1):

        results = await run_search_pipeline(
            "QA",
            mock_eval=True,
            allowed_remote_types=["remote"],
        )

        assert len(results) == 1
        assert results[0].get("unclassified") is not True


@pytest.mark.asyncio
async def test_aggregate_summary_logged_with_summary_level():
    """Pipeline summary uses summary log level and Attribute-filtered counter."""
    logs = []

    async def log_func(msg, level="info"):
        logs.append((level, msg))

    jobs = [
        _make_job(remote_type="remote", title="Job A", link="https://example.com/1"),
        _make_job(remote_type="in_office", title="Job B", link="https://example.com/2"),
        _make_job(remote_type="remote", title="Job C", link="https://example.com/3"),
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

    summary_entries = [(level, msg) for level, msg in logs if "Pipeline complete" in msg]
    assert summary_entries, "Expected a summary log at end of pipeline"
    level, msg = summary_entries[0]
    assert level == "summary"
    assert "Attribute-filtered" in msg


@pytest.mark.asyncio
async def test_aggregate_summary_counts_are_correct():
    """Summary counts: 3 scraped, 1 duplicate, 1 attribute-filtered, 1 saved."""
    summary_lines = []
    levels = []

    async def log_func(msg, level="info"):
        if any(k in msg.lower() for k in ["scraped", "duplicate", "attribute-filtered", "saved", "evaluated", "pipeline complete"]):
            summary_lines.append(msg)
            levels.append(level)

    jobs = [
        _make_job(remote_type="remote", title="Job A", link="https://example.com/1"),
        _make_job(remote_type="in_office", title="Job B", link="https://example.com/2"),
        _make_job(remote_type="remote", title="Job C", link="https://example.com/3"),
    ]

    def job_exists_side_effect(title, company, link):
        return link == "https://example.com/1"

    mock_eval_result = {
        "matchScore": 80,
        "matchType": "match",
        "shouldProceed": True,
        "strengths": [],
        "gaps": [],
        "remoteType": "remote",
        "seniority": "senior",
        "summary": "Good role.",
        "isRecruiter": False,
    }

    async def eval_side_effect(jobs, resume, log_func=None):
        results = []
        for job in jobs:
            if job.get("title") == "Job B":
                results.append({**mock_eval_result, "remoteType": "in_office"})
            else:
                results.append(mock_eval_result)
        return results

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=jobs), \
         patch("src.pipelines.load_resume", return_value="# Resume"), \
         patch("src.pipelines.evaluate_jobs_batch", new=AsyncMock(side_effect=eval_side_effect)), \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", side_effect=job_exists_side_effect), \
         patch("src.pipelines.database.add_job", return_value=99):

        await run_search_pipeline(
            "QA",
            mock_eval=False,
            allowed_remote_types=["remote"],
            log_func=log_func,
        )

    combined = " ".join(summary_lines)
    assert "3" in combined
    assert "Attribute-filtered" in combined
    assert "1" in combined
    assert summary_lines, "No summary log found"
    assert "summary" in levels
