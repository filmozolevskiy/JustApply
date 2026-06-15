"""Tests for archived visibility filter and un-archive — issue #54."""
import os
import sys
import sqlite3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db import init_db, get_jobs, update_job_status, add_job
from src.db.jobs import get_job, archive_job


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _add_and_archive_job(db_str) -> int:
    """Add a rejected job and archive it; return its id."""
    job_id = add_job({"title": "Archived Dev", "company": "ArchiveCo"}, db_str)
    update_job_status(job_id, "rejected", db_str)
    archive_job(job_id, db_str)
    return job_id


def _add_rejected_job_with_old_timestamp(db_str, days: int) -> int:
    """Add a rejected job with rejectedAt backdated by `days` and archive it."""
    job_id = add_job({"title": f"Old Job {days}", "company": f"OldCo-{days}"}, db_str)
    update_job_status(job_id, "rejected", db_str)
    archive_job(job_id, db_str)
    conn = sqlite3.connect(db_str)
    conn.execute(
        "UPDATE jobs SET rejectedAt = datetime('now', ?) WHERE id = ?",
        (f"-{days} days", job_id),
    )
    conn.commit()
    conn.close()
    return job_id


# ---------------------------------------------------------------------------
# DB-layer: get_jobs with archived_filter
# ---------------------------------------------------------------------------

def test_get_jobs_active_excludes_archived(tmp_path):
    """Tracer bullet: default 'active' filter hides archived jobs."""
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    archived_id = _add_and_archive_job(db_str)

    jobs = get_jobs(db_str)  # default archived_filter="active"
    assert not any(j["id"] == archived_id for j in jobs)


def test_get_jobs_archived_returns_only_archived(tmp_path):
    """get_jobs with archived_filter='archived' returns only archived jobs."""
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    archived_id = _add_and_archive_job(db_str)
    active_id = add_job({"title": "Active Job", "company": "ActiveCo"}, db_str)

    jobs = get_jobs(db_str, archived_filter="archived")
    ids = [j["id"] for j in jobs]
    assert archived_id in ids
    assert active_id not in ids


def test_get_jobs_all_returns_both(tmp_path):
    """get_jobs with archived_filter='all' returns both archived and active jobs."""
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    archived_id = _add_and_archive_job(db_str)
    active_id = add_job({"title": "Active Job", "company": "ActiveCo"}, db_str)

    jobs = get_jobs(db_str, archived_filter="all")
    ids = [j["id"] for j in jobs]
    assert archived_id in ids
    assert active_id in ids


# ---------------------------------------------------------------------------
# DB-layer: archive_job toggle — un-archive
# ---------------------------------------------------------------------------

def test_archive_job_on_archived_job_unarchives_it(tmp_path):
    """Tracer bullet: archive_job on an archived job sets archived=False."""
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    archived_id = _add_and_archive_job(db_str)

    result = archive_job(archived_id, db_str)

    assert result is not None
    assert result["archived"] is False


def test_unarchive_sets_auto_archive_exemption(tmp_path):
    """Un-archiving sets autoArchiveExempt=True."""
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    archived_id = _add_and_archive_job(db_str)

    archive_job(archived_id, db_str)

    job = get_job(archived_id, db_str)
    assert job["autoArchiveExempt"] is True


def test_unarchive_logs_correct_message(tmp_path):
    """Un-archiving appends 'Un-archived (auto-archive exempted)' to activity log."""
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    archived_id = _add_and_archive_job(db_str)

    archive_job(archived_id, db_str)

    job = get_job(archived_id, db_str)
    messages = [e["message"] for e in job["activityLog"]]
    assert "Un-archived (auto-archive exempted)" in messages


def test_unarchived_job_visible_in_active_board(tmp_path):
    """Un-archived job appears in active get_jobs after un-archive."""
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    archived_id = _add_and_archive_job(db_str)

    # Confirm it's hidden
    assert not any(j["id"] == archived_id for j in get_jobs(db_str))

    # Un-archive
    archive_job(archived_id, db_str)

    # Now visible
    assert any(j["id"] == archived_id for j in get_jobs(db_str))


def test_unarchived_job_absent_from_archived_filter(tmp_path):
    """Un-archived job no longer appears in archived filter."""
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    archived_id = _add_and_archive_job(db_str)

    archive_job(archived_id, db_str)  # un-archive

    jobs = get_jobs(db_str, archived_filter="archived")
    assert not any(j["id"] == archived_id for j in jobs)


def test_exemption_survives_auto_archive_sweep(tmp_path):
    """Un-archived job with old rejectedAt stays on active board (exemption blocks re-archive)."""
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = add_job({"title": "Old Rejected", "company": "OldCo"}, db_str)
    update_job_status(job_id, "rejected", db_str)

    # Backdate rejectedAt to 20 days ago
    conn = sqlite3.connect(db_str)
    conn.execute(
        "UPDATE jobs SET rejectedAt = datetime('now', '-20 days') WHERE id = ?",
        (job_id,),
    )
    conn.commit()
    conn.close()

    # Archive it, then un-archive (sets autoArchiveExempt)
    archive_job(job_id, db_str)
    archive_job(job_id, db_str)  # un-archive

    # get_jobs sweep runs — exemption should block re-archive
    jobs = get_jobs(db_str)
    assert any(j["id"] == job_id for j in jobs), "exempted job must stay on active board after sweep"


# ---------------------------------------------------------------------------
# API-layer: GET /api/jobs?archived=...
# ---------------------------------------------------------------------------

def _setup_client(tmp_path, suffix="test.db"):
    import src.db.connection as _db_connection
    from src.db import init_db as _init_db
    _db_connection.DB_PATH = str(tmp_path / suffix)
    _init_db(_db_connection.DB_PATH)
    from src.web.server import app
    from fastapi.testclient import TestClient
    return TestClient(app), _db_connection.DB_PATH


def test_api_get_jobs_default_excludes_archived(tmp_path):
    """GET /api/jobs (no param) returns only active jobs."""
    client, db_str = _setup_client(tmp_path, "api1.db")
    archived_id = _add_and_archive_job(db_str)

    response = client.get("/api/jobs")
    assert response.status_code == 200
    ids = [j["id"] for j in response.json()]
    assert archived_id not in ids


def test_api_get_jobs_archived_filter(tmp_path):
    """GET /api/jobs?archived=archived returns only archived jobs."""
    client, db_str = _setup_client(tmp_path, "api2.db")
    archived_id = _add_and_archive_job(db_str)
    active_id = add_job({"title": "Active", "company": "Co"}, db_str)

    response = client.get("/api/jobs?archived=archived")
    assert response.status_code == 200
    ids = [j["id"] for j in response.json()]
    assert archived_id in ids
    assert active_id not in ids


def test_api_get_jobs_all_filter(tmp_path):
    """GET /api/jobs?archived=all returns both archived and active jobs."""
    client, db_str = _setup_client(tmp_path, "api3.db")
    archived_id = _add_and_archive_job(db_str)
    active_id = add_job({"title": "Active", "company": "Co"}, db_str)

    response = client.get("/api/jobs?archived=all")
    assert response.status_code == 200
    ids = [j["id"] for j in response.json()]
    assert archived_id in ids
    assert active_id in ids


# ---------------------------------------------------------------------------
# API-layer: POST /api/jobs/{id}/archive — toggle un-archive
# ---------------------------------------------------------------------------

def test_api_archive_endpoint_unarchives_archived_job(tmp_path):
    """POST /api/jobs/{id}/archive on an already-archived job un-archives it."""
    client, db_str = _setup_client(tmp_path, "api4.db")
    archived_id = _add_and_archive_job(db_str)

    response = client.post(f"/api/jobs/{archived_id}/archive")
    assert response.status_code == 200
    body = response.json()
    assert body["archived"] is False
    assert body["autoArchiveExempt"] is True


def test_api_archive_endpoint_unarchived_job_appears_in_active(tmp_path):
    """After un-archive via API, job appears in active board."""
    client, db_str = _setup_client(tmp_path, "api5.db")
    archived_id = _add_and_archive_job(db_str)

    client.post(f"/api/jobs/{archived_id}/archive")

    response = client.get("/api/jobs")
    ids = [j["id"] for j in response.json()]
    assert archived_id in ids
