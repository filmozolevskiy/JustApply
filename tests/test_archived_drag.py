"""Tests for archived card drag rules — issue #55."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db import init_db, get_jobs, update_job_status, add_job
from src.db.jobs import archive_job, get_job

HTML_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")


def _read_html():
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Dashboard HTML: archived → Enriching is a no-op
# ---------------------------------------------------------------------------

def test_archived_enriching_drop_guard_present():
    content = _read_html()
    assert "job.archived && lane === 'enriching'" in content, (
        "Drop handler must guard against archived card being dropped on Enriching lane"
    )


def test_archived_enriching_drop_guard_is_noop():
    """The guard must return early — no moveJobStage, no enrich trigger."""
    content = _read_html()
    # The guard pattern: if (job.archived && lane === 'enriching') return;
    assert "job.archived && lane === 'enriching') return" in content, (
        "Guard must be a silent early return (no-op) for archived card dropped on Enriching"
    )


def test_nonarchived_drop_unaffected():
    """Non-archived cards retain existing behaviour: moveJobStage is still called."""
    content = _read_html()
    assert "moveJobStage(jobId, lane)" in content, (
        "Non-archived cards must still call moveJobStage on drop"
    )


# ---------------------------------------------------------------------------
# DB layer: status update on archived job preserves archived flag
# ---------------------------------------------------------------------------

def test_archived_job_status_update_preserves_archived(tmp_path):
    """Drag to non-Enriching lane → status changes, archived stays True."""
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = add_job({"title": "Dev", "company": "Acme", "status": "rejected"}, db_str)
    # Archive the job first
    update_job_status(job_id, "rejected", db_str)
    archive_job(job_id, db_str)
    job = get_job(job_id, db_str)
    assert job.archived is True

    # Simulate drag to sourced (what the dashboard does via PUT /api/jobs/{id}/status)
    updated = update_job_status(job_id, "sourced", db_str)
    assert updated.status == "sourced"
    assert updated.archived is True, "archived flag must survive a status update"


def test_archived_job_can_move_to_contacted(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = add_job({"title": "Dev", "company": "Acme", "status": "rejected"}, db_str)
    update_job_status(job_id, "rejected", db_str)
    archive_job(job_id, db_str)

    updated = update_job_status(job_id, "contacted", db_str)
    assert updated.status == "contacted"
    assert updated.archived is True


def test_archived_moved_job_absent_from_active_board(tmp_path):
    """After drag to sourced, archived card still hidden in active view."""
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = add_job({"title": "Dev", "company": "Acme", "status": "rejected"}, db_str)
    update_job_status(job_id, "rejected", db_str)
    archive_job(job_id, db_str)

    update_job_status(job_id, "sourced", db_str)
    active_jobs = get_jobs(db_str, archived_filter="active")
    ids = [j.id for j in active_jobs]
    assert job_id not in ids, "archived job must remain hidden in active board after status move"


def test_archived_moved_job_visible_in_archived_view(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = add_job({"title": "Dev", "company": "Acme", "status": "rejected"}, db_str)
    update_job_status(job_id, "rejected", db_str)
    archive_job(job_id, db_str)

    update_job_status(job_id, "sourced", db_str)
    archived_jobs = get_jobs(db_str, archived_filter="archived")
    ids = [j.id for j in archived_jobs]
    assert job_id in ids, "archived job must appear in archived view after status move"


# ---------------------------------------------------------------------------
# API layer: PUT /api/jobs/{id}/status preserves archived flag
# ---------------------------------------------------------------------------

def test_api_status_update_archived_job_preserves_archived(tmp_path):
    """End-to-end API call: archived job status update keeps archived=True."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from fastapi.testclient import TestClient
    from src.web.server import app
    import src.db.connection as conn_mod

    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = add_job({"title": "Dev", "company": "Acme", "status": "rejected"}, db_str)
    update_job_status(job_id, "rejected", db_str)
    archive_job(job_id, db_str)

    original_path = conn_mod.DB_PATH
    conn_mod.DB_PATH = db_str
    try:
        client = TestClient(app)
        resp = client.put(f"/api/jobs/{job_id}/status", json={"status": "sourced"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "sourced"
        assert data["archived"] is True
    finally:
        conn_mod.DB_PATH = original_path
