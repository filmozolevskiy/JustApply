"""Tests for Russian-only filtered enrichment: per-stream cache + Russian Apify filter.

Issue #75: Russian-only enrichment path uses (company_slug, 'russian') cache key,
calls Apify with Russian search + HR exclusion filters and maxItems=5, and caps contacts
at 5 Russian Speakers who are not Recruiters.
"""
import os
import sys
import json
import pytest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.db.connection as _db_connection
import src.core.enrichment.source as source_module
from src import db as database
from src.db.cache import (
    get_contact_sample,
    set_contact_sample,
)
from src.core.enrichment.contact_sample import (
    RUSSIAN_SAMPLE_SIZE,
    RUSSIAN_SEARCH_QUERY,
    RUSSIAN_EXCLUDE_FUNCTION_IDS,
)
from src.core.outreach import source_contacts
from src.schemas import OutreachSettings


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(_db_connection, "DB_PATH", db_path)
    database.init_db(db_path)
    return db_path


@pytest.fixture
def russian_only_settings():
    return OutreachSettings(target_recruiters=False, target_russian_speakers=True)


# ─── Constants ────────────────────────────────────────────────────────────────

def test_russian_constants():
    """RUSSIAN_SAMPLE_SIZE=5, RUSSIAN_SEARCH_QUERY='Russian', RUSSIAN_EXCLUDE_FUNCTION_IDS=['12']."""
    assert RUSSIAN_SAMPLE_SIZE == 5
    assert RUSSIAN_SEARCH_QUERY == "Russian"
    assert RUSSIAN_EXCLUDE_FUNCTION_IDS == ["12"]


# ─── Russian-only Apify orchestration ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_russian_only_calls_apify_for_russian_speakers(db, russian_only_settings):
    """Cache miss → _run_apify_for_russian_speakers is called, not the unfiltered actor."""
    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    mock_russian = AsyncMock(return_value=[])
    with patch.object(source_module, "_run_apify_for_russian_speakers", mock_russian), \
         patch.object(source_module, "_run_apify_actor", AsyncMock(return_value=[])), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=russian_only_settings)

    mock_russian.assert_called_once()


@pytest.mark.asyncio
async def test_russian_only_does_not_call_unfiltered_apify(db, russian_only_settings):
    """Russian-only path never calls the unfiltered Apify fetch."""
    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    mock_unfiltered = AsyncMock(return_value=[])
    with patch.object(source_module, "_run_apify_for_russian_speakers", AsyncMock(return_value=[])), \
         patch.object(source_module, "_run_apify_actor", mock_unfiltered), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=russian_only_settings)

    mock_unfiltered.assert_not_called()


@pytest.mark.asyncio
async def test_russian_only_does_not_call_recruiter_apify(db, russian_only_settings):
    """Russian-only path must not call the recruiter-filtered Apify fetch."""
    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    mock_recruiters = AsyncMock(return_value=[])
    with patch.object(source_module, "_run_apify_for_russian_speakers", AsyncMock(return_value=[])), \
         patch.object(source_module, "_run_apify_for_recruiters", mock_recruiters), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=russian_only_settings)

    mock_recruiters.assert_not_called()


@pytest.mark.asyncio
async def test_russian_only_caches_result_under_russian_stream(db, russian_only_settings):
    """Apify result is written to the 'russian' stream cache key."""
    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    profiles = [{"firstName": "Ivan", "headline": "Engineer", "linkedinUrl": "/in/ivan"}]
    with patch.object(source_module, "_run_apify_for_russian_speakers", AsyncMock(return_value=profiles)), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=russian_only_settings)

    cached = get_contact_sample("acme", stream="russian", db_path=db)
    assert cached is not None
    assert cached["profiles"] == profiles


@pytest.mark.asyncio
async def test_russian_only_does_not_write_legacy_cache(db, russian_only_settings):
    """Russian-only enrichment must not write to the legacy (stream='') cache entry."""
    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    with patch.object(source_module, "_run_apify_for_russian_speakers", AsyncMock(return_value=[])), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=russian_only_settings)

    legacy = get_contact_sample("acme", stream="", db_path=db)
    assert legacy is None


@pytest.mark.asyncio
async def test_russian_only_skips_apify_on_stream_cache_hit(db, russian_only_settings):
    """On 'russian' stream cache hit, Apify is not called."""
    profiles = [{"firstName": "Ivan", "linkedinUrl": "/in/ivan"}]
    set_contact_sample("acme", profiles, stream="russian", db_path=db)

    job = {"title": "Engineer", "company": "Acme", "contacts": []}
    mock_russian = AsyncMock(return_value=[])
    with patch.object(source_module, "_run_apify_for_russian_speakers", mock_russian), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=russian_only_settings)

    mock_russian.assert_not_called()


@pytest.mark.asyncio
async def test_russian_only_empty_apify_is_cached(db, russian_only_settings):
    """Zero-profile Russian Apify result is cached to prevent repeat Apify calls."""
    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    with patch.object(source_module, "_run_apify_for_russian_speakers", AsyncMock(return_value=[])), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=russian_only_settings)

    cached = get_contact_sample("acme", stream="russian", db_path=db)
    assert cached is not None
    assert cached["profiles"] == []


@pytest.mark.asyncio
async def test_russian_only_infrastructure_error_not_cached(db, russian_only_settings):
    """Infrastructure failure is not cached; exception propagates."""
    from src.core.enrichment.contact_sample import ApifyInfrastructureError
    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    with patch.object(source_module, "_run_apify_for_russian_speakers",
                      AsyncMock(side_effect=ApifyInfrastructureError("trigger failed"))):
        with pytest.raises(ApifyInfrastructureError):
            await source_contacts(job, settings=russian_only_settings)

    assert get_contact_sample("acme", stream="russian", db_path=db) is None


@pytest.mark.asyncio
async def test_russian_only_missing_company_url_skips_apify(db, russian_only_settings):
    """Missing companyUrl skips Apify in Russian-only mode."""
    job = {"title": "Engineer", "company": "Acme", "contacts": []}
    mock_russian = AsyncMock(return_value=[])
    with patch.object(source_module, "_run_apify_for_russian_speakers", mock_russian), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=russian_only_settings)

    mock_russian.assert_not_called()


@pytest.mark.asyncio
async def test_russian_only_logs_stream_name(db, russian_only_settings):
    """Task Logs mention 'russian' stream during fetch."""
    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    log_messages = []

    async def capture(msg, level="info"):
        log_messages.append(msg)

    with patch.object(source_module, "_run_apify_for_russian_speakers", AsyncMock(return_value=[])), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=russian_only_settings, log_func=capture)

    combined = " ".join(log_messages).lower()
    assert "russian" in combined


# ─── Non-HR cap (5 Russian Speakers who are not Recruiters) ───────────────────

@pytest.mark.asyncio
async def test_russian_speaker_non_recruiter_cap_is_5():
    """Classifier keeps at most 5 non-HR Russian Speaker contacts in Russian-only mode."""
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

    assert len(result) == 5
    assert all(c["russian_speaker"] for c in result)
    assert all(not c["is_recruiter"] for c in result)


@pytest.mark.asyncio
async def test_recruiter_classified_excluded_from_russian_pool():
    """Profiles classified as Recruiter are excluded from the Russian Speaker pool."""
    from src.core.enrichment.classifier import classify_contacts
    import src.core.gemini_client as gemini_mod

    items = [
        {"firstName": f"RU{i}", "lastName": "Person", "headline": "Engineer",
         "linkedinUrl": f"/in/ru{i}", "currentPosition": "", "location": "Moscow"}
        for i in range(4)
    ]
    # First 2 are pure Russian speakers, last 2 are dual-classified (Russian + Recruiter)
    classified_raw = [
        {"index": 0, "russian_speaker": True, "is_recruiter": False},
        {"index": 1, "russian_speaker": True, "is_recruiter": False},
        {"index": 2, "russian_speaker": True, "is_recruiter": True},
        {"index": 3, "russian_speaker": True, "is_recruiter": True},
    ]
    settings = OutreachSettings(target_recruiters=False, target_russian_speakers=True)

    with patch("src.core.enrichment.classifier.os.getenv", return_value="fake-key"), \
         patch.object(gemini_mod, "generate_text", new=AsyncMock(return_value=json.dumps(classified_raw))):
        result = await classify_contacts(items, settings)

    assert len(result) == 2, f"Expected 2 (non-recruiter Russians only), got {len(result)}"
    assert all(c["russian_speaker"] for c in result)
    assert all(not c["is_recruiter"] for c in result)


@pytest.mark.asyncio
async def test_apify_input_for_russian_speakers():
    """_run_apify_for_russian_speakers sends searchQuery=Russian and excludeFunctionIds=['12']."""
    from src.core.enrichment.contact_sample import _run_apify_for_russian_speakers
    import src.core.enrichment.contact_sample as contact_sample_mod

    captured_inputs = []

    async def mock_fetch(url, *, label, log_func=None, timeout_seconds=300.0,
                         poll_interval=5.0, start_page=1, function_ids=None,
                         max_items=None, search_query=None, exclude_function_ids=None):
        captured_inputs.append({
            "search_query": search_query,
            "exclude_function_ids": exclude_function_ids,
            "max_items": max_items,
        })
        return []

    with patch.object(contact_sample_mod, "_fetch_apify_employees_at_url", mock_fetch):
        await _run_apify_for_russian_speakers(
            "https://www.linkedin.com/company/acme/"
        )

    assert len(captured_inputs) == 1
    inp = captured_inputs[0]
    assert inp["search_query"] == "Russian"
    assert inp["exclude_function_ids"] == ["12"]
    assert inp["max_items"] == 5
