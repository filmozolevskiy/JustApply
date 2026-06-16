"""Tracer tests: EnrichmentCoordinator owns enrichment status transitions."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db import init_db, add_job, get_job


def _fresh_db(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    return db_str


def test_begin_enrichment_is_idempotent_no_duplicate_activity_log(tmp_path):
    """Second begin while already enriching does not append another Enrichment started entry."""
    from src.core.enrichment.coordinator import begin_enrichment

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme", "status": "sourced"}, db_str)

    first = begin_enrichment(job_id, db_str)
    assert first.status == "enriching"

    log_len_after_first = len(get_job(job_id, db_str).activityLog)
    second = begin_enrichment(job_id, db_str)
    assert second.status == "enriching"

    messages = [e.message for e in get_job(job_id, db_str).activityLog]
    assert messages.count("Enrichment started") == 1
    assert len(get_job(job_id, db_str).activityLog) == log_len_after_first


def test_abort_enrichment_reverts_sourced_job(tmp_path):
    """Infrastructure failure before completion returns a sourced job to Sourced."""
    from src.core.enrichment.coordinator import begin_enrichment, abort_enrichment

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme", "status": "sourced"}, db_str)

    begin_enrichment(job_id, db_str)
    reverted = abort_enrichment(job_id, db_str)

    assert reverted.status == "sourced"
    assert get_job(job_id, db_str).status == "sourced"


def test_abort_enrichment_reverts_enriched_job_after_refresh(tmp_path):
    """Refresh Contacts failure returns an enriched job to Enriched."""
    from src.core.enrichment.coordinator import begin_enrichment, abort_enrichment
    from src.db import enrich_job

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme", "status": "sourced"}, db_str)
    enrich_job(job_id, [], "Hi", db_path=db_str)

    begin_enrichment(job_id, db_str)
    reverted = abort_enrichment(job_id, db_str)

    assert reverted.status == "enriched"
    assert get_job(job_id, db_str).status == "enriched"


@pytest.mark.asyncio
async def test_pipeline_does_not_call_start_enrichment():
    """run_enrichment_pipeline assumes enriching status; coordinator owns transitions."""
    from unittest.mock import patch
    from src.pipelines import run_enrichment_pipeline

    job = {
        "id": 10,
        "title": "QA",
        "company": "Acme",
        "status": "sourced",
        "contacts": [],
    }

    with patch("src.pipelines.database.start_enrichment") as mock_start:
        result = await run_enrichment_pipeline(job)

    mock_start.assert_not_called()
    assert result is None
