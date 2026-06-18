"""Tests for dual-audience enrichment: both Recruiters and Russian Speakers toggles on.

Issue #77: When both Contact Search Settings toggles are active, enrichment runs two
Apify fetches (recruiter stream + russian stream), merges profiles by LinkedIn URL,
classifies the combined batch once, and applies caps:
  - up to 5 Russian Speakers with russian_speaker and NOT is_recruiter
  - up to 3 Recruiters
Dual-classified contacts count toward the Recruiter cap only.
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
from src.db.cache import get_contact_sample, set_contact_sample
from src.core.outreach import source_contacts
from src.schemas import OutreachSettings


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(_db_connection, "DB_PATH", db_path)
    database.init_db(db_path)
    return db_path


@pytest.fixture
def dual_settings():
    return OutreachSettings(target_recruiters=True, target_russian_speakers=True)


# ─── Two Apify runs on cache miss ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dual_audience_calls_recruiter_apify_on_cache_miss(db, dual_settings):
    """Both toggles on, cache miss → _run_apify_for_recruiters is called."""
    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    mock_recruiters = AsyncMock(return_value=[])
    mock_russian = AsyncMock(return_value=[])
    with patch.object(source_module, "_run_apify_for_recruiters", mock_recruiters), \
         patch.object(source_module, "_run_apify_for_russian_speakers", mock_russian), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=dual_settings)

    mock_recruiters.assert_called_once()


@pytest.mark.asyncio
async def test_dual_audience_calls_russian_apify_on_cache_miss(db, dual_settings):
    """Both toggles on, cache miss → _run_apify_for_russian_speakers is called."""
    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    mock_recruiters = AsyncMock(return_value=[])
    mock_russian = AsyncMock(return_value=[])
    with patch.object(source_module, "_run_apify_for_recruiters", mock_recruiters), \
         patch.object(source_module, "_run_apify_for_russian_speakers", mock_russian), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=dual_settings)

    mock_russian.assert_called_once()


@pytest.mark.asyncio
async def test_dual_audience_does_not_call_unfiltered_apify(db, dual_settings):
    """Both toggles on → the legacy unfiltered Apify fetch is never called."""
    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    mock_unfiltered = AsyncMock(return_value=[])
    with patch.object(source_module, "_run_apify_for_recruiters", AsyncMock(return_value=[])), \
         patch.object(source_module, "_run_apify_for_russian_speakers", AsyncMock(return_value=[])), \
         patch.object(source_module, "_run_apify_actor", mock_unfiltered), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=dual_settings)

    mock_unfiltered.assert_not_called()


# ─── Per-stream caching ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dual_audience_caches_recruiter_stream(db, dual_settings):
    """Dual-audience enrichment writes Apify result to the 'recruiters' stream cache."""
    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    recruiter_profiles = [{"firstName": "Alice", "headline": "HR", "linkedinUrl": "/in/alice"}]
    with patch.object(source_module, "_run_apify_for_recruiters", AsyncMock(return_value=recruiter_profiles)), \
         patch.object(source_module, "_run_apify_for_russian_speakers", AsyncMock(return_value=[])), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=dual_settings)

    cached = get_contact_sample("acme", stream="recruiters", db_path=db)
    assert cached is not None
    assert cached["profiles"] == recruiter_profiles


@pytest.mark.asyncio
async def test_dual_audience_caches_russian_stream(db, dual_settings):
    """Dual-audience enrichment writes Apify result to the 'russian' stream cache."""
    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    russian_profiles = [{"firstName": "Ivan", "headline": "Engineer", "linkedinUrl": "/in/ivan"}]
    with patch.object(source_module, "_run_apify_for_recruiters", AsyncMock(return_value=[])), \
         patch.object(source_module, "_run_apify_for_russian_speakers", AsyncMock(return_value=russian_profiles)), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=dual_settings)

    cached = get_contact_sample("acme", stream="russian", db_path=db)
    assert cached is not None
    assert cached["profiles"] == russian_profiles


@pytest.mark.asyncio
async def test_dual_audience_recruiter_cache_hit_skips_recruiter_apify(db, dual_settings):
    """When 'recruiters' stream is cached, that Apify call is skipped; Russian still runs."""
    recruiter_profiles = [{"firstName": "Alice", "linkedinUrl": "/in/alice"}]
    set_contact_sample("acme", recruiter_profiles, stream="recruiters", db_path=db)

    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    mock_recruiters = AsyncMock(return_value=[])
    mock_russian = AsyncMock(return_value=[])
    with patch.object(source_module, "_run_apify_for_recruiters", mock_recruiters), \
         patch.object(source_module, "_run_apify_for_russian_speakers", mock_russian), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=dual_settings)

    mock_recruiters.assert_not_called()
    mock_russian.assert_called_once()


@pytest.mark.asyncio
async def test_dual_audience_russian_cache_hit_skips_russian_apify(db, dual_settings):
    """When 'russian' stream is cached, that Apify call is skipped; Recruiter still runs."""
    russian_profiles = [{"firstName": "Ivan", "linkedinUrl": "/in/ivan"}]
    set_contact_sample("acme", russian_profiles, stream="russian", db_path=db)

    job = {
        "title": "Engineer", "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "contacts": [],
    }
    mock_recruiters = AsyncMock(return_value=[])
    mock_russian = AsyncMock(return_value=[])
    with patch.object(source_module, "_run_apify_for_recruiters", mock_recruiters), \
         patch.object(source_module, "_run_apify_for_russian_speakers", mock_russian), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=dual_settings)

    mock_russian.assert_not_called()
    mock_recruiters.assert_called_once()


@pytest.mark.asyncio
async def test_dual_audience_both_cache_hit_skips_all_apify(db, dual_settings):
    """Both streams cached → zero Apify calls."""
    set_contact_sample("acme", [{"firstName": "Alice", "linkedinUrl": "/in/alice"}],
                       stream="recruiters", db_path=db)
    set_contact_sample("acme", [{"firstName": "Ivan", "linkedinUrl": "/in/ivan"}],
                       stream="russian", db_path=db)

    job = {"title": "Engineer", "company": "Acme", "contacts": []}
    mock_recruiters = AsyncMock(return_value=[])
    mock_russian = AsyncMock(return_value=[])
    with patch.object(source_module, "_run_apify_for_recruiters", mock_recruiters), \
         patch.object(source_module, "_run_apify_for_russian_speakers", mock_russian), \
         patch.object(source_module, "classify_contacts", AsyncMock(return_value=[])):
        await source_contacts(job, settings=dual_settings)

    mock_recruiters.assert_not_called()
    mock_russian.assert_not_called()


# ─── Merged batch classification ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dual_audience_classifies_merged_batch(db, dual_settings):
    """classify_contacts receives profiles from both streams merged together."""
    recruiter_profiles = [{"firstName": "Alice", "headline": "HR", "linkedinUrl": "/in/alice"}]
    russian_profiles = [{"firstName": "Ivan", "headline": "Engineer", "linkedinUrl": "/in/ivan"}]

    captured = {}

    async def capture_classify(items, settings):
        captured["items"] = items
        return []

    with patch.object(source_module, "_run_apify_for_recruiters", AsyncMock(return_value=recruiter_profiles)), \
         patch.object(source_module, "_run_apify_for_russian_speakers", AsyncMock(return_value=russian_profiles)), \
         patch.object(source_module, "classify_contacts", capture_classify):
        await source_contacts({"title": "E", "company": "Acme",
                                "companyUrl": "https://www.linkedin.com/company/acme/",
                                "contacts": []}, settings=dual_settings)

    urls = {
        i.get("linkedinUrl") or i.get("linkedInUrl") or i.get("profileUrl") or i.get("url")
        for i in captured.get("items", [])
    }
    assert "/in/alice" in urls
    assert "/in/ivan" in urls


@pytest.mark.asyncio
async def test_dual_audience_deduplicates_overlapping_profiles(db, dual_settings):
    """A profile appearing in both streams is included only once in the classification batch."""
    shared = {"firstName": "Dual", "headline": "HR", "linkedinUrl": "/in/shared"}
    unique_russian = {"firstName": "Ivan", "headline": "Engineer", "linkedinUrl": "/in/ivan"}

    captured = {}

    async def capture_classify(items, settings):
        captured["items"] = items
        return []

    with patch.object(source_module, "_run_apify_for_recruiters", AsyncMock(return_value=[shared])), \
         patch.object(source_module, "_run_apify_for_russian_speakers",
                      AsyncMock(return_value=[shared, unique_russian])), \
         patch.object(source_module, "classify_contacts", capture_classify):
        await source_contacts({"title": "E", "company": "Acme",
                                "companyUrl": "https://www.linkedin.com/company/acme/",
                                "contacts": []}, settings=dual_settings)

    urls = [
        i.get("linkedinUrl") or i.get("linkedInUrl") or i.get("profileUrl") or i.get("url")
        for i in captured.get("items", [])
    ]
    assert urls.count("/in/shared") == 1
    assert "/in/ivan" in urls


# ─── Cap enforcement with dual audience ───────────────────────────────────────

@pytest.mark.asyncio
async def test_dual_audience_cap_3_recruiters():
    """Classifier with both toggles on keeps at most 3 Recruiters."""
    from src.core.enrichment.classifier import classify_contacts
    import src.core.gemini_client as gemini_mod

    items = [
        {"firstName": f"HR{i}", "lastName": "P", "headline": "Recruiter",
         "linkedinUrl": f"/in/hr{i}", "currentPosition": "", "location": ""}
        for i in range(5)
    ]
    classified_raw = [{"index": i, "russian_speaker": False, "is_recruiter": True} for i in range(5)]
    settings = OutreachSettings(target_recruiters=True, target_russian_speakers=True)

    with patch("src.core.enrichment.classifier.os.getenv", return_value="fake-key"), \
         patch.object(gemini_mod, "generate_text",
                      new=AsyncMock(return_value=json.dumps(classified_raw))):
        result = await classify_contacts(items, settings)

    assert len(result) == 3
    assert all(c["is_recruiter"] for c in result)


@pytest.mark.asyncio
async def test_dual_audience_cap_5_non_hr_russian():
    """Classifier with both toggles on keeps at most 5 non-HR Russian Speakers."""
    from src.core.enrichment.classifier import classify_contacts
    import src.core.gemini_client as gemini_mod

    items = [
        {"firstName": f"RU{i}", "lastName": "P", "headline": "Engineer",
         "linkedinUrl": f"/in/ru{i}", "currentPosition": "", "location": "Moscow"}
        for i in range(7)
    ]
    classified_raw = [{"index": i, "russian_speaker": True, "is_recruiter": False} for i in range(7)]
    settings = OutreachSettings(target_recruiters=True, target_russian_speakers=True)

    with patch("src.core.enrichment.classifier.os.getenv", return_value="fake-key"), \
         patch.object(gemini_mod, "generate_text",
                      new=AsyncMock(return_value=json.dumps(classified_raw))):
        result = await classify_contacts(items, settings)

    assert len(result) == 5
    assert all(c["russian_speaker"] for c in result)
    assert not any(c["is_recruiter"] for c in result)


@pytest.mark.asyncio
async def test_dual_audience_dual_classified_counts_toward_recruiter_cap():
    """A dual-classified contact (both russian_speaker=True, is_recruiter=True) counts toward
    the Recruiter cap only; the Russian Speaker count is unaffected."""
    from src.core.enrichment.classifier import classify_contacts
    import src.core.gemini_client as gemini_mod

    # 1 dual-classified + 5 pure Russian speakers
    items = [
        {"firstName": "Dual", "headline": "HR Russian", "linkedinUrl": "/in/dual",
         "currentPosition": "", "location": "Moscow"},
    ] + [
        {"firstName": f"RU{i}", "headline": "Engineer", "linkedinUrl": f"/in/ru{i}",
         "currentPosition": "", "location": "Moscow"}
        for i in range(5)
    ]
    classified_raw = [
        {"index": 0, "russian_speaker": True, "is_recruiter": True},
    ] + [
        {"index": i + 1, "russian_speaker": True, "is_recruiter": False}
        for i in range(5)
    ]
    settings = OutreachSettings(target_recruiters=True, target_russian_speakers=True)

    with patch("src.core.enrichment.classifier.os.getenv", return_value="fake-key"), \
         patch.object(gemini_mod, "generate_text",
                      new=AsyncMock(return_value=json.dumps(classified_raw))):
        result = await classify_contacts(items, settings)

    recruiters = [c for c in result if c["is_recruiter"]]
    russians = [c for c in result if c["russian_speaker"] and not c["is_recruiter"]]
    # Dual contact counted as recruiter → only 1 recruiter total (cap=3, only 1 dual)
    assert len(recruiters) == 1
    assert recruiters[0]["russian_speaker"] is True
    # Russian pool (non-recruiter) gets up to 5
    assert len(russians) == 5


@pytest.mark.asyncio
async def test_dual_audience_dual_classified_appears_once_in_output():
    """A dual-classified contact appears exactly once in the result list."""
    from src.core.enrichment.classifier import classify_contacts
    import src.core.gemini_client as gemini_mod

    items = [
        {"firstName": "Dual", "headline": "HR Russian", "linkedinUrl": "/in/dual",
         "currentPosition": "", "location": "Moscow"},
    ]
    classified_raw = [{"index": 0, "russian_speaker": True, "is_recruiter": True}]
    settings = OutreachSettings(target_recruiters=True, target_russian_speakers=True)

    with patch("src.core.enrichment.classifier.os.getenv", return_value="fake-key"), \
         patch.object(gemini_mod, "generate_text",
                      new=AsyncMock(return_value=json.dumps(classified_raw))):
        result = await classify_contacts(items, settings)

    assert len(result) == 1
    assert result[0]["is_recruiter"] is True
    assert result[0]["russian_speaker"] is True
