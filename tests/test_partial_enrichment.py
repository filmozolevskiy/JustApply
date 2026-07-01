"""Tests for partial enrichment success and Enrichment Notes.

Issue #79: When dual-audience is on and at least one stream keeps contacts but
another stream has zero, the job should be a partial success (not Enrichment Failure)
with a warning Enrichment Note naming the empty stream(s) and suggesting Load More.

Full failure (zero kept across all active streams) is unchanged.
"""
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.db.connection as _db_connection
from src import db as database
from src.core.enrichment.coordinator import begin_enrichment
from src.db.connection import init_db


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(_db_connection, "DB_PATH", db_path)
    init_db(db_path)
    return db_path


def _accepted_job(db):
    begin_enrichment(1, db)
    return database.get_job(1, db_path=db)


_TEMPLATES = {"recruiter": "Hello recruiter.", "russian_speaker": "Hello Russian."}
_EMPTY_TEMPLATES = {"recruiter": "", "russian_speaker": ""}


# ─── Tracer bullet: dual-audience, recruiters kept, zero Russian ────────────

@pytest.mark.asyncio
async def test_partial_success_recruiters_kept_zero_russian_sets_warning_note(db):
    """Dual-audience: 3 recruiters kept, 0 Russian contacts → partial success, warning note."""
    database.save_outreach_settings(
        target_russian_speakers=True,
        target_recruiters=True,
        short_connection_note=False,
        db_path=db,
    )
    recruiter_contacts = [
        {"name": f"HR{i}", "is_recruiter": True, "russian_speaker": False,
         "url": f"https://linkedin.com/in/hr{i}", "contacted": False, "is_job_poster": False}
        for i in range(3)
    ]

    with patch("src.pipelines.source_contacts", new=AsyncMock(return_value=recruiter_contacts)), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=_TEMPLATES)):
        from src.pipelines import run_enrichment_pipeline
        job = _accepted_job(db)
        result = await run_enrichment_pipeline(job)

    assert result is not None
    assert result.status == "accepted"
    assert "Russian Speakers" in result.enrichmentNote
    assert "Load More" in result.enrichmentNote
    assert result.enrichmentNoteKind == "warning"


# ─── Russian kept, zero recruiters ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_partial_success_russian_kept_zero_recruiters_sets_warning_note(db):
    """Dual-audience: 5 Russian contacts kept, 0 recruiters → partial success, warning note."""
    database.save_outreach_settings(
        target_russian_speakers=True,
        target_recruiters=True,
        short_connection_note=False,
        db_path=db,
    )
    russian_contacts = [
        {"name": f"RU{i}", "is_recruiter": False, "russian_speaker": True,
         "url": f"https://linkedin.com/in/ru{i}", "contacted": False, "is_job_poster": False}
        for i in range(5)
    ]

    with patch("src.pipelines.source_contacts", new=AsyncMock(return_value=russian_contacts)), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=_TEMPLATES)):
        from src.pipelines import run_enrichment_pipeline
        job = _accepted_job(db)
        result = await run_enrichment_pipeline(job)

    assert result is not None
    assert result.status == "accepted"
    assert "Recruiters" in result.enrichmentNote
    assert "Load More" in result.enrichmentNote
    assert result.enrichmentNoteKind == "warning"


# ─── Both streams empty → full failure (unchanged) ──────────────────────────

@pytest.mark.asyncio
async def test_dual_audience_zero_all_contacts_is_full_failure(db):
    """Dual-audience: zero contacts from all streams → Enrichment Failure, no contacts."""
    database.save_outreach_settings(
        target_russian_speakers=True,
        target_recruiters=True,
        short_connection_note=False,
        db_path=db,
    )

    with patch("src.pipelines.source_contacts", new=AsyncMock(return_value=[])), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=_EMPTY_TEMPLATES)):
        from src.pipelines import run_enrichment_pipeline
        job = _accepted_job(db)
        result = await run_enrichment_pipeline(job)

    assert result is not None
    assert result.enrichmentNote != ""
    # Full failure: note should NOT mention "Load More" (it's about no-match, not a partial)
    assert "Load More" not in result.enrichmentNote


# ─── Both streams have contacts → clean success, no note ────────────────────

@pytest.mark.asyncio
async def test_dual_audience_both_streams_have_contacts_clears_note(db):
    """Dual-audience: recruiters AND Russian contacts kept → no enrichment note."""
    database.save_outreach_settings(
        target_russian_speakers=True,
        target_recruiters=True,
        short_connection_note=False,
        db_path=db,
    )
    both_contacts = [
        {"name": "Alice", "is_recruiter": True, "russian_speaker": False,
         "url": "https://linkedin.com/in/alice", "contacted": False, "is_job_poster": False},
        {"name": "Ivan", "is_recruiter": False, "russian_speaker": True,
         "url": "https://linkedin.com/in/ivan", "contacted": False, "is_job_poster": False},
    ]

    with patch("src.pipelines.source_contacts", new=AsyncMock(return_value=both_contacts)), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=_TEMPLATES)):
        from src.pipelines import run_enrichment_pipeline
        job = _accepted_job(db)
        result = await run_enrichment_pipeline(job)

    assert result is not None
    assert result.enrichmentNote == ""
    assert result.status == "accepted"


# ─── Partial success is not logged as "Enrichment failed" ───────────────────

@pytest.mark.asyncio
async def test_partial_success_not_logged_as_enrichment_failed(db):
    """Partial success (warning note) should not write 'Enrichment failed' to the activity log."""
    database.save_outreach_settings(
        target_russian_speakers=True,
        target_recruiters=True,
        short_connection_note=False,
        db_path=db,
    )
    recruiter_contacts = [
        {"name": "Alice", "is_recruiter": True, "russian_speaker": False,
         "url": "https://linkedin.com/in/alice", "contacted": False, "is_job_poster": False},
    ]

    with patch("src.pipelines.source_contacts", new=AsyncMock(return_value=recruiter_contacts)), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=_TEMPLATES)):
        from src.pipelines import run_enrichment_pipeline
        job = _accepted_job(db)
        result = await run_enrichment_pipeline(job)

    assert result is not None
    activity_log = result.activityLog or []
    log_messages = [entry.message for entry in activity_log]
    assert not any("Enrichment failed" in msg for msg in log_messages), (
        f"Expected no 'Enrichment failed' in log, got: {log_messages}"
    )


# ─── Single-stream modes are unaffected by partial success logic ────────────

@pytest.mark.asyncio
async def test_recruiter_only_zero_contacts_is_failure_not_partial(db):
    """Recruiter-only mode: zero contacts → Enrichment Failure (no partial-success logic)."""
    database.save_outreach_settings(
        target_russian_speakers=False,
        target_recruiters=True,
        short_connection_note=False,
        db_path=db,
    )

    with patch("src.pipelines.source_contacts", new=AsyncMock(return_value=[])), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=_EMPTY_TEMPLATES)):
        from src.pipelines import run_enrichment_pipeline
        job = _accepted_job(db)
        result = await run_enrichment_pipeline(job)

    assert result is not None
    assert result.enrichmentNote != ""
    assert "Load More" not in result.enrichmentNote
