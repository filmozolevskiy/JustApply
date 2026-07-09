"""Tracer-bullet: Job is the canonical type returned from DB reads."""

import pytest
from src import db as database
from src.db.job_model import _parse_activity_log, activity_log_as_dicts


@pytest.fixture()
def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    database.init_db(db_path)
    return db_path

def test_parse_activity_log_empty():
    assert _parse_activity_log(None) == []
    assert _parse_activity_log("") == []

def test_parse_activity_log_invalid_json():
    assert _parse_activity_log("not json") == []
    assert _parse_activity_log("{broken") == []

def test_parse_activity_log_valid_entries():
    raw = '[{"ts": "2026-01-01T00:00:00+00:00", "message": "Found"}]'
    entries = _parse_activity_log(raw)
    assert len(entries) == 1
    assert entries[0].ts == "2026-01-01T00:00:00+00:00"
    assert entries[0].message == "Found"

def test_activity_log_as_dicts_round_trip():
    raw = '[{"ts": "2026-01-01", "message": "Moved Scraped → Applied"}]'
    assert activity_log_as_dicts(raw) == [
        {"ts": "2026-01-01", "message": "Moved Scraped → Applied"},
    ]

def test_legacy_activity_log_row_deserializes_via_get_job(db):
    """Legacy persisted JSON rows still deserialize through the shared parser."""
    import sqlite3

    job_id = database.add_job({"title": "QA", "company": "Acme"}, db_path=db)
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE jobs SET activityLog = ? WHERE id = ?",
        ('[{"ts":"2020-01-01","message":"Legacy entry"}]', job_id),
    )
    conn.commit()
    conn.close()

    job = database.get_job(job_id, db_path=db)
    assert len(job.activityLog) == 1
    assert job.activityLog[0].message == "Legacy entry"

def test_corrupt_activity_log_row_returns_empty_list(db):
    import sqlite3

    job_id = database.add_job({"title": "QA", "company": "Acme"}, db_path=db)
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE jobs SET activityLog = ? WHERE id = ?",
        ("{not valid json", job_id),
    )
    conn.commit()
    conn.close()

    job = database.get_job(job_id, db_path=db)
    assert job.activityLog == []

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
