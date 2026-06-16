"""Tests for POST /api/jobs/{id}/reclassify — re-classify from cached Contact Sample."""
import os
import sys
import pytest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import db as database
import src.db.connection as _db_connection
from src.web.server import app
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.fixture
def db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test.db")
    monkeypatch.setattr(_db_connection, "DB_PATH", test_db)
    database.init_db(test_db)
    return test_db


def _make_accepted_job_with_contacts(db):
    """Insert an accepted job with contacts and return its id."""
    from src.db.jobs import add_job, enrich_job
    from src.core.enrichment.coordinator import begin_enrichment
    job_id = add_job({
        "title": "QA Engineer",
        "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "status": "found",
    }, db_path=db)
    begin_enrichment(job_id, db)
    enrich_job(
        job_id,
        contacts=[{"name": "Alice", "title": "Recruiter", "url": "", "contacted": False,
                   "russian_speaker": False, "is_recruiter": True}],
        outreach_message="Hello",
        db_path=db,
    )
    return job_id


# --- 404 when job does not exist ---

def test_reclassify_returns_404_for_unknown_job(db):
    resp = client.post("/api/jobs/9999/reclassify")
    assert resp.status_code == 404


# --- 422 when no cached sample exists for the company ---

def test_reclassify_returns_422_when_no_cache(db):
    job_id = _make_accepted_job_with_contacts(db)
    with patch("src.db.cache.get_contact_sample", return_value=None):
        resp = client.post(f"/api/jobs/{job_id}/reclassify")
    assert resp.status_code == 422
    assert "cache" in resp.json()["message"].lower()


# --- 200 on success: re-classifies from cache, no Apify call ---

@pytest.mark.asyncio
async def test_reclassify_uses_cache_not_apify(db):
    job_id = _make_accepted_job_with_contacts(db)

    fake_cache = {
        "profiles": [{"firstName": "Bob", "lastName": "Smith", "headline": "Recruiter",
                      "linkedinUrl": "https://linkedin.com/in/bob"}],
        "fetched_at": "2026-01-01T00:00:00+00:00",
        "display_name": "Acme",
    }
    new_contacts = [{"name": "Bob Smith", "title": "Recruiter", "url": "https://linkedin.com/in/bob",
                     "contacted": False, "russian_speaker": False, "is_recruiter": True}]
    new_templates = {"recruiter": "Hello ______,\n\nAcme.", "russian_speaker": ""}

    with patch("src.db.cache.get_contact_sample", return_value=fake_cache), \
         patch("src.pipelines.classify_contacts", new=AsyncMock(return_value=new_contacts)), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=new_templates)), \
         patch("src.core.enrichment.contact_sample._run_apify_actor") as mock_apify:
        resp = client.post(f"/api/jobs/{job_id}/reclassify")

    assert resp.status_code == 200
    mock_apify.assert_not_called()
    data = resp.json()
    assert data["id"] == job_id
    assert len(data["contacts"]) == 1
    assert data["contacts"][0]["name"] == "Bob Smith"


# --- 422 when job is not in Accepted lane ---

def test_reclassify_returns_422_for_non_accepted_job(db):
    from src.db.jobs import add_job
    job_id = add_job({
        "title": "Dev",
        "company": "TechCo",
        "status": "found",
    }, db_path=db)
    resp = client.post(f"/api/jobs/{job_id}/reclassify")
    assert resp.status_code == 422
    assert "accepted" in resp.json()["message"].lower()


# --- Drawer: Re-classify button shown on Accepted jobs with contacts ---

def test_drawer_shows_reclassify_button_for_accepted_jobs_with_contacts():
    from kanban_js import read_drawer_controller
    content = read_drawer_controller()
    assert "Re-classify" in content, \
        "drawerController.js must contain 'Re-classify' button text"
    assert "reclassifyJob" in content, \
        "drawerController.js must call reclassifyJob()"


def test_drawer_reclassify_button_only_on_accepted_not_found():
    from kanban_js import read_drawer_controller
    content = read_drawer_controller()
    reclassify_idx = content.find("Re-classify")
    assert reclassify_idx != -1
    # The 'accepted' status check must appear within 600 chars before the Re-classify button
    nearby = content[max(0, reclassify_idx - 600):reclassify_idx + 50]
    assert "accepted" in nearby, \
        "Re-classify button must only appear for accepted jobs"


# --- Dashboard: reclassifyJob is exported to window ---

def test_dashboard_exports_reclassify_job():
    from kanban_js import read_dashboard_html, get_script_section
    script = get_script_section(read_dashboard_html())
    assert "reclassifyJob" in script, \
        "dashboard.html must define and export reclassifyJob"
