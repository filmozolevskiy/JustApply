from unittest.mock import AsyncMock, patch

import pytest
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
async def test_duplicate_job_skips_save_and_batch_submit():
    """Duplicate job (exists in DB) is not saved or submitted for batch evaluation."""
    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[_make_job()]), \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=True), \
         patch("src.pipelines.submit_batch_evaluation", new=AsyncMock()) as mock_submit, \
         patch("src.pipelines.database.add_job") as mock_add:

        results = await run_search_pipeline("QA", mock_eval=False, log_func=None)

        mock_submit.assert_not_called()
        mock_add.assert_not_called()
        assert results == []


@pytest.mark.asyncio
async def test_search_saves_scraped_before_batch_submit():
    """New jobs are saved to Scraped with empty matchType, then submitted asynchronously."""
    call_order = []

    def fake_add(job):
        call_order.append(("add", job.get("matchType")))
        return 99

    async def fake_submit(jobs, resume, kind, log_func=None, **kwargs):
        call_order.append(("submit", [job["id"] for job in jobs]))
        return [{"batchName": "batches/test", "jobIds": [job["id"] for job in jobs]}]

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[_make_job()]), \
         patch("src.pipelines.load_resume", return_value="# Resume"), \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=False), \
         patch("src.pipelines.database.add_job", side_effect=fake_add), \
         patch("src.pipelines.submit_batch_evaluation", side_effect=fake_submit):

        results = await run_search_pipeline("QA", mock_eval=False, allowed_remote_types=["remote"])

        assert call_order[0] == ("add", "")
        assert call_order[1] == ("submit", [99])
        assert len(results) == 1
        assert results[0]["id"] == 99
        assert results[0]["matchType"] == ""


@pytest.mark.asyncio
async def test_remote_type_mismatch_still_saved_and_submitted():
    """Scraper remote-type mismatch no longer blocks save; batch submission still runs."""
    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[_make_job(remote_type="in_office")]), \
         patch("src.pipelines.load_resume", return_value="# Resume"), \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=False), \
         patch("src.pipelines.submit_batch_evaluation", new=AsyncMock(return_value=[{"batchName": "batches/x"}])) as mock_submit, \
         patch("src.pipelines.database.add_job", return_value=1) as mock_add:

        results = await run_search_pipeline(
            "QA",
            mock_eval=False,
            allowed_remote_types=["remote"],
        )

        mock_submit.assert_called_once()
        mock_add.assert_called_once()
        assert len(results) == 1
        saved_job = mock_add.call_args[0][0]
        assert saved_job["status"] == "scraped"
        assert saved_job["matchType"] == ""


@pytest.mark.asyncio
async def test_rejected_job_in_db_blocks_rescrape(tmp_path, monkeypatch):
    """Previously rejected jobs persist and are skipped by dedup on re-scrape."""
    from src import db as database

    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database.connection, "DB_PATH", str(db_path))
    database.init_db(str(db_path))
    database.add_job(
        {
            "title": "QA Engineer",
            "company": "Acme",
            "link": "https://example.com/job1",
            "status": "rejected",
            "matchType": "no-match",
        },
        db_path=str(db_path),
    )

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[_make_job()]), \
         patch("src.pipelines.load_resume", return_value="# Resume"), \
         patch("src.pipelines.submit_batch_evaluation", new=AsyncMock()) as mock_submit, \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", side_effect=database.job_exists), \
         patch("src.pipelines.database.add_job", side_effect=database.add_job):

        monkeypatch.setattr(database.connection, "DB_PATH", str(db_path))
        results = await run_search_pipeline("QA", mock_eval=False)

        mock_submit.assert_not_called()
        assert results == []


@pytest.mark.asyncio
async def test_allowed_remote_types_any_still_saves_and_submits():
    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[_make_job(remote_type="in_office")]), \
         patch("src.pipelines.load_resume", return_value="# Resume"), \
         patch("src.pipelines.submit_batch_evaluation", new=AsyncMock(return_value=[{}])), \
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
async def test_mock_scraper_forwarded_to_scraper_as_force_mock():
    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[]) as mock_scrape, \
         patch("src.pipelines.database.init_db"):
        await run_search_pipeline("QA", mock_eval=True, mock_scraper=True)

    assert mock_scrape.await_args.kwargs["force_mock"] is True

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[]) as mock_scrape, \
         patch("src.pipelines.database.init_db"):
        await run_search_pipeline("QA", mock_eval=True, mock_scraper=False)

    assert mock_scrape.await_args.kwargs["force_mock"] is False


@pytest.mark.asyncio
async def test_mock_eval_skips_batch_submission():
    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[_make_job(remote_type="in_office")]), \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=False), \
         patch("src.pipelines.submit_batch_evaluation", new=AsyncMock()) as mock_submit, \
         patch("src.pipelines.database.add_job", return_value=1):

        results = await run_search_pipeline(
            "QA",
            mock_eval=True,
            allowed_remote_types=["remote"],
        )

        mock_submit.assert_not_called()
        assert len(results) == 1


@pytest.mark.asyncio
async def test_aggregate_summary_logged_with_summary_level():
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
    assert "Saved to Scraped" in msg


@pytest.mark.asyncio
async def test_submit_batch_evaluation_receives_only_new_saved_jobs():
    jobs = [
        _make_job(title="Job A", link="https://example.com/1"),
        _make_job(title="Job B", link="https://example.com/2"),
    ]

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=jobs), \
         patch("src.pipelines.load_resume", return_value="# Resume"), \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=False), \
         patch("src.pipelines.database.add_job", side_effect=[10, 11]), \
         patch("src.pipelines.submit_batch_evaluation", new=AsyncMock(return_value=[{}])) as mock_submit:

        await run_search_pipeline("QA", mock_eval=False)

    submitted_jobs = mock_submit.await_args.args[0]
    assert [job["id"] for job in submitted_jobs] == [10, 11]
    assert mock_submit.await_args.kwargs["kind"] == "search"


@pytest.mark.asyncio
async def test_large_search_chunks_via_submit_batch_evaluation():
    jobs = [
        _make_job(title=f"Job {i}", link=f"https://example.com/{i}")
        for i in range(150)
    ]

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=jobs), \
         patch("src.pipelines.load_resume", return_value="# Resume"), \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=False), \
         patch("src.pipelines.database.add_job", side_effect=list(range(1, 151))), \
         patch("src.pipelines.submit_batch_evaluation", new=AsyncMock(return_value=[{}, {}])) as mock_submit:

        await run_search_pipeline("QA", mock_eval=False)

    submitted_jobs = mock_submit.await_args.args[0]
    assert len(submitted_jobs) == 150
