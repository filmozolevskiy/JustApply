"""Tracer-bullet: get_jobs reads must not mutate; sweep is explicit."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db import add_job, get_jobs, init_db, update_job_status
from src.db.jobs import archive_stale_rejected_jobs, get_job


def _add_rejected_job(db_str, backdated_days: int) -> int:
    import sqlite3

    job_id = add_job(
        {"title": "Stale QA", "company": f"Co-{backdated_days}", "status": "sourced"},
        db_str,
    )
    update_job_status(job_id, "rejected", db_str)
    conn = sqlite3.connect(db_str)
    conn.execute(
        "UPDATE jobs SET rejectedAt = datetime('now', ?) WHERE id = ?",
        (f"-{backdated_days} days", job_id),
    )
    conn.commit()
    conn.close()
    return job_id


def test_get_jobs_does_not_auto_archive(tmp_path):
    """Pure read: get_jobs must not mutate stale rejected jobs."""
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = _add_rejected_job(db_str, 15)

    get_jobs(db_str)

    job = get_job(job_id, db_str)
    assert job.archived is False


def test_archive_stale_rejected_jobs_archives_stale(tmp_path):
    """Explicit maintenance sweep archives 14+ day rejected jobs."""
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = _add_rejected_job(db_str, 15)

    archived_count = archive_stale_rejected_jobs(db_str)

    assert archived_count == 1
    job = get_job(job_id, db_str)
    assert job.archived is True
