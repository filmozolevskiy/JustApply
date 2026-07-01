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


def test_begin_enrichment_scraped_job_moves_to_accepted(tmp_path):
    """begin_enrichment on a Found job moves it to Accepted."""
    from src.core.enrichment.coordinator import begin_enrichment

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme", "status": "scraped"}, db_str)

    result = begin_enrichment(job_id, db_str)
    assert result is not None
    assert result.status == "accepted"


def test_begin_enrichment_accepted_job_stays_accepted(tmp_path):
    """begin_enrichment on an already-Accepted job returns it unchanged."""
    from src.core.enrichment.coordinator import begin_enrichment
    from src.db import update_job_status

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme", "status": "scraped"}, db_str)
    update_job_status(job_id, "accepted", db_str)

    result = begin_enrichment(job_id, db_str)
    assert result is not None
    assert result.status == "accepted"


def test_begin_enrichment_is_idempotent_no_duplicate_activity_log(tmp_path):
    """Second begin on Accepted does not append duplicate log entries."""
    from src.core.enrichment.coordinator import begin_enrichment

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme", "status": "scraped"}, db_str)

    begin_enrichment(job_id, db_str)
    log_len_after_first = len(get_job(job_id, db_str).activityLog)
    begin_enrichment(job_id, db_str)

    assert len(get_job(job_id, db_str).activityLog) == log_len_after_first


def test_abort_enrichment_leaves_job_accepted(tmp_path):
    """abort_enrichment on an Accepted job keeps it Accepted."""
    from src.core.enrichment.coordinator import begin_enrichment, abort_enrichment

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme", "status": "scraped"}, db_str)

    begin_enrichment(job_id, db_str)
    reverted = abort_enrichment(job_id, db_str)

    assert reverted is not None
    assert reverted.status == "accepted"
    assert get_job(job_id, db_str).status == "accepted"


@pytest.mark.asyncio
async def test_pipeline_rejects_non_accepted_job():
    """run_enrichment_pipeline assumes accepted status; coordinator owns transitions."""
    from unittest.mock import patch
    from src.pipelines import run_enrichment_pipeline

    job = {
        "id": 10,
        "title": "QA",
        "company": "Acme",
        "status": "found",
        "contacts": [],
    }

    result = await run_enrichment_pipeline(job)

    assert result is None
