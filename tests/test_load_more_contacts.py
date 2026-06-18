"""Tests for Load More Contacts — append next Apify page to cache and re-classify."""
import os
import sys
import pytest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.db.connection as _db_connection
from src import db as database
from src.db.cache import get_contact_sample, set_contact_sample
from src.web.server import app
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.fixture
def db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test.db")
    monkeypatch.setattr(_db_connection, "DB_PATH", test_db)
    database.init_db(test_db)
    return test_db


# --- Cache schema: pages_fetched ---

def test_cache_returns_pages_fetched_default_one(db):
    """get_contact_sample returns pages_fetched=1 for a newly cached sample."""
    set_contact_sample("acme", [{"firstName": "Ivan"}], display_name="Acme", db_path=db)
    cached = get_contact_sample("acme", db_path=db)
    assert cached["pages_fetched"] == 1


def test_cache_set_with_explicit_pages_fetched(db):
    """set_contact_sample respects explicit pages_fetched value."""
    set_contact_sample("acme", [{"firstName": "Ivan"}], pages_fetched=3, db_path=db)
    cached = get_contact_sample("acme", db_path=db)
    assert cached["pages_fetched"] == 3


# --- append_contact_sample ---

def test_append_dedupes_by_normalized_linkedin_url(db):
    """append_contact_sample dedupes new profiles that share a LinkedIn URL with existing ones."""
    from src.db.cache import append_contact_sample
    existing = [{"firstName": "Ivan", "linkedinUrl": "https://linkedin.com/in/ivan/"}]
    set_contact_sample("acme", existing, db_path=db)
    new_profiles = [
        {"firstName": "Ivan", "linkedinUrl": "https://linkedin.com/in/ivan/"},  # dup
        {"firstName": "Anna", "linkedinUrl": "https://linkedin.com/in/anna/"},   # new
    ]
    append_contact_sample("acme", new_profiles, db_path=db)
    cached = get_contact_sample("acme", db_path=db)
    assert len(cached["profiles"]) == 2
    names = [p["firstName"] for p in cached["profiles"]]
    assert "Ivan" in names
    assert "Anna" in names


def test_append_increments_pages_fetched(db):
    """append_contact_sample increments pages_fetched by 1."""
    from src.db.cache import append_contact_sample
    set_contact_sample("acme", [{"firstName": "Ivan"}], db_path=db)
    append_contact_sample("acme", [{"firstName": "Anna", "linkedinUrl": ""}], db_path=db)
    cached = get_contact_sample("acme", db_path=db)
    assert cached["pages_fetched"] == 2


def test_append_second_call_increments_again(db):
    """Each append_contact_sample call increments pages_fetched."""
    from src.db.cache import append_contact_sample
    set_contact_sample("acme", [{"firstName": "Ivan"}], db_path=db)
    append_contact_sample("acme", [{"firstName": "Anna", "linkedinUrl": ""}], db_path=db)
    append_contact_sample("acme", [{"firstName": "Boris", "linkedinUrl": ""}], db_path=db)
    cached = get_contact_sample("acme", db_path=db)
    assert cached["pages_fetched"] == 3


# --- Pipeline: run_load_more_contacts_pipeline ---

def _make_accepted_job_with_cache(db):
    """Insert an accepted job with a recruiter contact and a seeded per-stream recruiters cache."""
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
    set_contact_sample(
        "acme",
        [{"firstName": "Alice", "linkedinUrl": ""}],
        display_name="Acme",
        stream="recruiters",
        db_path=db,
    )
    return job_id


@pytest.mark.asyncio
async def test_pipeline_raises_for_unknown_job(db):
    from src.pipelines import run_load_more_contacts_pipeline
    with pytest.raises(ValueError, match="not found"):
        await run_load_more_contacts_pipeline(9999)


@pytest.mark.asyncio
async def test_pipeline_raises_for_non_accepted_job(db):
    from src.db.jobs import add_job
    from src.pipelines import run_load_more_contacts_pipeline
    job_id = add_job({"title": "Dev", "company": "TechCo", "status": "found"}, db_path=db)
    with pytest.raises(ValueError, match="[Aa]ccepted"):
        await run_load_more_contacts_pipeline(job_id)


@pytest.mark.asyncio
async def test_pipeline_raises_when_no_cache(db):
    from src.pipelines import run_load_more_contacts_pipeline
    job_id = _make_accepted_job_with_cache(db)
    with patch("src.db.cache.get_contact_sample", return_value=None):
        with pytest.raises(ValueError, match="[Cc]ache"):
            await run_load_more_contacts_pipeline(job_id)


@pytest.mark.asyncio
async def test_pipeline_calls_apify_with_next_page(db):
    """Pipeline calls stream-specific Apify with start_page = pages_fetched + 1."""
    from src.pipelines import run_load_more_contacts_pipeline
    import src.pipelines as pipelines_module
    job_id = _make_accepted_job_with_cache(db)  # recruiters cache pages_fetched=1

    new_profiles = [{"firstName": "Bob", "linkedinUrl": "https://linkedin.com/in/bob/"}]
    new_contacts = [{"name": "Bob Smith", "title": "Engineer", "url": "https://linkedin.com/in/bob/",
                     "contacted": False, "russian_speaker": False, "is_recruiter": False}]
    new_templates = {"recruiter": "Hello ______,", "russian_speaker": ""}

    with patch.object(pipelines_module, "_run_apify_for_recruiters", new=AsyncMock(return_value=new_profiles)) as mock_apify, \
         patch.object(pipelines_module, "source_contacts", new=AsyncMock(return_value=new_contacts)), \
         patch.object(pipelines_module, "generate_outreach_templates", new=AsyncMock(return_value=new_templates)):
        await run_load_more_contacts_pipeline(job_id)

    mock_apify.assert_called_once()
    call_kwargs = mock_apify.call_args
    start_page = call_kwargs.kwargs.get("start_page")
    assert start_page == 2, f"Expected start_page=2, got {start_page}"


@pytest.mark.asyncio
async def test_pipeline_appends_profiles_to_cache(db):
    """Pipeline appends new profiles to per-stream cache and increments pages_fetched."""
    from src.pipelines import run_load_more_contacts_pipeline
    import src.pipelines as pipelines_module
    from src.core.enrichment.contact_sample import company_cache_slug
    job_id = _make_accepted_job_with_cache(db)

    new_profiles = [{"firstName": "Bob", "linkedinUrl": "https://linkedin.com/in/bob/"}]
    new_contacts = [{"name": "Bob Smith", "title": "Engineer", "url": "",
                     "contacted": False, "russian_speaker": False, "is_recruiter": False}]
    new_templates = {"recruiter": "Hello ______,", "russian_speaker": ""}

    with patch.object(pipelines_module, "_run_apify_for_recruiters", new=AsyncMock(return_value=new_profiles)), \
         patch.object(pipelines_module, "source_contacts", new=AsyncMock(return_value=new_contacts)), \
         patch.object(pipelines_module, "generate_outreach_templates", new=AsyncMock(return_value=new_templates)):
        await run_load_more_contacts_pipeline(job_id)

    slug = company_cache_slug("Acme", "https://www.linkedin.com/company/acme/")
    cached = get_contact_sample(slug, stream="recruiters", db_path=db)
    assert cached["pages_fetched"] == 2
    assert len(cached["profiles"]) == 2  # original Alice + new Bob


@pytest.mark.asyncio
async def test_pipeline_job_stays_accepted(db):
    """Job status remains 'accepted' after load-more."""
    from src.pipelines import run_load_more_contacts_pipeline
    import src.pipelines as pipelines_module
    job_id = _make_accepted_job_with_cache(db)

    new_profiles = [{"firstName": "Bob", "linkedinUrl": "https://linkedin.com/in/bob/"}]
    new_contacts = [{"name": "Bob Smith", "title": "Engineer", "url": "",
                     "contacted": False, "russian_speaker": False, "is_recruiter": False}]
    new_templates = {"recruiter": "", "russian_speaker": ""}

    with patch.object(pipelines_module, "_run_apify_for_recruiters", new=AsyncMock(return_value=new_profiles)), \
         patch.object(pipelines_module, "source_contacts", new=AsyncMock(return_value=new_contacts)), \
         patch.object(pipelines_module, "generate_outreach_templates", new=AsyncMock(return_value=new_templates)):
        updated = await run_load_more_contacts_pipeline(job_id)

    assert updated.status == "accepted"


@pytest.mark.asyncio
async def test_second_load_more_requests_page_3(db):
    """When pages_fetched=2, next load-more calls Apify with start_page=3."""
    from src.pipelines import run_load_more_contacts_pipeline
    import src.pipelines as pipelines_module
    from src.core.enrichment.contact_sample import company_cache_slug
    job_id = _make_accepted_job_with_cache(db)
    slug = company_cache_slug("Acme", "https://www.linkedin.com/company/acme/")
    # Simulate one prior load-more already done
    set_contact_sample(slug, [{"firstName": "Alice", "linkedinUrl": ""}], pages_fetched=2,
                       stream="recruiters", db_path=db)

    new_profiles = [{"firstName": "Carol", "linkedinUrl": "https://linkedin.com/in/carol/"}]
    new_contacts = []
    new_templates = {"recruiter": "", "russian_speaker": ""}

    with patch.object(pipelines_module, "_run_apify_for_recruiters", new=AsyncMock(return_value=new_profiles)) as mock_apify, \
         patch.object(pipelines_module, "source_contacts", new=AsyncMock(return_value=new_contacts)), \
         patch.object(pipelines_module, "generate_outreach_templates", new=AsyncMock(return_value=new_templates)):
        await run_load_more_contacts_pipeline(job_id)

    mock_apify.assert_called_once()
    call_kwargs = mock_apify.call_args
    start_page = call_kwargs.kwargs.get("start_page")
    assert start_page == 3, f"Expected start_page=3, got {start_page}"


# --- API endpoint ---

def test_load_more_endpoint_returns_404_for_unknown_job(db):
    resp = client.post("/api/jobs/9999/load-more-contacts")
    assert resp.status_code == 404


def test_load_more_endpoint_returns_422_for_non_accepted_job(db):
    from src.db.jobs import add_job
    job_id = add_job({"title": "Dev", "company": "TechCo", "status": "found"}, db_path=db)
    resp = client.post(f"/api/jobs/{job_id}/load-more-contacts")
    assert resp.status_code == 422
    assert "accepted" in resp.json()["message"].lower()


def test_load_more_endpoint_returns_422_when_no_cache(db):
    job_id = _make_accepted_job_with_cache(db)
    with patch("src.db.cache.get_contact_sample", return_value=None):
        resp = client.post(f"/api/jobs/{job_id}/load-more-contacts")
    assert resp.status_code == 422
    assert "cache" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_load_more_endpoint_logs_activity(db):
    import src.pipelines as pipelines_module
    job_id = _make_accepted_job_with_cache(db)

    new_profiles = [{"firstName": "Bob", "linkedinUrl": "https://linkedin.com/in/bob/"}]
    new_contacts = [{"name": "Bob Smith", "title": "Engineer", "url": "https://linkedin.com/in/bob/",
                     "contacted": False, "russian_speaker": False, "is_recruiter": False}]
    new_templates = {"recruiter": "Hello ______,", "russian_speaker": ""}

    with patch.object(pipelines_module, "_run_apify_for_recruiters", new=AsyncMock(return_value=new_profiles)), \
         patch.object(pipelines_module, "source_contacts", new=AsyncMock(return_value=new_contacts)), \
         patch.object(pipelines_module, "generate_outreach_templates", new=AsyncMock(return_value=new_templates)):
        resp = client.post(f"/api/jobs/{job_id}/load-more-contacts")

    assert resp.status_code == 200
    data = resp.json()
    assert any("Load more contacts" in e["message"] for e in data["activityLog"])
    assert any("new profile" in e["message"] for e in data["activityLog"])


# --- Drawer UI ---

def test_drawer_shows_load_more_contacts_button():
    from kanban_js import read_drawer_controller
    content = read_drawer_controller()
    assert "Load More Contacts" in content, \
        "drawerController.js must contain 'Load More Contacts' button text"
    assert "loadMoreContacts" in content, \
        "drawerController.js must call loadMoreContacts()"


def test_drawer_load_more_only_on_accepted_jobs():
    from kanban_js import read_drawer_controller
    content = read_drawer_controller()
    idx = content.find("Load More Contacts")
    assert idx != -1
    nearby = content[max(0, idx - 600):idx + 50]
    assert "hasContactSampleActions" in nearby, \
        "Load More Contacts button must be gated via hasContactSampleActions (accepted + enriched)"


def test_drawer_load_more_gated_on_enrichment_not_contact_count():
    from kanban_js import read_drawer_controller
    content = read_drawer_controller()
    assert "hasContactSampleActions" in content, \
        "drawerController must gate Load More / Re-classify via hasContactSampleActions"
    idx = content.find("Load More Contacts")
    assert idx != -1
    nearby = content[max(0, idx - 600):idx + 50]
    assert "hasContactSampleActions" in nearby, \
        "Load More Contacts must use hasContactSampleActions (not contacts.length only)"


# --- Dashboard JS export ---

def test_dashboard_exports_load_more_contacts():
    from kanban_js import read_dashboard_html, get_script_section
    script = get_script_section(read_dashboard_html())
    assert "loadMoreContacts" in script, \
        "dashboard.html must define and export loadMoreContacts"
