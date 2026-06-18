"""Tests for Recruiter-only filtered enrichment: per-stream cache + Apify HR filter.

Issue #73: Recruiter-only enrichment path uses (company_slug, 'recruiters') cache key,
calls Apify with HR function filter (functionIds=["12"], maxItems=3), and caps contacts
at 3 Recruiters.
"""
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.db.connection as _db_connection
import src.core.enrichment.source as source_module
from src import db as database
from src.db.cache import (
    get_contact_sample,
    set_contact_sample,
    delete_contact_sample,
    append_contact_sample,
)
from src.core.enrichment.contact_sample import (
    RECRUITER_FUNCTION_IDS,
    RECRUITER_SAMPLE_SIZE,
)
from src.core.outreach import source_contacts
from src.schemas import OutreachSettings


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(_db_connection, "DB_PATH", db_path)
    database.init_db(db_path)
    return db_path


# ─── Per-stream cache schema ───────────────────────────────────────────────────

def test_per_stream_cache_miss_returns_none(db):
    """get_contact_sample for 'recruiters' stream returns None when no entry exists."""
    assert get_contact_sample("acme", stream="recruiters", db_path=db) is None


def test_per_stream_cache_set_and_get(db):
    """set_contact_sample / get_contact_sample round-trip for 'recruiters' stream."""
    profiles = [{"firstName": "Alice", "lastName": "HR", "linkedinUrl": "/in/alice"}]
    set_contact_sample("acme", profiles, display_name="Acme", stream="recruiters", db_path=db)
    cached = get_contact_sample("acme", stream="recruiters", db_path=db)
    assert cached is not None
    assert cached["profiles"] == profiles
    assert cached["display_name"] == "Acme"
    assert cached["pages_fetched"] == 1


def test_per_stream_cache_independent_of_legacy(db):
    """Legacy (stream='') and named stream rows are independent."""
    legacy_profiles = [{"firstName": "Legacy"}]
    stream_profiles = [{"firstName": "Recruiter"}]

    set_contact_sample("acme", legacy_profiles, db_path=db)              # stream=''
    set_contact_sample("acme", stream_profiles, stream="recruiters", db_path=db)

    legacy = get_contact_sample("acme", db_path=db)                      # stream=''
    recruiter = get_contact_sample("acme", stream="recruiters", db_path=db)

    assert legacy["profiles"] == legacy_profiles
    assert recruiter["profiles"] == stream_profiles


def test_legacy_cache_is_miss_for_recruiter_stream(db):
    """A legacy (stream='') cache entry does not satisfy a recruiter-stream lookup."""
    set_contact_sample("acme", [{"firstName": "Ivan"}], db_path=db)  # stream=''
    result = get_contact_sample("acme", stream="recruiters", db_path=db)
    assert result is None


def test_per_stream_cache_stores_empty_list(db):
    """Empty profiles are cached for 'recruiters' stream to prevent repeat Apify calls."""
    set_contact_sample("acme", [], stream="recruiters", db_path=db)
    cached = get_contact_sample("acme", stream="recruiters", db_path=db)
    assert cached is not None
    assert cached["profiles"] == []


def test_per_stream_append_increments_pages_fetched(db):
    """append_contact_sample for 'recruiters' stream increments pages_fetched."""
    initial = [{"firstName": "Alice", "linkedinUrl": "/in/alice"}]
    set_contact_sample("acme", initial, stream="recruiters", db_path=db)

    more = [{"firstName": "Bob", "linkedinUrl": "/in/bob"}]
    append_contact_sample("acme", more, stream="recruiters", db_path=db)

    cached = get_contact_sample("acme", stream="recruiters", db_path=db)
    assert cached["pages_fetched"] == 2
    assert len(cached["profiles"]) == 2


def test_per_stream_delete(db):
    """delete_contact_sample removes only the targeted stream row."""
    set_contact_sample("acme", [{"x": 1}], stream="recruiters", db_path=db)
    set_contact_sample("acme", [{"x": 2}], stream="", db_path=db)

    delete_contact_sample("acme", stream="recruiters", db_path=db)

    assert get_contact_sample("acme", stream="recruiters", db_path=db) is None
    assert get_contact_sample("acme", stream="", db_path=db) is not None


# ─── Recruiter-only Apify orchestration ───────────────────────────────────────

@pytest.fixture
def recruiter_only_settings():
    return OutreachSettings(target_recruiters=True, target_russian_speakers=False)


@pytest.mark.asyncio
async def test_recruiter_only_calls_apify_on_cache_miss(db, recruiter_only_settings):
    """Cache miss → Apify is called with recruiter filter."""
    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    mock_recruiters = AsyncMock(return_value=[])
    with patch.object(source_module, "_run_apify_for_recruiters", mock_recruiters), \
         patch.object(source_module, "_run_apify_actor", AsyncMock(return_value=[])), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=recruiter_only_settings)

    mock_recruiters.assert_called_once()


@pytest.mark.asyncio
async def test_recruiter_only_does_not_call_unfiltered_apify(db, recruiter_only_settings):
    """Recruiter-only path never falls back to the unfiltered Apify fetch."""
    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    mock_unfiltered = AsyncMock(return_value=[])
    with patch.object(source_module, "_run_apify_for_recruiters", AsyncMock(return_value=[])), \
         patch.object(source_module, "_run_apify_actor", mock_unfiltered), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=recruiter_only_settings)

    mock_unfiltered.assert_not_called()


@pytest.mark.asyncio
async def test_recruiter_only_caches_result_under_recruiter_stream(db, recruiter_only_settings):
    """Apify result is written to the 'recruiters' stream cache key."""
    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    profiles = [{"firstName": "Alice", "headline": "HR Manager", "linkedinUrl": "/in/alice"}]
    with patch.object(source_module, "_run_apify_for_recruiters", AsyncMock(return_value=profiles)), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=recruiter_only_settings)

    cached = get_contact_sample("acme", stream="recruiters", db_path=db)
    assert cached is not None
    assert cached["profiles"] == profiles


@pytest.mark.asyncio
async def test_recruiter_only_does_not_write_legacy_cache(db, recruiter_only_settings):
    """Recruiter-only enrichment must not write to the legacy (stream='') cache entry."""
    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    with patch.object(source_module, "_run_apify_for_recruiters", AsyncMock(return_value=[])), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=recruiter_only_settings)

    legacy = get_contact_sample("acme", stream="", db_path=db)
    assert legacy is None


@pytest.mark.asyncio
async def test_recruiter_only_skips_apify_on_stream_cache_hit(db, recruiter_only_settings):
    """On 'recruiters' stream cache hit, Apify is not called."""
    profiles = [{"firstName": "Alice", "linkedinUrl": "/in/alice"}]
    set_contact_sample("acme", profiles, stream="recruiters", db_path=db)

    job = {"title": "Engineer", "company": "Acme", "contacts": []}
    mock_recruiters = AsyncMock(return_value=[])
    with patch.object(source_module, "_run_apify_for_recruiters", mock_recruiters), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=recruiter_only_settings)

    mock_recruiters.assert_not_called()


@pytest.mark.asyncio
async def test_recruiter_only_empty_apify_is_cached(db, recruiter_only_settings):
    """Zero-profile recruiter Apify result is cached to prevent repeat Apify calls."""
    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    with patch.object(source_module, "_run_apify_for_recruiters", AsyncMock(return_value=[])), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=recruiter_only_settings)

    cached = get_contact_sample("acme", stream="recruiters", db_path=db)
    assert cached is not None
    assert cached["profiles"] == []


@pytest.mark.asyncio
async def test_recruiter_only_infrastructure_error_not_cached(db, recruiter_only_settings):
    """Infrastructure failure is not cached; exception propagates."""
    from src.core.enrichment.contact_sample import ApifyInfrastructureError
    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    with patch.object(source_module, "_run_apify_for_recruiters",
                      AsyncMock(side_effect=ApifyInfrastructureError("trigger failed"))):
        with pytest.raises(ApifyInfrastructureError):
            await source_contacts(job, settings=recruiter_only_settings)

    assert get_contact_sample("acme", stream="recruiters", db_path=db) is None


@pytest.mark.asyncio
async def test_recruiter_only_missing_company_url_skips_apify(db, recruiter_only_settings):
    """Missing companyUrl skips Apify in recruiter-only mode."""
    job = {"title": "Engineer", "company": "Acme", "contacts": []}
    mock_recruiters = AsyncMock(return_value=[])
    with patch.object(source_module, "_run_apify_for_recruiters", mock_recruiters), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=recruiter_only_settings)

    mock_recruiters.assert_not_called()


@pytest.mark.asyncio
async def test_recruiter_only_logs_stream_name(db, recruiter_only_settings):
    """Task Logs mention 'recruiters' stream during fetch."""
    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    log_messages = []

    async def capture(msg, level="info"):
        log_messages.append(msg)

    with patch.object(source_module, "_run_apify_for_recruiters", AsyncMock(return_value=[])), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=recruiter_only_settings, log_func=capture)

    combined = " ".join(log_messages).lower()
    assert "recruiter" in combined


# ─── Recruiter cap (3) via classifier ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_recruiter_cap_is_3():
    """Classifier keeps at most 3 Recruiter contacts regardless of input size."""
    import json
    from src.core.enrichment.classifier import classify_contacts
    import src.core.gemini_client as gemini_mod

    items = [
        {"firstName": f"HR{i}", "lastName": "Person", "headline": "Recruiter",
         "linkedinUrl": f"/in/hr{i}", "currentPosition": "", "location": ""}
        for i in range(5)
    ]
    classified_raw = [{"index": i, "russian_speaker": False, "is_recruiter": True} for i in range(5)]
    settings = OutreachSettings(target_recruiters=True, target_russian_speakers=False)

    with patch("src.core.enrichment.classifier.os.getenv", return_value="fake-key"), \
         patch.object(gemini_mod, "generate_text", new=AsyncMock(return_value=json.dumps(classified_raw))):
        result = await classify_contacts(items, settings)

    assert len(result) == 3, f"Expected cap of 3 recruiters, got {len(result)}"
    assert all(c["is_recruiter"] for c in result)


@pytest.mark.asyncio
async def test_russian_speaker_cap_is_5():
    """Classifier keeps at most 5 Russian Speaker contacts."""
    import json
    from src.core.enrichment.classifier import classify_contacts
    import src.core.gemini_client as gemini_mod

    items = [
        {"firstName": f"RU{i}", "lastName": "Person", "headline": "Engineer",
         "linkedinUrl": f"/in/ru{i}", "currentPosition": "", "location": "Moscow"}
        for i in range(7)
    ]
    classified_raw = [{"index": i, "russian_speaker": True, "is_recruiter": False} for i in range(7)]
    settings = OutreachSettings(target_recruiters=False, target_russian_speakers=True)

    with patch("src.core.enrichment.classifier.os.getenv", return_value="fake-key"), \
         patch.object(gemini_mod, "generate_text", new=AsyncMock(return_value=json.dumps(classified_raw))):
        result = await classify_contacts(items, settings)

    assert len(result) == 5, f"Expected cap of 5 Russian speakers, got {len(result)}"
    assert all(c["russian_speaker"] for c in result)


# ─── RECRUITER_SAMPLE_SIZE / RECRUITER_FUNCTION_IDS constants ─────────────────

def test_recruiter_constants():
    """RECRUITER_SAMPLE_SIZE=3 and RECRUITER_FUNCTION_IDS=["12"]."""
    assert RECRUITER_SAMPLE_SIZE == 3
    assert RECRUITER_FUNCTION_IDS == ["12"]
