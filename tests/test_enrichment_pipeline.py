import os
import sys
import pytest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db import init_db, get_job, enrich_job


@pytest.fixture
def db(tmp_path, monkeypatch):
    import src.db.connection as _db_connection
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(_db_connection, "DB_PATH", db_path)
    init_db(db_path)
    return db_path


_EMPTY_TEMPLATES = {"recruiter": "", "russian_speaker": ""}
_BOTH_TEMPLATES = {
    "recruiter": "Hello ______,\nAcme – QA.\nMy experience align well with the requirements.\nI would be grateful to connect and share my CV.",
    "russian_speaker": "Hello ______,\nAcme – QA.\nMy experience align well with the requirements.\nI'd be grateful if you could refer me for the role.",
}


@pytest.mark.asyncio
async def test_enrichment_no_employees_sets_specific_note(db):
    """Zero Apify profiles sets a company-specific enrichmentNote."""
    log_records = []

    async def capture_log(msg, level="info"):
        log_records.append((msg, level))

    async def mock_source_contacts(job, settings=None, log_func=None, bust_cache=False, meta=None):
        if meta is not None:
            meta["empty_reason"] = "no_employees"
        return []

    with patch("src.pipelines.source_contacts", new=mock_source_contacts), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=_EMPTY_TEMPLATES)):
        from src.pipelines import run_enrichment_pipeline
        job = get_job(1, db_path=db)
        result = await run_enrichment_pipeline(job, log_func=capture_log)

    assert result["enrichmentNote"] == "No LinkedIn employees found for this company."


@pytest.mark.asyncio
async def test_enrichment_failure_zero_contacts_sets_note(db):
    """Zero contacts sets a non-empty enrichmentNote on the job."""
    with patch("src.pipelines.source_contacts", new=AsyncMock(return_value=[])), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=_EMPTY_TEMPLATES)):
        from src.pipelines import run_enrichment_pipeline
        job = get_job(1, db_path=db)
        result = await run_enrichment_pipeline(job)

    assert result is not None
    assert result["enrichmentNote"] != ""
    assert result["status"] == "enriched"


@pytest.mark.asyncio
async def test_enrichment_infrastructure_error_sets_note(db):
    """Infrastructure error during source_contacts sets enrichmentNote."""
    with patch("src.pipelines.source_contacts", new=AsyncMock(side_effect=Exception("Apify trigger failed: HTTP 403"))), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=_EMPTY_TEMPLATES)):
        from src.pipelines import run_enrichment_pipeline
        job = get_job(1, db_path=db)
        result = await run_enrichment_pipeline(job)

    assert result is not None
    assert result["enrichmentNote"] != ""
    assert result["status"] == "enriched"


@pytest.mark.asyncio
async def test_enrichment_success_clears_note(db):
    """Successful enrichment clears a pre-existing enrichmentNote."""
    enrich_job(1, [], "old msg", enrichment_note="old failure", db_path=db)

    contacts = [{"name": "Alice", "url": "https://linkedin.com/in/alice",
                 "contacted": False, "russian_speaker": True, "is_recruiter": False, "is_job_poster": False}]
    with patch("src.pipelines.source_contacts", new=AsyncMock(return_value=contacts)), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=_BOTH_TEMPLATES)):
        from src.pipelines import run_enrichment_pipeline
        job = get_job(1, db_path=db)
        result = await run_enrichment_pipeline(job)

    assert result is not None
    assert result["enrichmentNote"] == ""
    assert result["status"] == "enriched"


@pytest.mark.asyncio
async def test_enrichment_zero_contacts_logs_final_error(db):
    """Pipeline logs final line as 'error' level when no contacts found."""
    log_records = []

    async def capture_log(msg, level="info"):
        log_records.append((msg, level))

    with patch("src.pipelines.source_contacts", new=AsyncMock(return_value=[])), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=_EMPTY_TEMPLATES)):
        from src.pipelines import run_enrichment_pipeline
        job = get_job(1, db_path=db)
        await run_enrichment_pipeline(job, log_func=capture_log)

    assert log_records, "No log lines emitted"
    final_level = log_records[-1][1]
    assert final_level == "error", f"Expected final log level 'error', got {final_level!r}"


@pytest.mark.asyncio
async def test_enrichment_success_logs_final_success(db):
    """Pipeline logs final line as 'success' level when contacts found."""
    log_records = []

    async def capture_log(msg, level="info"):
        log_records.append((msg, level))

    contacts = [{"name": "Alice", "url": "https://linkedin.com/in/alice",
                 "contacted": False, "russian_speaker": True}]
    with patch("src.pipelines.source_contacts", new=AsyncMock(return_value=contacts)), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=_BOTH_TEMPLATES)):
        from src.pipelines import run_enrichment_pipeline
        job = get_job(1, db_path=db)
        await run_enrichment_pipeline(job, log_func=capture_log)

    assert log_records, "No log lines emitted"
    final_level = log_records[-1][1]
    assert final_level == "success", f"Expected final log level 'success', got {final_level!r}"


@pytest.mark.asyncio
async def test_enrichment_pipeline_persists_both_outreach_templates(db):
    """Pipeline passes both audience templates to enrich_job."""
    contacts = [
        {"name": "Sarah", "is_recruiter": True, "russian_speaker": False, "url": "", "contacted": False},
        {"name": "Ivan", "is_recruiter": False, "russian_speaker": True, "url": "", "contacted": False},
    ]
    with patch("src.pipelines.source_contacts", new=AsyncMock(return_value=contacts)), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=_BOTH_TEMPLATES)):
        from src.pipelines import run_enrichment_pipeline
        job = get_job(1, db_path=db)
        result = await run_enrichment_pipeline(job)

    assert result is not None
    assert result["recruiterOutreachTemplate"] == _BOTH_TEMPLATES["recruiter"]
    assert result["russianSpeakerOutreachTemplate"] == _BOTH_TEMPLATES["russian_speaker"]
