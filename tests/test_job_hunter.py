import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.cli import run_search, run_promote
from src.schemas import Job


@pytest.mark.asyncio
async def test_run_search_calls_scraper_and_saves_to_db():
    mock_jobs = [
        {
            "title": "Senior QA Engineer",
            "company": "Acme",
            "size": "100-500",
            "link": "https://example.com/job1",
            "date": "2026-06-07",
            "location": "Remote",
            "remoteType": "remote",
            "seniority": "senior",
            "salary": "$130k",
            "description": "Need a QA engineer.",
            "status": "found",
            "contacts": [],
        }
    ]

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=mock_jobs) as mock_scrape, \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=False), \
         patch("src.pipelines.database.add_job", return_value=1) as mock_add, \
         patch("src.service.job_hunter.scrape_limiter.acquire"):

        results = await run_search("QA", mock_eval=True)

        assert mock_scrape.called
        assert mock_add.call_count == 1
        assert len(results) == 1
        assert results[0]["id"] == 1


@pytest.mark.asyncio
async def test_run_search_calls_evaluate_when_not_mock():
    mock_jobs = [
        {
            "title": "QA Lead",
            "company": "TechCorp",
            "size": "50-200",
            "link": "https://example.com/job2",
            "date": "2026-06-07",
            "location": "Remote",
            "remoteType": "remote",
            "seniority": "senior",
            "salary": "$120k",
            "description": "QA Lead role.",
            "status": "found",
            "contacts": [],
        }
    ]

    mock_evaluation = {
        "matchScore": 88,
        "matchType": "match",
        "shouldProceed": True,
        "strengths": ["Python expertise"],
        "gaps": ["No mobile testing"],
        "remoteType": "hybrid",
        "summary": "This is a concise summary of the QA Lead role."
    }

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=mock_jobs), \
         patch("src.pipelines.load_resume", return_value="# Resume content"), \
         patch("src.pipelines.evaluate_job", return_value=mock_evaluation) as mock_eval, \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=False), \
         patch("src.pipelines.database.add_job", return_value=42), \
         patch("src.service.job_hunter.scrape_limiter.acquire"):

        results = await run_search("QA", mock_eval=False)

        assert mock_eval.called
        assert results[0]["matchScore"] == 88
        assert results[0]["shouldProceed"] is True
        assert results[0]["remoteType"] == "remote"
        assert results[0]["description"] == "This is a concise summary of the QA Lead role."


@pytest.mark.asyncio
async def test_run_promote_reads_found_jobs_and_sources_contacts():
    seeded_jobs = [
        Job(id=1, title="QA Engineer", company="Docker", shouldProceed=True, status="found"),
        Job(id=2, title="PM", company="Google", shouldProceed=False, status="found"),
        Job(id=3, title="QA Lead", company="ACME", shouldProceed=True, status="applied"),
    ]

    mock_contacts = [{"name": "Jane Recruiter", "title": "Recruiter", "url": "https://linkedin.com/in/jane"}]
    enriched_job = Job(**{**seeded_jobs[0].model_dump(), "status": "accepted", "contacts": []})

    with patch("src.service.job_hunter.init_db"), \
         patch("src.service.job_hunter.get_jobs", return_value=seeded_jobs), \
         patch("src.service.job_hunter.begin_enrichment", return_value=Job(**{**seeded_jobs[0].model_dump(), "status": "accepted"})), \
         patch("src.service.job_hunter.complete_enrichment", new=AsyncMock(return_value=enriched_job)) as mock_enrich:

        results = await run_promote()

        # Only job 1 qualifies (shouldProceed=True and status=found)
        assert mock_enrich.call_count == 1
        assert len(results) == 1
        assert results[0].company == "Docker"
        assert results[0].status == "accepted"


@pytest.mark.asyncio
async def test_run_promote_handles_no_contacts_gracefully():
    seeded_jobs = [
        Job(id=5, title="QA Analyst", company="Startup", shouldProceed=True, status="found"),
    ]

    enriched_job = Job(**{**seeded_jobs[0].model_dump(), "status": "accepted"})

    with patch("src.service.job_hunter.init_db"), \
         patch("src.service.job_hunter.get_jobs", return_value=seeded_jobs), \
         patch("src.service.job_hunter.begin_enrichment", return_value=Job(**{**seeded_jobs[0].model_dump(), "status": "accepted"})), \
         patch("src.service.job_hunter.complete_enrichment", new=AsyncMock(return_value=enriched_job)):

        results = await run_promote()

        # Job is still included even with no contacts
        assert len(results) == 1
        assert results[0].status == "accepted"


@pytest.mark.asyncio
async def test_run_enrichment_pipeline_sources_contacts_and_persists():
    from src.pipelines import run_enrichment_pipeline

    job = Job(
        id=10,
        title="QA Engineer",
        company="Docker",
        resumeUsed="qa.md",
        description="Build test automation.",
        status="accepted",
    )
    mock_contacts = [{"name": "Jane", "title": "Recruiter", "url": "https://linkedin.com/in/jane", "contacted": False, "russian_speaker": False}]
    enriched = Job(**{**job.model_dump(), "status": "accepted", "outreachMessage": "Hello Jane"})
    mock_templates = {"recruiter": "Hello Jane", "russian_speaker": ""}

    with patch("src.pipelines.source_contacts", new=AsyncMock(return_value=mock_contacts)), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=mock_templates)), \
         patch("src.pipelines.database.enrich_job", return_value=enriched) as mock_save, \
         patch("src.pipelines.database.get_outreach_settings", return_value={"target_russian_speakers": True, "target_recruiters": True}):

        result = await run_enrichment_pipeline(job)

        assert result.status == "accepted"
        assert len(result.contacts) == 0
        mock_save.assert_called_once_with(
            10, mock_contacts, "Hello Jane",
            enrichment_note="",
            recruiter_template="Hello Jane",
            russian_speaker_template="",
        )


@pytest.mark.asyncio
async def test_run_enrichment_pipeline_requires_begin_enrichment():
    from src.pipelines import run_enrichment_pipeline

    job = Job(
        id=10,
        title="QA Engineer",
        company="Docker",
        resumeUsed="qa.md",
        status="found",
    )

    result = await run_enrichment_pipeline(job)
    assert result is None


@pytest.mark.asyncio
async def test_run_enrichment_pipeline_runs_when_already_accepted():
    from src.pipelines import run_enrichment_pipeline

    job = Job(
        id=10,
        title="QA Engineer",
        company="Docker",
        resumeUsed="qa.md",
        status="accepted",
    )
    enriched = Job(**{**job.model_dump(), "status": "accepted", "outreachMessage": "Hi"})

    with patch("src.pipelines.database.start_enrichment") as mock_start, \
         patch("src.pipelines.source_contacts", new=AsyncMock(return_value=[])), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value={"recruiter": "Hi", "russian_speaker": ""})), \
         patch("src.pipelines.database.enrich_job", return_value=enriched), \
         patch("src.pipelines.database.get_outreach_settings", return_value={"target_russian_speakers": True, "target_recruiters": True}):

        result = await run_enrichment_pipeline(job)

    mock_start.assert_not_called()
    assert result.status == "accepted"


@pytest.mark.asyncio
async def test_run_enrichment_pipeline_reads_settings_and_passes_to_source_contacts():
    from src.pipelines import run_enrichment_pipeline
    from src.schemas import OutreachSettings

    job = Job(
        id=10,
        title="QA Engineer",
        company="Docker",
        resumeUsed="qa.md",
        status="accepted",
    )
    enriched = Job(**{**job.model_dump(), "status": "accepted", "outreachMessage": "Hi"})

    with patch("src.pipelines.database.get_outreach_settings", return_value={"target_russian_speakers": False, "target_recruiters": True}) as mock_get_settings, \
         patch("src.pipelines.source_contacts", new=AsyncMock(return_value=[])) as mock_source, \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value={"recruiter": "Hi", "russian_speaker": ""})), \
         patch("src.pipelines.database.enrich_job", return_value=enriched):

        await run_enrichment_pipeline(job)

    mock_get_settings.assert_called_once()
    called_settings = mock_source.call_args[1]["settings"]
    assert isinstance(called_settings, OutreachSettings)
    assert called_settings.target_russian_speakers is False
    assert called_settings.target_recruiters is True
