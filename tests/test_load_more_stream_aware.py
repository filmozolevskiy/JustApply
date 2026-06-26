"""Tests for stream-aware Load More Contacts — preflight endpoint and per-stream pipeline."""
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


def _make_accepted_job(db, contacts=None, company_url="https://www.linkedin.com/company/acme/"):
    from src.db.jobs import add_job, enrich_job
    from src.core.enrichment.coordinator import begin_enrichment
    job_id = add_job({
        "title": "QA Engineer",
        "company": "Acme",
        "companyUrl": company_url,
        "status": "scraped",
    }, db_path=db)
    begin_enrichment(job_id, db)
    enrich_job(
        job_id,
        contacts=contacts or [],
        outreach_message="Hello",
        db_path=db,
    )
    return job_id


# --- Preflight endpoint ---

def test_preflight_recruiter_below_cap_returns_stream(db):
    """Stream with recruiter count below cap and per-stream cache → billable."""
    job_id = _make_accepted_job(db, contacts=[
        {"name": "Alice", "title": "Recruiter", "url": "", "contacted": False,
         "russian_speaker": False, "is_recruiter": True},
    ])
    set_contact_sample("acme", [{"firstName": "Alice"}], stream="recruiters", db_path=db)
    database.save_outreach_settings(target_recruiters=True, target_russian_speakers=False, db_path=db)

    resp = client.get(f"/api/jobs/{job_id}/load-more-preflight")
    assert resp.status_code == 200
    data = resp.json()
    streams = [s["stream"] for s in data["billable_streams"]]
    assert "Recruiters" in streams


def test_preflight_recruiter_at_cap_still_billable(db):
    """Contact count does not cap Load More — recruiter stream with cache remains billable."""
    contacts = [
        {"name": f"R{i}", "title": "Recruiter", "url": f"/in/r{i}", "contacted": False,
         "russian_speaker": False, "is_recruiter": True}
        for i in range(3)
    ]
    job_id = _make_accepted_job(db, contacts=contacts)
    set_contact_sample("acme", [{"firstName": "Alice"}], stream="recruiters", db_path=db)
    database.save_outreach_settings(target_recruiters=True, target_russian_speakers=False, db_path=db)

    resp = client.get(f"/api/jobs/{job_id}/load-more-preflight")
    data = resp.json()
    streams = [s["stream"] for s in data["billable_streams"]]
    assert "Recruiters" in streams


def test_preflight_russian_at_cap_still_billable(db):
    """Contact count does not cap Load More — russian stream with cache remains billable."""
    contacts = [
        {"name": f"I{i}", "title": "Dev", "url": f"/in/i{i}", "contacted": False,
         "russian_speaker": True, "is_recruiter": False}
        for i in range(5)
    ]
    job_id = _make_accepted_job(db, contacts=contacts)
    set_contact_sample("acme", [{"firstName": "Ivan"}], stream="russian", db_path=db)
    database.save_outreach_settings(target_recruiters=False, target_russian_speakers=True, db_path=db)

    resp = client.get(f"/api/jobs/{job_id}/load-more-preflight")
    data = resp.json()
    streams = [s["stream"] for s in data["billable_streams"]]
    assert "Russian Speakers" in streams


def test_preflight_inactive_toggle_excluded(db):
    """Inactive audience toggle → stream not billable even if below cap."""
    job_id = _make_accepted_job(db, contacts=[])
    set_contact_sample("acme", [{"firstName": "Ivan"}], stream="recruiters", db_path=db)
    database.save_outreach_settings(target_recruiters=False, target_russian_speakers=False, db_path=db)

    resp = client.get(f"/api/jobs/{job_id}/load-more-preflight")
    data = resp.json()
    assert data["estimated_runs"] == 0
    assert data["billable_streams"] == []


def test_preflight_no_cache_is_billable_page_one(db):
    """Missing per-stream cache → billable at page 1."""
    job_id = _make_accepted_job(db, contacts=[])
    database.save_outreach_settings(target_recruiters=True, target_russian_speakers=False, db_path=db)

    resp = client.get(f"/api/jobs/{job_id}/load-more-preflight")
    data = resp.json()
    assert data["estimated_runs"] == 1
    assert data["billable_streams"][0]["page"] == 1
    assert data["billable_streams"][0]["stream"] == "Recruiters"


def test_preflight_exhausted_stream_excluded(db):
    """Stream Exhausted (last_fetch_empty) → not billable."""
    job_id = _make_accepted_job(db, contacts=[])
    set_contact_sample("acme", [], last_fetch_empty=True, stream="recruiters", db_path=db)
    database.save_outreach_settings(target_recruiters=True, target_russian_speakers=False, db_path=db)

    resp = client.get(f"/api/jobs/{job_id}/load-more-preflight")
    data = resp.json()
    assert data["estimated_runs"] == 0
    assert data["blocked_reason"] == "all_streams_exhausted"


def test_preflight_blocked_reason_no_audience_toggles(db):
    job_id = _make_accepted_job(db, contacts=[])
    database.save_outreach_settings(target_recruiters=False, target_russian_speakers=False, db_path=db)

    resp = client.get(f"/api/jobs/{job_id}/load-more-preflight")
    data = resp.json()
    assert data["estimated_runs"] == 0
    assert data["blocked_reason"] == "no_audience_toggles"


def test_preflight_both_short_streams_returns_both(db):
    """Both active streams below cap → both in billable_streams."""
    job_id = _make_accepted_job(db, contacts=[])
    set_contact_sample("acme", [{"firstName": "Alice"}], pages_fetched=1, stream="recruiters", db_path=db)
    set_contact_sample("acme", [{"firstName": "Ivan"}], pages_fetched=2, stream="russian", db_path=db)

    resp = client.get(f"/api/jobs/{job_id}/load-more-preflight")
    data = resp.json()
    assert data["estimated_runs"] == 2
    streams = {s["stream"] for s in data["billable_streams"]}
    assert "Recruiters" in streams
    assert "Russian Speakers" in streams


def test_preflight_page_number_is_pages_fetched_plus_one(db):
    """Page number in billable_streams = cache pages_fetched + 1."""
    job_id = _make_accepted_job(db, contacts=[])
    set_contact_sample("acme", [{"firstName": "Alice"}], pages_fetched=3, stream="recruiters", db_path=db)
    database.save_outreach_settings(target_recruiters=True, target_russian_speakers=False, db_path=db)

    resp = client.get(f"/api/jobs/{job_id}/load-more-preflight")
    data = resp.json()
    assert data["billable_streams"][0]["page"] == 4


def test_preflight_estimated_cost_per_run(db):
    """estimated_cost = estimated_runs × 0.05."""
    job_id = _make_accepted_job(db, contacts=[])
    set_contact_sample("acme", [{"firstName": "Alice"}], stream="recruiters", db_path=db)
    set_contact_sample("acme", [{"firstName": "Ivan"}], stream="russian", db_path=db)

    resp = client.get(f"/api/jobs/{job_id}/load-more-preflight")
    data = resp.json()
    assert data["estimated_cost"] == round(data["estimated_runs"] * 0.05, 2)


def test_preflight_returns_404_for_unknown_job(db):
    resp = client.get("/api/jobs/9999/load-more-preflight")
    assert resp.status_code == 404


# --- Pipeline: stream-aware Apify dispatch ---

def _make_job_with_per_stream_caches(db, contacts=None, recruiter_pages=1, russian_pages=1,
                                      with_russian_cache=True):
    job_id = _make_accepted_job(db, contacts=contacts or [])
    slug = "acme"
    set_contact_sample(slug, [{"firstName": "Alice"}], pages_fetched=recruiter_pages,
                       stream="recruiters", db_path=db)
    if with_russian_cache:
        set_contact_sample(slug, [{"firstName": "Ivan"}], pages_fetched=russian_pages,
                           stream="russian", db_path=db)
    return job_id


@pytest.mark.asyncio
async def test_pipeline_calls_apify_for_recruiters_when_recruiter_short(db):
    """Pipeline calls _run_apify_for_recruiters when recruiters stream is below cap."""
    from src.pipelines import run_load_more_contacts_pipeline
    import src.pipelines as pipelines_module
    job_id = _make_job_with_per_stream_caches(db, contacts=[
        {"name": "Alice", "title": "Recruiter", "url": "", "contacted": False,
         "russian_speaker": False, "is_recruiter": True},
    ], with_russian_cache=False)
    database.save_outreach_settings(target_recruiters=True, target_russian_speakers=False, db_path=db)

    with patch.object(pipelines_module, "_run_apify_for_recruiters", new=AsyncMock(return_value=[])) as mock_apify, \
         patch.object(pipelines_module, "source_contacts", new=AsyncMock(return_value=[])), \
         patch.object(pipelines_module, "generate_outreach_templates", new=AsyncMock(return_value={})):
        await run_load_more_contacts_pipeline(job_id)

    mock_apify.assert_called_once()


@pytest.mark.asyncio
async def test_pipeline_calls_apify_for_russian_when_russian_short(db):
    """Pipeline calls _run_apify_for_russian_speakers when russian stream is below cap."""
    from src.pipelines import run_load_more_contacts_pipeline
    import src.pipelines as pipelines_module
    job_id = _make_job_with_per_stream_caches(db, contacts=[
        {"name": "Ivan", "title": "Dev", "url": "", "contacted": False,
         "russian_speaker": True, "is_recruiter": False},
    ], recruiter_pages=1, with_russian_cache=True)
    database.save_outreach_settings(target_recruiters=False, target_russian_speakers=True, db_path=db)

    with patch.object(pipelines_module, "_run_apify_for_russian_speakers", new=AsyncMock(return_value=[])) as mock_apify, \
         patch.object(pipelines_module, "source_contacts", new=AsyncMock(return_value=[])), \
         patch.object(pipelines_module, "generate_outreach_templates", new=AsyncMock(return_value={})):
        await run_load_more_contacts_pipeline(job_id)

    mock_apify.assert_called_once()


@pytest.mark.asyncio
async def test_pipeline_skips_exhausted_stream(db):
    """Pipeline does not call Apify for a Stream Exhausted stream."""
    job_id = _make_job_with_per_stream_caches(db, contacts=[], with_russian_cache=False)
    set_contact_sample("acme", [], last_fetch_empty=True, stream="recruiters", db_path=db)
    database.save_outreach_settings(target_recruiters=True, target_russian_speakers=False, db_path=db)

    from src.pipelines import run_load_more_contacts_pipeline
    import src.pipelines as pipelines_module
    with patch.object(pipelines_module, "_run_apify_for_recruiters", new=AsyncMock(return_value=[])) as mock_recruiters, \
         patch.object(pipelines_module, "source_contacts", new=AsyncMock(return_value=[])), \
         patch.object(pipelines_module, "generate_outreach_templates", new=AsyncMock(return_value={})):
        with pytest.raises(ValueError):
            await run_load_more_contacts_pipeline(job_id)

    mock_recruiters.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_fetches_page_one_when_no_cache(db):
    """Pipeline calls Apify at page 1 when per-stream cache is missing."""
    from src.pipelines import run_load_more_contacts_pipeline
    import src.pipelines as pipelines_module
    job_id = _make_accepted_job(db, contacts=[])
    database.save_outreach_settings(target_recruiters=True, target_russian_speakers=False, db_path=db)

    with patch.object(pipelines_module, "_run_apify_for_recruiters", new=AsyncMock(return_value=[])) as mock_apify, \
         patch.object(pipelines_module, "source_contacts", new=AsyncMock(return_value=[])), \
         patch.object(pipelines_module, "generate_outreach_templates", new=AsyncMock(return_value={})):
        await run_load_more_contacts_pipeline(job_id)

    mock_apify.assert_called_once()
    assert mock_apify.call_args.kwargs.get("start_page") == 1


@pytest.mark.asyncio
async def test_pipeline_appends_to_per_stream_cache(db):
    """Pipeline appends new profiles to the correct per-stream cache entry."""
    from src.pipelines import run_load_more_contacts_pipeline
    import src.pipelines as pipelines_module
    from src.core.enrichment.contact_sample import company_cache_slug
    job_id = _make_job_with_per_stream_caches(db, contacts=[], with_russian_cache=False)
    database.save_outreach_settings(target_recruiters=True, target_russian_speakers=False, db_path=db)

    new_profiles = [{"firstName": "Bob", "linkedinUrl": "https://linkedin.com/in/bob/"}]
    with patch.object(pipelines_module, "_run_apify_for_recruiters", new=AsyncMock(return_value=new_profiles)), \
         patch.object(pipelines_module, "source_contacts", new=AsyncMock(return_value=[])), \
         patch.object(pipelines_module, "generate_outreach_templates", new=AsyncMock(return_value={})):
        await run_load_more_contacts_pipeline(job_id)

    slug = company_cache_slug("Acme", "https://www.linkedin.com/company/acme/")
    cached = get_contact_sample(slug, stream="recruiters", db_path=db)
    assert cached is not None
    assert cached["pages_fetched"] == 2
    names = [p["firstName"] for p in cached["profiles"]]
    assert "Bob" in names


@pytest.mark.asyncio
async def test_pipeline_raises_when_all_streams_exhausted(db):
    """Pipeline raises ValueError when all active streams are Stream Exhausted."""
    from src.pipelines import run_load_more_contacts_pipeline
    job_id = _make_job_with_per_stream_caches(db, contacts=[], with_russian_cache=False)
    set_contact_sample("acme", [], last_fetch_empty=True, stream="recruiters", db_path=db)
    database.save_outreach_settings(target_recruiters=True, target_russian_speakers=False, db_path=db)

    with pytest.raises(ValueError):
        await run_load_more_contacts_pipeline(job_id)


@pytest.mark.asyncio
async def test_pipeline_calls_apify_with_correct_start_page(db):
    """Pipeline passes start_page = pages_fetched + 1 to the stream-specific Apify function."""
    from src.pipelines import run_load_more_contacts_pipeline
    import src.pipelines as pipelines_module
    job_id = _make_job_with_per_stream_caches(db, contacts=[], recruiter_pages=3, with_russian_cache=False)
    database.save_outreach_settings(target_recruiters=True, target_russian_speakers=False, db_path=db)

    with patch.object(pipelines_module, "_run_apify_for_recruiters", new=AsyncMock(return_value=[])) as mock_apify, \
         patch.object(pipelines_module, "source_contacts", new=AsyncMock(return_value=[])), \
         patch.object(pipelines_module, "generate_outreach_templates", new=AsyncMock(return_value={})):
        await run_load_more_contacts_pipeline(job_id)

    call_kwargs = mock_apify.call_args
    start_page = call_kwargs.kwargs.get("start_page")
    assert start_page == 4


# --- Dashboard JS ---

def test_dashboard_load_more_fetches_preflight():
    """loadMoreContacts JS fetches the load-more-preflight endpoint."""
    from kanban_js import read_dashboard_html
    content = read_dashboard_html()
    assert "load-more-preflight" in content


def test_dashboard_load_more_uses_blocked_reason():
    """loadMoreContacts shows specific acknowledgement from blocked_reason, not generic cap message."""
    from kanban_js import read_dashboard_html
    content = read_dashboard_html()
    idx = content.find("loadMoreContacts")
    assert idx != -1
    nearby = content[idx:idx + 1200]
    assert "blocked_reason" in nearby
    assert "showSpendAckModal(" in nearby
    assert "alert(" not in nearby
    assert "at cap" not in nearby.lower()


def test_dashboard_load_more_confirm_includes_stream_and_page():
    """loadMoreContacts confirm builds lines from billable_streams and includes page number."""
    from kanban_js import read_dashboard_html
    content = read_dashboard_html()
    idx = content.find("loadMoreContacts")
    assert idx != -1
    nearby = content[idx:idx + 1200]
    assert "billable_streams" in nearby, "confirm must reference billable_streams"
    assert "page" in nearby, "confirm must include page number"
