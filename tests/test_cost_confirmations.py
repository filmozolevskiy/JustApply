"""Tests for cost confirmation dialogs — Issue #64, #78.

Server: GET /api/jobs/{id}/cache-status
Client (static): enrichJob confirms on cache miss, loadMoreContacts always confirms,
                 reclassifyJob never confirms.
"""
import os
import sys
import pytest

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


def _make_accepted_job(db, company="Acme", company_url="https://www.linkedin.com/company/acme/"):
    from src.db.jobs import add_job
    from src.core.enrichment.coordinator import begin_enrichment
    job_id = add_job({"title": "QA", "company": company, "companyUrl": company_url, "status": "found"}, db_path=db)
    begin_enrichment(job_id, db)
    return job_id


# ── Server: GET /api/jobs/{id}/cache-status ──────────────────────────────────

def test_cache_status_returns_404_for_unknown_job(db):
    resp = client.get("/api/jobs/9999/cache-status")
    assert resp.status_code == 404


def test_cache_status_returns_has_cache_false_when_no_cache(db):
    job_id = _make_accepted_job(db)
    resp = client.get(f"/api/jobs/{job_id}/cache-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_cache"] is False


def test_cache_status_returns_has_cache_true_when_all_active_streams_cached(db):
    from src.db.cache import set_contact_sample
    from src.core.enrichment.contact_sample import company_cache_slug
    job_id = _make_accepted_job(db)
    slug = company_cache_slug("Acme", "https://www.linkedin.com/company/acme/")
    set_contact_sample(slug, [{"name": "Alice"}], pages_fetched=2, stream="recruiters", db_path=db)
    set_contact_sample(slug, [{"name": "Bob"}], pages_fetched=1, stream="russian", db_path=db)

    resp = client.get(f"/api/jobs/{job_id}/cache-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_cache"] is True
    assert data["estimated_runs"] == 0
    assert data["will_call_apify"] is False


# ── Server: per-stream billable fetch plan ────────────────────────────────────

def test_cache_status_billable_streams_both_on_full_cache_miss(db):
    job_id = _make_accepted_job(db)
    resp = client.get(f"/api/jobs/{job_id}/cache-status")
    assert resp.status_code == 200
    data = resp.json()
    streams = {s["stream"] for s in data["billable_streams"]}
    assert "Recruiters" in streams
    assert "Russian Speakers" in streams
    assert data["estimated_runs"] == 2


def test_cache_status_partial_cache_hit_only_uncached_stream_billable(db):
    from src.db.cache import set_contact_sample
    from src.core.enrichment.contact_sample import company_cache_slug
    job_id = _make_accepted_job(db)
    slug = company_cache_slug("Acme", "https://www.linkedin.com/company/acme/")
    set_contact_sample(slug, [{"name": "Alice"}], stream="recruiters", db_path=db)

    resp = client.get(f"/api/jobs/{job_id}/cache-status")
    data = resp.json()
    stream_names = [s["stream"] for s in data["billable_streams"]]
    assert stream_names == ["Russian Speakers"]
    assert data["estimated_runs"] == 1


def test_cache_status_estimated_cost_two_runs(db):
    job_id = _make_accepted_job(db)
    resp = client.get(f"/api/jobs/{job_id}/cache-status")
    data = resp.json()
    assert data["estimated_runs"] == 2
    assert abs(data["estimated_cost"] - 0.10) < 0.001


def test_cache_status_estimated_cost_one_run(db):
    from src.db.cache import set_contact_sample
    from src.core.enrichment.contact_sample import company_cache_slug
    job_id = _make_accepted_job(db)
    slug = company_cache_slug("Acme", "https://www.linkedin.com/company/acme/")
    set_contact_sample(slug, [{"name": "Alice"}], stream="recruiters", db_path=db)

    resp = client.get(f"/api/jobs/{job_id}/cache-status")
    data = resp.json()
    assert data["estimated_runs"] == 1
    assert abs(data["estimated_cost"] - 0.05) < 0.001


def test_cache_status_billable_streams_include_profile_count(db):
    job_id = _make_accepted_job(db)
    resp = client.get(f"/api/jobs/{job_id}/cache-status")
    data = resp.json()
    for s in data["billable_streams"]:
        assert "profile_count" in s
        assert s["profile_count"] > 0
        assert "page" in s
        assert s["page"] == 1


# ── Client static: enrichJob ─────────────────────────────────────────────────

def _get_function_body(content: str, func_name: str, window: int = 2000) -> str:
    for prefix in (f"async function {func_name}(", f"function {func_name}("):
        idx = content.find(prefix)
        if idx != -1:
            return content[idx: idx + window]
    raise AssertionError(f"{func_name} not found in content")


def _dashboard_script() -> str:
    from kanban_js import get_script_section, read_dashboard_html
    return get_script_section(read_dashboard_html())


def test_enrich_job_fetches_cache_status_before_enrich():
    script = _dashboard_script()
    body = _get_function_body(script, "enrichJob")
    cache_status_idx = body.find("cache-status")
    enrich_idx = body.find("/enrich")
    assert cache_status_idx != -1, "enrichJob must call /cache-status"
    assert enrich_idx != -1, "enrichJob must call /enrich"
    assert cache_status_idx < enrich_idx, "/cache-status check must come before /enrich POST"


def test_enrich_job_shows_confirm_on_cache_miss():
    script = _dashboard_script()
    body = _get_function_body(script, "enrichJob")
    assert "confirm(" in body, "enrichJob must call confirm() for cache-miss case"
    assert "estimated_runs" in body, "enrichJob must branch on estimated_runs"


def test_enrich_confirm_lists_stream_names():
    script = _dashboard_script()
    body = _get_function_body(script, "enrichJob")
    assert "billable_streams" in body, "enrichJob confirm must use billable_streams list"
    assert "s.stream" in body or "stream" in body, "enrichJob confirm must render stream names"


def test_enrich_confirm_shows_run_count_and_cost():
    script = _dashboard_script()
    body = _get_function_body(script, "enrichJob")
    assert "estimated_runs" in body, "enrichJob confirm must show run count"
    assert "estimated_cost" in body, "enrichJob confirm must show estimated cost"


def test_enrich_no_confirm_when_estimated_runs_zero():
    script = _dashboard_script()
    body = _get_function_body(script, "enrichJob")
    assert "estimated_runs > 0" in body, "enrichJob must skip confirm when estimated_runs is 0"


# ── Server: will_call_apify field ────────────────────────────────────────────

def _make_found_job_no_url(db):
    from src.db.jobs import add_job
    return add_job({"title": "QA", "company": "Acumatica", "companyUrl": "", "status": "found"}, db_path=db)


def test_cache_status_will_call_apify_false_when_no_company_url(db):
    job_id = _make_found_job_no_url(db)
    resp = client.get(f"/api/jobs/{job_id}/cache-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["will_call_apify"] is False


def test_cache_status_will_call_apify_true_when_company_url_set_and_no_cache(db):
    job_id = _make_accepted_job(db)
    resp = client.get(f"/api/jobs/{job_id}/cache-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_cache"] is False
    assert data["will_call_apify"] is True


def test_cache_status_will_call_apify_false_when_all_active_streams_cached(db):
    from src.db.cache import set_contact_sample
    from src.core.enrichment.contact_sample import company_cache_slug
    job_id = _make_accepted_job(db)
    slug = company_cache_slug("Acme", "https://www.linkedin.com/company/acme/")
    set_contact_sample(slug, [{"name": "Bob"}], stream="recruiters", db_path=db)
    set_contact_sample(slug, [{"name": "Alice"}], stream="russian", db_path=db)
    resp = client.get(f"/api/jobs/{job_id}/cache-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_cache"] is True
    assert data["will_call_apify"] is False


# ── Client static: loadMoreContacts ──────────────────────────────────────────

def test_load_more_contacts_always_shows_confirm():
    script = _dashboard_script()
    body = _get_function_body(script, "loadMoreContacts")
    assert "confirm(" in body, "loadMoreContacts must call confirm()"


def test_load_more_contacts_cost_estimate_visible():
    script = _dashboard_script()
    body = _get_function_body(script, "loadMoreContacts")
    assert "estimated_cost" in body, "loadMoreContacts confirm must show dynamic estimated_cost from preflight"


def test_load_more_contacts_shows_card_spinner_while_loading():
    script = _dashboard_script()
    body = _get_function_body(script, "loadMoreContacts")
    assert "activeLoadMoreJobId" in body, "loadMoreContacts must set activeLoadMoreJobId"
    assert "renderActiveVariant()" in body, "loadMoreContacts must re-render to show card spinner"
    assert "refreshDrawerIfOpen" in body, "loadMoreContacts must refresh drawer to show loading animation"


# ── Client static: reclassifyJob — no confirm ─────────────────────────────────

def test_reclassify_job_never_shows_confirm():
    script = _dashboard_script()
    body = _get_function_body(script, "reclassifyJob", window=80)
    assert "confirm(" not in body, "reclassifyJob must NOT call confirm() — no Apify spend"


def test_reclassify_job_shows_card_spinner_while_loading():
    script = _dashboard_script()
    assert "activeReclassifyJobIds" in script, "dashboard must track active reclassify job ids"
    spinner_body = _get_function_body(script, "attachReclassifyStream", window=2000)
    assert "activeReclassifyJobIds" in script
    assert "connectTaskLogStream" in spinner_body, "attachReclassifyStream must stream task logs via SSE"
    assert "saveReclassifyTaskEntry" in script
    assert "renderActiveVariant()" in spinner_body
    assert "refreshDrawerIfOpen" in spinner_body
