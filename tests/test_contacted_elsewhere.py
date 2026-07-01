"""Tests for Contacted Elsewhere cross-job outreach warnings."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from src.db import add_job, get_job, get_jobs, init_db, update_contact_status
from src.db import connection as _db_connection
from src.db.contacted_elsewhere import (
    build_contacted_index,
    contacted_elsewhere_for_contact,
    contacted_timestamp,
    enrich_jobs_with_contacted_elsewhere,
)
from src.web.server import app

SHARED_URL = "https://linkedin.com/in/jane-doe"


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "contacted_elsewhere.db")
    init_db(db_path)
    return db_path


def _add_job_with_contact(db_path, *, title, company, contacted=False, contacted_at="", archived=False):
    job_id = add_job(
        {
            "title": title,
            "company": company,
            "status": "accepted",
            "contacts": [
                {
                    "name": "Jane Doe",
                    "title": "Recruiter",
                    "url": SHARED_URL,
                    "contacted": contacted,
                    **({"contacted_at": contacted_at} if contacted_at else {}),
                }
            ],
        },
        db_path=db_path,
    )
    if archived:
        from src.db.connection import get_db_connection

        conn = get_db_connection(db_path)
        conn.execute("UPDATE jobs SET archived = 1 WHERE id = ?", (job_id,))
        conn.commit()
        conn.close()
    return job_id


def test_contacted_timestamp_prefers_contacted_at(db):
    ts = contacted_timestamp(
        {"name": "Jane Doe", "contacted_at": "2026-01-02T10:00:00+00:00"},
        [],
    )
    assert ts == "2026-01-02T10:00:00+00:00"


def test_contacted_timestamp_falls_back_to_activity_log(db):
    ts = contacted_timestamp(
        {"name": "Jane Doe"},
        [{"ts": "2026-01-01T08:00:00+00:00", "message": "Marked Jane Doe contacted"}],
    )
    assert ts == "2026-01-01T08:00:00+00:00"


def test_build_contacted_index_includes_archived_jobs(db):
    active_id = _add_job_with_contact(
        db,
        title="Role A",
        company="Acme",
        contacted=True,
        contacted_at="2026-01-01T08:00:00+00:00",
    )
    archived_id = _add_job_with_contact(
        db,
        title="Role B",
        company="Beta",
        contacted=True,
        contacted_at="2026-02-01T08:00:00+00:00",
        archived=True,
    )
    jobs = get_jobs(db_path=db, archived_filter="all")
    index = build_contacted_index(jobs)
    slug = "/in/jane-doe"
    assert len(index[slug]) == 2
    job_ids = {entry["jobId"] for entry in index[slug]}
    assert job_ids == {active_id, archived_id}


def test_contacted_elsewhere_picks_most_recent_other_job(db):
    older_id = _add_job_with_contact(
        db,
        title="Older Role",
        company="OldCo",
        contacted=True,
        contacted_at="2026-01-01T08:00:00+00:00",
    )
    newer_id = _add_job_with_contact(
        db,
        title="Newer Role",
        company="NewCo",
        contacted=True,
        contacted_at="2026-02-01T08:00:00+00:00",
    )
    current_id = _add_job_with_contact(db, title="Current Role", company="NowCo")
    jobs = get_jobs(db_path=db, archived_filter="all")
    index = build_contacted_index(jobs)
    current_job = next(j for j in jobs if j.id == current_id)
    contact = current_job.contacts[0]
    elsewhere = contacted_elsewhere_for_contact(current_id, contact, index)
    assert elsewhere == {"jobId": newer_id, "company": "NewCo", "title": "Newer Role"}
    assert elsewhere["jobId"] != older_id


def test_contacted_elsewhere_hidden_when_current_contact_is_contacted(db):
    job_id = _add_job_with_contact(
        db,
        title="Current Role",
        company="NowCo",
        contacted=True,
        contacted_at="2026-03-01T08:00:00+00:00",
    )
    _add_job_with_contact(
        db,
        title="Other Role",
        company="OtherCo",
        contacted=True,
        contacted_at="2026-02-01T08:00:00+00:00",
    )
    job = get_job(job_id, db_path=db)
    assert job.contacts[0].contacted is True
    assert not hasattr(job.contacts[0], "contactedElsewhere") or job.contacts[0].model_dump().get("contactedElsewhere") is None


def test_update_contact_status_sets_contacted_at(db):
    job_id = _add_job_with_contact(db, title="Role", company="Acme")
    updated = update_contact_status(job_id, 0, True, db_path=db)
    assert updated.contacts[0].contacted is True
    raw = updated.contacts[0].model_dump()
    assert raw.get("contacted_at")


def test_get_jobs_enriches_contacted_elsewhere(db):
    source_id = _add_job_with_contact(
        db,
        title="Source Role",
        company="SourceCo",
        contacted=True,
        contacted_at="2026-02-01T08:00:00+00:00",
    )
    target_id = _add_job_with_contact(db, title="Target Role", company="TargetCo")
    jobs = get_jobs(db_path=db)
    target = next(j for j in jobs if j.id == target_id)
    payload = target.contacts[0].model_dump()
    assert payload["contactedElsewhere"] == {
        "jobId": source_id,
        "company": "SourceCo",
        "title": "Source Role",
    }


def test_api_get_job_returns_contacted_elsewhere(db, monkeypatch):
    monkeypatch.setattr(_db_connection, "DB_PATH", db)
    client = TestClient(app)
    source_id = _add_job_with_contact(
        db,
        title="Source Role",
        company="SourceCo",
        contacted=True,
        contacted_at="2026-02-01T08:00:00+00:00",
    )
    target_id = _add_job_with_contact(db, title="Target Role", company="TargetCo")
    resp = client.get(f"/api/jobs/{target_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["contacts"][0]["contactedElsewhere"]["jobId"] == source_id


def test_api_contact_toggle_clears_elsewhere_on_same_job(db, monkeypatch):
    monkeypatch.setattr(_db_connection, "DB_PATH", db)
    client = TestClient(app)
    source_id = _add_job_with_contact(
        db,
        title="Source Role",
        company="SourceCo",
        contacted=True,
        contacted_at="2026-02-01T08:00:00+00:00",
    )
    target_id = _add_job_with_contact(db, title="Target Role", company="TargetCo")
    before = client.get(f"/api/jobs/{target_id}").json()
    assert before["contacts"][0]["contactedElsewhere"]["jobId"] == source_id

    resp = client.put(f"/api/jobs/{target_id}/contacts/0", json={"contacted": True})
    assert resp.status_code == 200
    after = resp.json()
    assert after["contacts"][0]["contacted"] is True
    assert "contactedElsewhere" not in after["contacts"][0]


def test_enrich_jobs_with_contacted_elsewhere_is_noop_for_empty_list(db):
    assert enrich_jobs_with_contacted_elsewhere([], db_path=db) == []


def test_enrich_job_returns_contacted_elsewhere(db):
    from src.db.jobs import enrich_job

    source_id = _add_job_with_contact(
        db,
        title="Source Role",
        company="SourceCo",
        contacted=True,
        contacted_at="2026-02-01T08:00:00+00:00",
    )
    target_id = _add_job_with_contact(db, title="Target Role", company="TargetCo")
    updated = enrich_job(
        target_id,
        [
            {
                "name": "Jane Doe",
                "title": "Recruiter",
                "url": SHARED_URL,
                "contacted": False,
            }
        ],
        "Hello",
        db_path=db,
    )
    payload = updated.contacts[0].model_dump()
    assert payload["contactedElsewhere"] == {
        "jobId": source_id,
        "company": "SourceCo",
        "title": "Source Role",
    }


def test_update_job_status_returns_contacted_elsewhere(db, monkeypatch):
    monkeypatch.setattr(_db_connection, "DB_PATH", db)
    client = TestClient(app)
    source_id = _add_job_with_contact(
        db,
        title="Source Role",
        company="SourceCo",
        contacted=True,
        contacted_at="2026-02-01T08:00:00+00:00",
    )
    target_id = _add_job_with_contact(
        db,
        title="Target Role",
        company="TargetCo",
        contacted=False,
    )
    resp = client.put(f"/api/jobs/{target_id}/status", json={"status": "accepted"})
    assert resp.status_code == 200
    assert resp.json()["contacts"][0]["contactedElsewhere"]["jobId"] == source_id
