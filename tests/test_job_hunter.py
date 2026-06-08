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

    with patch("src.cli.scrape_linkedin_jobs", return_value=mock_jobs) as mock_scrape, \
         patch("src.cli.database.init_db") as mock_init, \
         patch("src.cli.os.path.exists", return_value=False), \
         patch("src.cli.database.add_job", return_value=1) as mock_add:

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

    with patch("src.cli.scrape_linkedin_jobs", return_value=mock_jobs), \
         patch("src.cli.load_resume", return_value="# Resume content"), \
         patch("src.cli.evaluate_job", return_value=mock_evaluation) as mock_eval, \
         patch("src.cli.database.init_db"), \
         patch("src.cli.os.path.exists", return_value=False), \
         patch("src.cli.database.add_job", return_value=42):

        results = await run_search("QA", mock_eval=False)

        assert mock_eval.called
        assert results[0]["matchScore"] == 88
        assert results[0]["shouldProceed"] is True
        assert results[0]["remoteType"] == "hybrid"
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

    with patch("src.cli.database.init_db"), \
         patch("src.cli.database.get_jobs", return_value=seeded_jobs), \
         patch("src.cli.source_contacts", return_value=mock_contacts) as mock_source:

        results = await run_promote()

        # Only job 1 qualifies (shouldProceed=True and status=sourced)
        assert mock_source.call_count == 1
        assert len(results) == 1
        assert results[0]["company"] == "Docker"


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

    with patch("src.cli.database.init_db"), \
         patch("src.cli.database.get_jobs", return_value=seeded_jobs), \
         patch("src.cli.source_contacts", return_value=[]):

        results = await run_promote()

        # Job is still included even with no contacts
        assert len(results) == 1
