"""Tests for auto-archive of stale Rejected jobs — issue #53."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db import add_job, archive_stale_rejected_jobs, get_jobs, init_db, update_job_status
from src.db.jobs import archive_job, get_job

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _add_rejected_job(db_str, backdated_days: int) -> int:
    """Add a job, set it rejected, then manually backdate rejectedAt."""
    import sqlite3
    job_id = add_job({"title": "Stale QA", "company": f"Co-{backdated_days}", "status": "sourced"}, db_str)
    update_job_status(job_id, "rejected", db_str)
    conn = sqlite3.connect(db_str)
    conn.execute(
        "UPDATE jobs SET rejectedAt = datetime('now', ?) WHERE id = ?",
        (f"-{backdated_days} days", job_id),
    )
    conn.commit()
    conn.close()
    return job_id


# ---------------------------------------------------------------------------
# DB-layer: archive_stale_rejected_jobs (explicit sweep)
# ---------------------------------------------------------------------------

def test_archive_stale_rejected_jobs_archives_15_day_old_rejected(tmp_path):
    """Tracer bullet: rejected job with rejectedAt 15 days ago gets archived on sweep."""
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = _add_rejected_job(db_str, 15)

    archive_stale_rejected_jobs(db_str)

    job = get_job(job_id, db_str)
    assert job.archived is True


def test_auto_archived_job_absent_from_active_board(tmp_path):
    """Auto-archived job must not appear in the default get_jobs response."""
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = _add_rejected_job(db_str, 15)

    archive_stale_rejected_jobs(db_str)

    jobs = get_jobs(db_str)

    assert not any(j.id == job_id for j in jobs)


def test_auto_archive_logs_correct_message(tmp_path):
    """Auto-archived job should have 'Auto-archived (rejected 14+ days)' in activity log."""
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = _add_rejected_job(db_str, 15)

    archive_stale_rejected_jobs(db_str)

    job = get_job(job_id, db_str)
    messages = [e.message for e in job.activityLog]
    assert "Auto-archived (rejected 14+ days)" in messages


def test_exempt_job_not_auto_archived(tmp_path):
    """Job with autoArchiveExempt=True must survive the sweep."""
    import sqlite3
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = _add_rejected_job(db_str, 15)
    conn = sqlite3.connect(db_str)
    conn.execute("UPDATE jobs SET autoArchiveExempt = 1 WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()

    archive_stale_rejected_jobs(db_str)

    job = get_job(job_id, db_str)
    assert job.archived is False


def test_non_rejected_job_not_auto_archived(tmp_path):
    """A sourced job with an old rejectedAt (edge case) must not be archived."""
    import sqlite3
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = add_job({"title": "Active Job", "company": "Co"}, db_str)
    # Manually write an old rejectedAt even though status stays sourced
    conn = sqlite3.connect(db_str)
    conn.execute(
        "UPDATE jobs SET rejectedAt = datetime('now', '-20 days') WHERE id = ?", (job_id,)
    )
    conn.commit()
    conn.close()

    archive_stale_rejected_jobs(db_str)

    job = get_job(job_id, db_str)
    assert job.archived is False


def test_job_rejected_13_days_ago_not_auto_archived(tmp_path):
    """Rejected job that is only 13 days old must not yet be auto-archived."""
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = _add_rejected_job(db_str, 13)

    archive_stale_rejected_jobs(db_str)

    job = get_job(job_id, db_str)
    assert job.archived is False


def test_already_archived_job_not_double_archived(tmp_path):
    """Manually archived rejected job must not get an extra activity log entry on sweep."""
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = _add_rejected_job(db_str, 15)
    archive_job(job_id, db_str)  # manual archive first

    archive_stale_rejected_jobs(db_str)

    job = get_job(job_id, db_str)
    auto_entries = [e for e in job.activityLog if "Auto-archived" in e.message]
    assert len(auto_entries) == 0, "sweep must not touch already-archived jobs"


# ---------------------------------------------------------------------------
# API-layer: GET /api/jobs triggers the sweep
# ---------------------------------------------------------------------------

def test_api_get_jobs_triggers_auto_archive(tmp_path):
    """GET /api/jobs must auto-archive stale rejected jobs before returning results."""
    import src.db.connection as _db_connection
    from fastapi.testclient import TestClient
    from src.db import init_db as _init_db

    _db_connection.DB_PATH = str(tmp_path / "test.db")
    _init_db(_db_connection.DB_PATH)

    import sqlite3
    job_id = add_job({"title": "Stale API Job", "company": "APICO"}, _db_connection.DB_PATH)
    update_job_status(job_id, "rejected", _db_connection.DB_PATH)
    conn = sqlite3.connect(_db_connection.DB_PATH)
    conn.execute("UPDATE jobs SET rejectedAt = datetime('now', '-15 days') WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()

    from src.web.server import app
    client = TestClient(app)

    response = client.get("/api/jobs")
    assert response.status_code == 200
    returned_ids = [j["id"] for j in response.json()]
    assert job_id not in returned_ids, "stale rejected job must not appear in active board"

    job = get_job(job_id, _db_connection.DB_PATH)
    assert job.archived is True
