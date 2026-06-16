"""Tracer-bullet: Job is the canonical type returned from DB reads."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import db as database


@pytest.fixture()
def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    database.init_db(db_path)
    return db_path


def test_get_job_returns_job_model(db):
    from src.schemas import Job

    job_id = database.add_job(
        {"title": "QA Engineer", "company": "Acme", "status": "sourced"},
        db_path=db,
    )
    job = database.get_job(job_id, db_path=db)
    assert isinstance(job, Job)
    assert job.title == "QA Engineer"
    assert job.id == job_id


def test_get_jobs_returns_job_models(db):
    from src.schemas import Job

    jobs = database.get_jobs(db_path=db)
    assert len(jobs) > 0
    assert all(isinstance(j, Job) for j in jobs)


def test_legacy_outreach_message_migrated_on_read(db):
    """Read-time migration: outreachMessage → recruiterOutreachTemplate."""
    import sqlite3
    from src.schemas import Job

    job_id = database.add_job(
        {"title": "QA", "company": "Acme", "status": "sourced"},
        db_path=db,
    )
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE jobs SET outreachMessage = ?, recruiterOutreachTemplate = '' WHERE id = ?",
        ("Legacy note", job_id),
    )
    conn.commit()
    conn.close()

    job = database.get_job(job_id, db_path=db)
    assert isinstance(job, Job)
    assert job.recruiterOutreachTemplate == "Legacy note"
