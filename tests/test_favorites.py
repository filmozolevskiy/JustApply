"""Tests for Favorite Job — persist, toggle, activity log (issue #166)."""

from src.db import add_job, get_jobs, init_db, update_job_status
from src.db.jobs import archive_job, get_job, set_job_favorited


def _fresh_db(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    return db_str


# ---------------------------------------------------------------------------
# DB-layer: schema + defaults
# ---------------------------------------------------------------------------


def test_new_job_defaults_not_favorited(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme", "status": "scraped"}, db_str)
    job = get_job(job_id, db_str)
    assert job.favorited is False


def test_existing_seed_jobs_read_as_not_favorited(tmp_path):
    db_str = _fresh_db(tmp_path)
    jobs = get_jobs(db_str, archived_filter="all")
    assert jobs, "seed data should contain jobs"
    assert all(j.favorited is False for j in jobs)


# ---------------------------------------------------------------------------
# DB-layer: set_job_favorited
# ---------------------------------------------------------------------------


def test_set_job_favorited_marks_favorite(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme", "status": "matched"}, db_str)

    result = set_job_favorited(job_id, True, db_str)

    assert result is not None
    assert result.favorited is True
    assert result.status == "matched"


def test_set_job_favorited_logs_marked_favorite(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)

    set_job_favorited(job_id, True, db_str)
    job = get_job(job_id, db_str)

    messages = [e.message for e in job.activityLog]
    assert "Marked favorite" in messages


def test_set_job_favorited_unmarks_and_logs(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    set_job_favorited(job_id, True, db_str)

    result = set_job_favorited(job_id, False, db_str)

    assert result.favorited is False
    messages = [e.message for e in result.activityLog]
    assert "Unmarked favorite" in messages


def test_set_job_favorited_does_not_change_status_or_archive(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme", "status": "accepted"}, db_str)

    result = set_job_favorited(job_id, True, db_str)

    assert result.status == "accepted"
    assert result.archived is False


def test_set_job_favorited_missing_job_returns_none(tmp_path):
    db_str = _fresh_db(tmp_path)
    assert set_job_favorited(99999, True, db_str) is None


# ---------------------------------------------------------------------------
# Preserve favorited across lane move / archive
# ---------------------------------------------------------------------------


def test_lane_move_preserves_favorited(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme", "status": "matched"}, db_str)
    set_job_favorited(job_id, True, db_str)

    updated = update_job_status(job_id, "accepted", db_str)

    assert updated.favorited is True
    assert updated.status == "accepted"


def test_archive_unarchive_preserves_favorited(tmp_path):
    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    update_job_status(job_id, "rejected", db_str)
    set_job_favorited(job_id, True, db_str)

    archived = archive_job(job_id, db_str)
    assert archived.favorited is True
    assert archived.archived is True

    unarchived = archive_job(job_id, db_str)
    assert unarchived.favorited is True
    assert unarchived.archived is False


def test_auto_archive_preserves_favorited(tmp_path):
    import sqlite3

    from src.db import archive_stale_rejected_jobs

    db_str = _fresh_db(tmp_path)
    job_id = add_job({"title": "Old Reject", "company": "GoneCo"}, db_str)
    update_job_status(job_id, "rejected", db_str)
    set_job_favorited(job_id, True, db_str)
    conn = sqlite3.connect(db_str)
    conn.execute(
        "UPDATE jobs SET rejectedAt = datetime('now', '-20 days') WHERE id = ?",
        (job_id,),
    )
    conn.commit()
    conn.close()

    archive_stale_rejected_jobs(db_str)
    job = get_job(job_id, db_str)
    assert job.archived is True
    assert job.favorited is True


# ---------------------------------------------------------------------------
# API-layer: POST /api/jobs/{id}/favorite
# ---------------------------------------------------------------------------


def test_favorite_endpoint_marks_and_returns_job(tmp_path):
    import src.db.connection as _db_connection
    from fastapi.testclient import TestClient
    from src.db import init_db as _init_db

    _db_connection.DB_PATH = str(tmp_path / "test.db")
    _init_db(_db_connection.DB_PATH)

    from src.web.server import app

    client = TestClient(app)
    jobs = client.get("/api/jobs?archived=all").json()
    job_id = jobs[0]["id"]

    response = client.post(f"/api/jobs/{job_id}/favorite", json={"favorited": True})
    assert response.status_code == 200
    body = response.json()
    assert body["favorited"] is True
    messages = [e["message"] for e in body["activityLog"]]
    assert "Marked favorite" in messages


def test_favorite_endpoint_unmarks(tmp_path):
    import src.db.connection as _db_connection
    from fastapi.testclient import TestClient
    from src.db import init_db as _init_db

    _db_connection.DB_PATH = str(tmp_path / "test.db")
    _init_db(_db_connection.DB_PATH)

    from src.web.server import app

    client = TestClient(app)
    jobs = client.get("/api/jobs?archived=all").json()
    job_id = jobs[0]["id"]
    client.post(f"/api/jobs/{job_id}/favorite", json={"favorited": True})

    response = client.post(f"/api/jobs/{job_id}/favorite", json={"favorited": False})
    assert response.status_code == 200
    body = response.json()
    assert body["favorited"] is False
    messages = [e["message"] for e in body["activityLog"]]
    assert "Unmarked favorite" in messages


def test_favorite_endpoint_404_for_missing_job(tmp_path):
    import src.db.connection as _db_connection
    from fastapi.testclient import TestClient
    from src.db import init_db as _init_db

    _db_connection.DB_PATH = str(tmp_path / "test.db")
    _init_db(_db_connection.DB_PATH)

    from src.web.server import app

    client = TestClient(app)
    response = client.post("/api/jobs/99999/favorite", json={"favorited": True})
    assert response.status_code == 404


def test_get_jobs_exposes_favorited(tmp_path):
    import src.db.connection as _db_connection
    from fastapi.testclient import TestClient
    from src.db import init_db as _init_db

    _db_connection.DB_PATH = str(tmp_path / "test.db")
    _init_db(_db_connection.DB_PATH)

    from src.web.server import app

    client = TestClient(app)
    jobs = client.get("/api/jobs?archived=all").json()
    assert "favorited" in jobs[0]
    assert jobs[0]["favorited"] is False

    job_id = jobs[0]["id"]
    client.post(f"/api/jobs/{job_id}/favorite", json={"favorited": True})
    single = client.get(f"/api/jobs/{job_id}").json()
    assert single["favorited"] is True


# ---------------------------------------------------------------------------
# Dashboard static wiring smoke
# ---------------------------------------------------------------------------


def test_dashboard_wires_favorite_toggle_and_card_cue():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    drawer = (root / "src/web/static/js/drawerController.js").read_text()
    board = (root / "src/web/static/js/boardRenderer.js").read_text()
    css = (root / "src/web/static/css/dashboard.css").read_text()
    app_js = (root / "src/web/static/js/dashboardApp.js").read_text()

    assert "toggleJobFavorite" in drawer
    assert "/api/jobs/${jobId}/favorite" in drawer
    assert "drawer-favorite-btn" in drawer
    assert "kanban-card--favorited" in board
    assert "favorite-header-chip" in board
    assert "Favorite" in board
    assert ".kanban-card--favorited" in css
    assert "toggleJobFavorite: board.toggleJobFavorite" in app_js
