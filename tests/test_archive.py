"""Tests for manual archive on Rejected cards — issue #52."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db import init_db, get_jobs, update_job_status, add_job
from src.db.jobs import archive_job, get_job


# ---------------------------------------------------------------------------
# DB-layer: schema migration
# ---------------------------------------------------------------------------

def test_schema_adds_archived_columns(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    jobs = get_jobs(db_str)
    job = jobs[0]
    assert hasattr(job, "archived")
    assert hasattr(job, "rejectedAt")
    assert hasattr(job, "autoArchiveExempt")


def test_new_job_defaults_not_archived(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = add_job({"title": "Dev", "company": "Acme", "status": "scraped"}, db_str)
    job = get_job(job_id, db_str)
    assert job.archived is False
    assert job.rejectedAt == ""
    assert job.autoArchiveExempt is False


def test_existing_rejected_jobs_get_rejected_at_backfilled(tmp_path):
    """Seed job 5 is in 'rejected' status — it must have rejectedAt set after init_db."""
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    jobs = get_jobs(db_str)
    rejected_jobs = [j for j in jobs if j.status == "rejected"]
    assert rejected_jobs, "seed data should contain at least one rejected job"
    for rj in rejected_jobs:
        assert rj.rejectedAt, f"job {rj.id} is rejected but has no rejectedAt"


# ---------------------------------------------------------------------------
# DB-layer: rejectedAt set on first move to Rejected
# ---------------------------------------------------------------------------

def test_rejected_at_set_on_first_rejection(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = add_job({"title": "Dev", "company": "X"}, db_str)
    updated = update_job_status(job_id, "rejected", db_str)
    assert updated.rejectedAt != ""


def test_rejected_at_not_overwritten_on_later_rejection(tmp_path):
    """Move to rejected, then to another lane, then back to rejected — rejectedAt unchanged."""
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = add_job({"title": "Dev", "company": "X"}, db_str)
    first = update_job_status(job_id, "rejected", db_str)
    first_ts = first.rejectedAt
    assert first_ts

    update_job_status(job_id, "scraped", db_str)
    second = update_job_status(job_id, "rejected", db_str)
    assert second.rejectedAt == first_ts, "rejectedAt must not change on re-rejection"


def test_rejected_at_not_set_for_non_rejected_status(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = add_job({"title": "Dev", "company": "X"}, db_str)
    updated = update_job_status(job_id, "scraped", db_str)
    assert updated.rejectedAt == ""


def test_get_jobs_still_returns_non_archived(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    all_jobs = get_jobs(db_str)
    non_rejected = [j for j in all_jobs if j.status != "rejected"]
    assert non_rejected, "should have non-rejected jobs in seed data"


# ---------------------------------------------------------------------------
# DB-layer: archive_job
# ---------------------------------------------------------------------------

def test_archive_rejected_job(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job5_id = next(j.id for j in get_jobs(db_str) if j.status == "rejected")
    result = archive_job(job5_id, db_str)
    assert result is not None
    assert result.archived is True


def test_archive_logs_archived_to_activity_log(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job5_id = next(j.id for j in get_jobs(db_str) if j.status == "rejected")
    archive_job(job5_id, db_str)
    job = get_job(job5_id, db_str)
    messages = [e.message for e in job.activityLog]
    assert "Archived" in messages


def test_archive_non_rejected_job_returns_none(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    sourced_id = next(j.id for j in get_jobs(db_str) if j.status == "matched")
    result = archive_job(sourced_id, db_str)
    assert result is None


def test_archive_nonexistent_job_returns_none(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    assert archive_job(99999, db_str) is None


# ---------------------------------------------------------------------------
# DB-layer: deduplication still matches archived jobs
# ---------------------------------------------------------------------------

def test_job_exists_returns_true_for_archived_job(tmp_path):
    from src.db import job_exists
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    # Add a job, reject it, archive it
    job_id = add_job({
        "title": "Archived QA",
        "company": "Vanishing Co",
        "link": "https://example.com/archived-job",
        "status": "rejected",
    }, db_str)
    update_job_status(job_id, "rejected", db_str)
    archive_job(job_id, db_str)
    # job_exists must still find it
    assert job_exists("Archived QA", "Vanishing Co", "https://example.com/archived-job", db_str)
    assert job_exists("Archived QA", "Vanishing Co", db_path=db_str)


# ---------------------------------------------------------------------------
# API-layer: POST /api/jobs/{id}/archive
# ---------------------------------------------------------------------------

def test_archive_endpoint_archives_rejected_job(tmp_path):
    from fastapi.testclient import TestClient
    import src.db.connection as _db_connection
    from src.db import init_db as _init_db

    _db_connection.DB_PATH = str(tmp_path / "test.db")
    _init_db(_db_connection.DB_PATH)

    from src.web.server import app
    client = TestClient(app)

    jobs = client.get("/api/jobs").json()
    rejected = next(j for j in jobs if j["status"] == "rejected")
    response = client.post(f"/api/jobs/{rejected['id']}/archive")
    assert response.status_code == 200
    assert response.json()["archived"] is True

    # Job no longer in active board
    jobs_after = client.get("/api/jobs").json()
    assert not any(j["id"] == rejected["id"] for j in jobs_after)


def test_archive_endpoint_rejects_non_rejected_job(tmp_path):
    from fastapi.testclient import TestClient
    import src.db.connection as _db_connection
    from src.db import init_db as _init_db

    _db_connection.DB_PATH = str(tmp_path / "test2.db")
    _init_db(_db_connection.DB_PATH)

    from src.web.server import app
    client = TestClient(app)

    jobs = client.get("/api/jobs").json()
    sourced = next(j for j in jobs if j["status"] == "matched")
    response = client.post(f"/api/jobs/{sourced['id']}/archive")
    assert response.status_code == 422


def test_archive_endpoint_nonexistent_job(tmp_path):
    from fastapi.testclient import TestClient
    import src.db.connection as _db_connection
    from src.db import init_db as _init_db

    _db_connection.DB_PATH = str(tmp_path / "test3.db")
    _init_db(_db_connection.DB_PATH)

    from src.web.server import app
    client = TestClient(app)

    response = client.post("/api/jobs/99999/archive")
    assert response.status_code == 404
