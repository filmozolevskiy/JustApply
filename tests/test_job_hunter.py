import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.cli import run_search, run_promote


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
            "status": "sourced",
            "contacts": [],
        }
    ]

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=mock_jobs) as mock_scrape, \
         patch("src.pipelines.database.init_db"), \
         patch("src.pipelines.database.job_exists", return_value=False), \
         patch("src.pipelines.database.add_job", return_value=1) as mock_add, \
         patch("src.cli.scrape_limiter.acquire"):

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
            "status": "sourced",
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
         patch("src.cli.scrape_limiter.acquire"):

        results = await run_search("QA", mock_eval=False)

        assert mock_eval.called
        assert results[0]["matchScore"] == 88
        assert results[0]["shouldProceed"] is True
        assert results[0]["remoteType"] == "remote"
        assert results[0]["description"] == "This is a concise summary of the QA Lead role."


@pytest.mark.asyncio
async def test_run_promote_reads_sourced_jobs_and_sources_contacts():
    seeded_jobs = [
        {
            "id": 1,
            "title": "QA Engineer",
            "company": "Docker",
            "shouldProceed": True,
            "status": "sourced",
            "contacts": [],
        },
        {
            "id": 2,
            "title": "PM",
            "company": "Google",
            "shouldProceed": False,
            "status": "sourced",
            "contacts": [],
        },
        {
            "id": 3,
            "title": "QA Lead",
            "company": "ACME",
            "shouldProceed": True,
            "status": "applied",  # Already promoted — skip
            "contacts": [],
        },
    ]

    mock_contacts = [{"name": "Jane Recruiter", "title": "Recruiter", "url": "https://linkedin.com/in/jane"}]
    enriched_job = {**seeded_jobs[0], "status": "enriched", "contacts": mock_contacts}

    with patch("src.cli.database.init_db"), \
         patch("src.cli.database.get_jobs", return_value=seeded_jobs), \
         patch("src.cli.cli.begin_enrichment", return_value={**seeded_jobs[0], "status": "enriching"}), \
         patch("src.cli.cli.run_enrichment_pipeline", new=AsyncMock(return_value=enriched_job)) as mock_enrich:

        results = await run_promote()

        # Only job 1 qualifies (shouldProceed=True and status=sourced)
        assert mock_enrich.call_count == 1
        assert len(results) == 1
        assert results[0]["company"] == "Docker"
        assert results[0]["status"] == "enriched"


@pytest.mark.asyncio
async def test_run_promote_handles_no_contacts_gracefully():
    seeded_jobs = [
        {
            "id": 5,
            "title": "QA Analyst",
            "company": "Startup",
            "shouldProceed": True,
            "status": "sourced",
            "contacts": [],
        }
    ]

    enriched_job = {**seeded_jobs[0], "status": "enriched", "contacts": []}

    with patch("src.cli.database.init_db"), \
         patch("src.cli.database.get_jobs", return_value=seeded_jobs), \
         patch("src.cli.cli.begin_enrichment", return_value={**seeded_jobs[0], "status": "enriching"}), \
         patch("src.cli.cli.run_enrichment_pipeline", new=AsyncMock(return_value=enriched_job)):

        results = await run_promote()

        # Job is still included even with no contacts
        assert len(results) == 1
        assert results[0]["status"] == "enriched"


@pytest.mark.asyncio
async def test_run_enrichment_pipeline_sources_contacts_and_persists():
    from src.pipelines import run_enrichment_pipeline

    job = {
        "id": 10,
        "title": "QA Engineer",
        "company": "Docker",
        "resumeUsed": "qa.md",
        "description": "Build test automation.",
        "contacts": [],
        "status": "enriching",
    }
    mock_contacts = [{"name": "Jane", "title": "Recruiter", "url": "https://linkedin.com/in/jane", "contacted": False, "russian_speaker": False}]
    enriched = {**job, "status": "enriched", "contacts": mock_contacts, "outreachMessage": "Hello Jane"}
    mock_templates = {"recruiter": "Hello Jane", "russian_speaker": ""}

    with patch("src.pipelines.source_contacts", new=AsyncMock(return_value=mock_contacts)), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=mock_templates)), \
         patch("src.pipelines.database.enrich_job", return_value=enriched) as mock_save, \
         patch("src.pipelines.database.get_outreach_settings", return_value={"target_russian_speakers": True, "target_recruiters": True}):

        result = await run_enrichment_pipeline(job)

        assert result["status"] == "enriched"
        assert result["contacts"] == mock_contacts
        mock_save.assert_called_once_with(
            10, mock_contacts, "Hello Jane",
            enrichment_note="",
            recruiter_template="Hello Jane",
            russian_speaker_template="",
        )


@pytest.mark.asyncio
async def test_run_enrichment_pipeline_requires_begin_enrichment():
    from src.pipelines import run_enrichment_pipeline

    job = {
        "id": 10,
        "title": "QA Engineer",
        "company": "Docker",
        "resumeUsed": "qa.md",
        "status": "sourced",
        "contacts": [],
    }

    result = await run_enrichment_pipeline(job)
    assert result is None


@pytest.mark.asyncio
async def test_run_enrichment_pipeline_runs_when_already_enriching():
    from src.pipelines import run_enrichment_pipeline

    job = {
        "id": 10,
        "title": "QA Engineer",
        "company": "Docker",
        "resumeUsed": "qa.md",
        "status": "sourced",
        "contacts": [],
    }
    enriched = {**job, "status": "enriched", "contacts": [], "outreachMessage": "Hi"}

    with patch("src.pipelines.database.start_enrichment") as mock_start, \
         patch("src.pipelines.source_contacts", new=AsyncMock(return_value=[])), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value={"recruiter": "Hi", "russian_speaker": ""})), \
         patch("src.pipelines.database.enrich_job", return_value=enriched), \
         patch("src.pipelines.database.get_outreach_settings", return_value={"target_russian_speakers": True, "target_recruiters": True}):

        result = await run_enrichment_pipeline({**job, "status": "enriching"})

    mock_start.assert_not_called()
    assert result["status"] == "enriched"


@pytest.mark.asyncio
async def test_run_enrichment_pipeline_reads_settings_and_passes_to_source_contacts():
    from src.pipelines import run_enrichment_pipeline
    from src.schemas import OutreachSettings

    job = {
        "id": 10,
        "title": "QA Engineer",
        "company": "Docker",
        "resumeUsed": "qa.md",
        "status": "enriching",
        "contacts": [],
    }
    enriched = {**job, "status": "enriched", "contacts": [], "outreachMessage": "Hi"}

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
