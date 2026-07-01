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


def _job_after_reclassify_post(job_id, db):
    """POST reclassify starts a background task; TestClient runs it before returning."""
    from src.db.jobs import get_job
    resp = client.post(f"/api/jobs/{job_id}/reclassify")
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert data["job_id"] == job_id
    return get_job(job_id, db_path=db)


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
        "status": "scraped",
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


# --- 200 template-only path when no cached sample exists ---

def test_reclassify_no_cache_returns_200(db):
    job_id = _make_accepted_job_with_contacts(db)
    templates = {"recruiter": "Hello ______,\n\nAcme.", "russian_speaker": ""}
    with patch("src.db.cache.get_contact_sample", return_value=None), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=templates)):
        job = _job_after_reclassify_post(job_id, db)
    assert job is not None


def test_reclassify_no_cache_enrichment_note_kind_is_info(db):
    job_id = _make_accepted_job_with_contacts(db)
    templates = {"recruiter": "Hello ______,\n\nAcme.", "russian_speaker": ""}
    with patch("src.db.cache.get_contact_sample", return_value=None), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=templates)):
        job = _job_after_reclassify_post(job_id, db)
    assert job.enrichmentNoteKind == "info"
    assert "templates refreshed" in job.enrichmentNote


def test_reclassify_no_cache_preserves_existing_contacts(db):
    job_id = _make_accepted_job_with_contacts(db)
    templates = {"recruiter": "Hello ______,\n\nAcme.", "russian_speaker": ""}
    with patch("src.db.cache.get_contact_sample", return_value=None), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=templates)):
        job = _job_after_reclassify_post(job_id, db)
    assert len(job.contacts) == 1
    assert job.contacts[0].name == "Alice"


def test_reclassify_no_cache_activity_log_templates_refreshed(db):
    job_id = _make_accepted_job_with_contacts(db)
    templates = {"recruiter": "Hello ______,\n\nAcme.", "russian_speaker": ""}
    with patch("src.db.cache.get_contact_sample", return_value=None), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=templates)):
        job = _job_after_reclassify_post(job_id, db)
    messages = [e.message for e in job.activityLog]
    assert any("Re-classified · Outreach templates refreshed" in m for m in messages)
    assert not any("Enrichment failed" in m for m in messages)


@pytest.mark.asyncio
async def test_reclassify_no_cache_does_not_call_source_contacts(db):
    from src.pipelines import run_reclassify_pipeline
    job_id = _make_accepted_job_with_contacts(db)
    templates = {"recruiter": "Hello ______,\n\nAcme.", "russian_speaker": ""}
    with patch("src.db.cache.get_contact_sample", return_value=None), \
         patch("src.pipelines.source_contacts", new=AsyncMock()) as mock_source, \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=templates)):
        await run_reclassify_pipeline(job_id)
    mock_source.assert_not_called()


def test_enrich_job_failure_sets_warning_note_kind(db):
    from src.db.jobs import add_job, enrich_job
    from src.core.enrichment.coordinator import begin_enrichment
    job_id = add_job({"title": "Dev", "company": "Co", "status": "found"}, db_path=db)
    begin_enrichment(job_id, db)
    result = enrich_job(
        job_id,
        contacts=[],
        outreach_message="",
        enrichment_note="No contacts matched active Outreach Settings.",
        db_path=db,
    )
    assert result.enrichmentNoteKind == "warning"


def test_job_schema_has_enrichment_note_kind():
    from src.schemas import Job
    job = Job(title="Test", company="Co")
    assert hasattr(job, "enrichmentNoteKind")
    assert job.enrichmentNoteKind == ""


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
         patch("src.pipelines.source_contacts", new=AsyncMock(return_value=new_contacts)), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=new_templates)), \
         patch("src.core.enrichment.contact_sample._run_apify_actor") as mock_apify:
        job = _job_after_reclassify_post(job_id, db)

    mock_apify.assert_not_called()
    assert job.id == job_id
    assert len(job.contacts) == 1
    assert job.contacts[0].name == "Bob Smith"
    assert any("Re-classified" in e.message for e in job.activityLog)


@pytest.mark.asyncio
async def test_reclassify_uses_source_contacts_and_preserves_contacted(db):
    """Re-classify runs source_contacts (poster merge, contacted flags) — no Apify."""
    from src.pipelines import run_reclassify_pipeline
    from src.db.jobs import add_job, enrich_job
    from src.core.enrichment.coordinator import begin_enrichment
    from src.db.cache import set_contact_sample
    from src.core.enrichment.contact_sample import company_cache_slug

    job_id = add_job({
        "title": "QA Engineer",
        "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "status": "scraped",
    }, db_path=db)
    begin_enrichment(job_id, db)
    enrich_job(
        job_id,
        contacts=[{
            "name": "Alice", "title": "Recruiter",
            "url": "https://linkedin.com/in/alice", "contacted": True,
            "russian_speaker": False, "is_recruiter": True,
        }],
        outreach_message="Hello",
        db_path=db,
    )
    slug = company_cache_slug("Acme", "https://www.linkedin.com/company/acme/")
    set_contact_sample(
        slug,
        [{"firstName": "Alice", "linkedinUrl": "https://linkedin.com/in/alice", "headline": "Recruiter"}],
        db_path=db,
    )

    classified = [{
        "name": "Alice", "title": "Recruiter", "url": "https://linkedin.com/in/alice",
        "contacted": False, "russian_speaker": False, "is_recruiter": True,
    }]
    templates = {"recruiter": "Hello ______,\n\nAcme.", "russian_speaker": ""}

    with patch("src.core.enrichment.source.classify_contacts", new=AsyncMock(return_value=classified)), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=templates)), \
         patch("src.core.enrichment.contact_sample._run_apify_actor") as mock_apify:
        updated = await run_reclassify_pipeline(job_id)

    mock_apify.assert_not_called()
    assert updated.contacts[0].contacted is True


@pytest.mark.asyncio
async def test_reclassify_uses_complete_message_format_when_setting_disabled(db):
    from src.pipelines import run_reclassify_pipeline
    from src.db.cache import set_contact_sample
    from src.core.enrichment.contact_sample import company_cache_slug

    job_id = _make_accepted_job_with_contacts(db)
    slug = company_cache_slug("Acme", "https://www.linkedin.com/company/acme/")
    set_contact_sample(
        slug,
        [{"firstName": "Alice", "linkedinUrl": "https://linkedin.com/in/alice", "headline": "Recruiter"}],
        db_path=db,
    )

    database.save_outreach_settings(True, True, short_connection_note=False, db_path=db)

    classified = [{
        "name": "Alice", "title": "Recruiter", "url": "https://linkedin.com/in/alice",
        "contacted": False, "russian_speaker": False, "is_recruiter": True,
    }]
    complete_template = "Hello ______,\n\nComplete outreach draft."

    with patch("src.core.enrichment.source.classify_contacts", new=AsyncMock(return_value=classified)), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value={"recruiter": complete_template, "russian_speaker": ""})) as mock_gen:
        updated = await run_reclassify_pipeline(job_id)

    mock_gen.assert_awaited_once()
    assert mock_gen.await_args.kwargs["short_connection_note"] is False
    assert updated.recruiterOutreachTemplate == complete_template


def test_reclassify_post_returns_task_id(db):
    job_id = _make_accepted_job_with_contacts(db)
    templates = {"recruiter": "Hello ______,\n\nAcme.", "russian_speaker": ""}
    with patch("src.db.cache.get_contact_sample", return_value=None), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=templates)):
        resp = client.post(f"/api/jobs/{job_id}/reclassify")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == job_id
    assert isinstance(data["task_id"], str)
    assert data["task_id"]


@pytest.mark.asyncio
async def test_run_reclassify_task_with_logs_writes_results(db):
    from src.web.server import run_reclassify_task_with_logs, TaskState, active_tasks
    import uuid

    job_id = _make_accepted_job_with_contacts(db)
    templates = {"recruiter": "Hello ______,\n\nAcme.", "russian_speaker": ""}
    task_id = str(uuid.uuid4())
    state = TaskState({"job_id": job_id})
    active_tasks[task_id] = state

    with patch("src.db.cache.get_contact_sample", return_value=None), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=templates)):
        await run_reclassify_task_with_logs(task_id, job_id)

    from src.db.jobs import get_job
    job = get_job(job_id, db_path=db)
    assert job.enrichmentNoteKind == "info"
    assert state.status == "completed"
    assert state.result["job"]["id"] == job_id


# --- 422 when job is not in Accepted lane ---

def test_reclassify_returns_422_for_non_accepted_job(db):
    from src.db.jobs import add_job
    job_id = add_job({
        "title": "Dev",
        "company": "TechCo",
        "status": "scraped",
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


def test_drawer_reclassify_button_gated_on_accepted_status():
    """Re-classify is gated on status === 'accepted', not hasContactSampleActions."""
    from kanban_js import read_drawer_controller
    content = read_drawer_controller()
    idx = content.find("reclassifyJob(")
    assert idx != -1
    nearby = content[max(0, idx - 400):idx + 50]
    assert "status === 'accepted'" in nearby, \
        "Re-classify button must be gated on job.status === 'accepted'"
    assert "hasContactSampleActions" not in nearby, \
        "Re-classify must not be gated on hasContactSampleActions — show for all Accepted jobs"


def test_load_more_contacts_gated_on_company_url():
    """Load More Contacts requires Accepted status and companyUrl."""
    from kanban_js import read_drawer_controller
    content = read_drawer_controller()
    idx = content.find("loadMoreContacts(")
    assert idx != -1
    nearby = content[max(0, idx - 400):idx + 50]
    assert "companyUrl" in nearby, \
        "Load More Contacts must be gated on job.companyUrl"
    assert "status === 'accepted'" in nearby, \
        "Load More Contacts must be gated on job.status === 'accepted'"


# --- Dashboard: reclassifyJob is exported to window ---

def test_dashboard_exports_reclassify_job():
    from kanban_js import read_dashboard_html, get_script_section
    script = get_script_section(read_dashboard_html())
    assert "reclassifyJob" in script, \
        "dashboard.html must define and export reclassifyJob"


# --- Hardening: infrastructure failures (issue #118) ---

_EMPTY_TEMPLATES = {"recruiter": "", "russian_speaker": ""}
_BOTH_TEMPLATES = {
    "recruiter": "Hello ______,\n\nAcme is looking for a QA.",
    "russian_speaker": "Hello ______,\n\nAcme is looking for a QA.",
}


@pytest.mark.asyncio
async def test_reclassify_settings_read_failure_no_cache_completes_with_note(db):
    """Settings read failure on no-cache path completes without crash."""
    log_records = []

    async def capture_log(msg, level="info"):
        log_records.append((msg, level))

    job_id = _make_accepted_job_with_contacts(db)

    with patch("src.pipelines.database.get_outreach_settings", side_effect=Exception("DB locked")), \
         patch("src.db.cache.get_contact_sample", return_value=None), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=_BOTH_TEMPLATES)):
        from src.pipelines import run_reclassify_pipeline
        result = await run_reclassify_pipeline(job_id, log_func=capture_log)

    assert result is not None
    assert result.status == "accepted"
    assert result.enrichmentNote.startswith("Could not load Outreach Settings:")
    assert "DB locked" in result.enrichmentNote
    assert result.recruiterOutreachTemplate == _BOTH_TEMPLATES["recruiter"]
    assert any(level == "error" for _, level in log_records)


@pytest.mark.asyncio
async def test_reclassify_settings_read_failure_cache_hit_completes_with_note(db):
    """Settings read failure on cache-hit path completes without crash."""
    from src.db.cache import set_contact_sample
    from src.core.enrichment.contact_sample import company_cache_slug

    job_id = _make_accepted_job_with_contacts(db)
    slug = company_cache_slug("Acme", "https://www.linkedin.com/company/acme/")
    set_contact_sample(
        slug,
        [{"firstName": "Bob", "linkedinUrl": "https://linkedin.com/in/bob", "headline": "HR Manager"}],
        stream="recruiters",
        db_path=db,
    )

    with patch("src.pipelines.database.get_outreach_settings", side_effect=Exception("DB locked")), \
         patch("src.pipelines.source_contacts", new=AsyncMock(return_value=[])), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=_BOTH_TEMPLATES)):
        from src.pipelines import run_reclassify_pipeline
        result = await run_reclassify_pipeline(job_id)

    assert result is not None
    assert result.status == "accepted"
    assert result.enrichmentNote.startswith("Could not load Outreach Settings:")
    assert result.recruiterOutreachTemplate == _BOTH_TEMPLATES["recruiter"]


@pytest.mark.asyncio
async def test_reclassify_template_generation_failure_persists_note(db):
    """Template generation failure leaves Accepted job with explanatory note."""
    job_id = _make_accepted_job_with_contacts(db)

    with patch("src.db.cache.get_contact_sample", return_value=None), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(side_effect=Exception("LLM timeout"))):
        from src.pipelines import run_reclassify_pipeline
        result = await run_reclassify_pipeline(job_id)

    assert result is not None
    assert result.status == "accepted"
    assert result.enrichmentNote.startswith("Outreach template generation failed:")
    assert "LLM timeout" in result.enrichmentNote


@pytest.mark.asyncio
async def test_reclassify_contact_sourcing_failure_persists_note(db):
    """Contact sourcing failure on cache-hit path persists note and templates."""
    from src.db.cache import set_contact_sample
    from src.core.enrichment.contact_sample import company_cache_slug

    job_id = _make_accepted_job_with_contacts(db)
    slug = company_cache_slug("Acme", "https://www.linkedin.com/company/acme/")
    set_contact_sample(
        slug,
        [{"firstName": "Bob", "linkedinUrl": "https://linkedin.com/in/bob", "headline": "HR Manager"}],
        stream="recruiters",
        db_path=db,
    )

    with patch("src.pipelines.source_contacts", new=AsyncMock(side_effect=Exception("Apify trigger failed"))), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=_BOTH_TEMPLATES)):
        from src.pipelines import run_reclassify_pipeline
        result = await run_reclassify_pipeline(job_id)

    assert result is not None
    assert result.status == "accepted"
    assert result.enrichmentNote.startswith("Contact sourcing failed:")
    assert result.recruiterOutreachTemplate == _BOTH_TEMPLATES["recruiter"]


@pytest.mark.asyncio
async def test_run_reclassify_task_settings_failure_reaches_terminal_state(db):
    """Dashboard re-classify task completes (not stuck) when settings read fails."""
    from src.web.server import run_reclassify_task_with_logs, TaskState, active_tasks
    import uuid

    job_id = _make_accepted_job_with_contacts(db)
    task_id = str(uuid.uuid4())
    state = TaskState({"job_id": job_id})
    active_tasks[task_id] = state

    with patch("src.pipelines.database.get_outreach_settings", side_effect=Exception("DB locked")), \
         patch("src.db.cache.get_contact_sample", return_value=None), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=_BOTH_TEMPLATES)):
        await run_reclassify_task_with_logs(task_id, job_id)

    assert state.status == "completed"
    assert state.result is not None
    assert any(
        "Could not load Outreach Settings" in entry.get("message", "")
        for entry in state.logs
        if entry.get("level") == "error"
    )
