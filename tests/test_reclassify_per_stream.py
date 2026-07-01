"""Tests for per-stream cache behavior in run_reclassify_pipeline (issue #76)."""
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.db.connection as _db_connection
from src import db as database


@pytest.fixture
def db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test.db")
    monkeypatch.setattr(_db_connection, "DB_PATH", test_db)
    database.init_db(test_db)
    return test_db


def _make_accepted_job(db):
    from src.core.enrichment.coordinator import begin_enrichment
    from src.db.jobs import add_job, enrich_job
    job_id = add_job({
        "title": "QA Engineer",
        "company": "Acme",
        "companyUrl": "https://www.linkedin.com/company/acme/",
        "status": "scraped",
    }, db_path=db)
    begin_enrichment(job_id, db)
    enrich_job(
        job_id,
        contacts=[{"name": "Alice", "title": "Recruiter", "url": "https://linkedin.com/in/alice",
                   "contacted": False, "russian_speaker": False, "is_recruiter": True}],
        outreach_message="Hello",
        db_path=db,
    )
    return job_id


# --- Per-stream cache hits: no Apify calls ---

@pytest.mark.asyncio
async def test_reclassify_recruiter_stream_cache_hit_no_apify(db):
    """Re-classify with recruiter-only settings + cached recruiters stream → no Apify."""
    from src.core.enrichment.contact_sample import company_cache_slug
    from src.db.cache import set_contact_sample
    from src.db.settings import save_outreach_settings
    from src.pipelines import run_reclassify_pipeline

    job_id = _make_accepted_job(db)
    slug = company_cache_slug("Acme", "https://www.linkedin.com/company/acme/")
    set_contact_sample(
        slug,
        [{"firstName": "Bob", "linkedinUrl": "https://linkedin.com/in/bob", "headline": "HR Manager"}],
        stream="recruiters",
        db_path=db,
    )
    save_outreach_settings(target_russian_speakers=False, target_recruiters=True, db_path=db)

    classified = [{"name": "Bob Smith", "title": "HR Manager", "url": "https://linkedin.com/in/bob",
                   "contacted": False, "russian_speaker": False, "is_recruiter": True}]
    templates = {"recruiter": "Hello Bob,", "russian_speaker": ""}

    with patch("src.core.enrichment.source.classify_contacts", new=AsyncMock(return_value=classified)), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=templates)), \
         patch("src.core.enrichment.contact_sample._run_apify_for_recruiters") as mock_rec, \
         patch("src.core.enrichment.contact_sample._run_apify_for_russian_speakers") as mock_rus:
        updated = await run_reclassify_pipeline(job_id)

    mock_rec.assert_not_called()
    mock_rus.assert_not_called()
    assert updated.id == job_id
    assert len(updated.contacts) == 1
    assert updated.contacts[0].name == "Bob Smith"


@pytest.mark.asyncio
async def test_reclassify_russian_stream_cache_hit_no_apify(db):
    """Re-classify with russian-only settings + cached russian stream → no Apify."""
    from src.core.enrichment.contact_sample import company_cache_slug
    from src.db.cache import set_contact_sample
    from src.db.settings import save_outreach_settings
    from src.pipelines import run_reclassify_pipeline

    job_id = _make_accepted_job(db)
    slug = company_cache_slug("Acme", "https://www.linkedin.com/company/acme/")
    set_contact_sample(
        slug,
        [{"firstName": "Ivan", "linkedinUrl": "https://linkedin.com/in/ivan", "headline": "Engineer",
          "languages": ["Russian"]}],
        stream="russian",
        db_path=db,
    )
    save_outreach_settings(target_russian_speakers=True, target_recruiters=False, db_path=db)

    classified = [{"name": "Ivan Petrov", "title": "Engineer", "url": "https://linkedin.com/in/ivan",
                   "contacted": False, "russian_speaker": True, "is_recruiter": False}]
    templates = {"recruiter": "", "russian_speaker": "Привет Ivan,"}

    with patch("src.core.enrichment.source.classify_contacts", new=AsyncMock(return_value=classified)), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=templates)), \
         patch("src.core.enrichment.contact_sample._run_apify_for_recruiters") as mock_rec, \
         patch("src.core.enrichment.contact_sample._run_apify_for_russian_speakers") as mock_rus:
        updated = await run_reclassify_pipeline(job_id)

    mock_rec.assert_not_called()
    mock_rus.assert_not_called()
    assert len(updated.contacts) == 1
    assert updated.contacts[0].name == "Ivan Petrov"


@pytest.mark.asyncio
async def test_reclassify_dual_audience_both_caches_no_apify(db):
    """Re-classify with both toggles on + both stream caches present → no Apify."""
    from src.core.enrichment.contact_sample import company_cache_slug
    from src.db.cache import set_contact_sample
    from src.db.settings import save_outreach_settings
    from src.pipelines import run_reclassify_pipeline

    job_id = _make_accepted_job(db)
    slug = company_cache_slug("Acme", "https://www.linkedin.com/company/acme/")
    set_contact_sample(
        slug,
        [{"firstName": "Bob", "linkedinUrl": "https://linkedin.com/in/bob", "headline": "HR"}],
        stream="recruiters",
        db_path=db,
    )
    set_contact_sample(
        slug,
        [{"firstName": "Ivan", "linkedinUrl": "https://linkedin.com/in/ivan", "headline": "Engineer"}],
        stream="russian",
        db_path=db,
    )
    save_outreach_settings(target_russian_speakers=True, target_recruiters=True, db_path=db)

    classified = [
        {"name": "Bob Smith", "title": "HR", "url": "https://linkedin.com/in/bob",
         "contacted": False, "russian_speaker": False, "is_recruiter": True},
        {"name": "Ivan Petrov", "title": "Engineer", "url": "https://linkedin.com/in/ivan",
         "contacted": False, "russian_speaker": True, "is_recruiter": False},
    ]
    templates = {"recruiter": "Hello Bob,", "russian_speaker": "Привет Ivan,"}

    with patch("src.core.enrichment.source.classify_contacts", new=AsyncMock(return_value=classified)), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=templates)), \
         patch("src.core.enrichment.contact_sample._run_apify_for_recruiters") as mock_rec, \
         patch("src.core.enrichment.contact_sample._run_apify_for_russian_speakers") as mock_rus:
        updated = await run_reclassify_pipeline(job_id)

    mock_rec.assert_not_called()
    mock_rus.assert_not_called()
    assert len(updated.contacts) == 2


@pytest.mark.asyncio
async def test_reclassify_recruiter_settings_no_recruiter_cache_template_only(db):
    """Re-classify with recruiter-only settings + no cached recruiters stream → template-only."""
    from src.db.settings import save_outreach_settings
    from src.pipelines import run_reclassify_pipeline

    job_id = _make_accepted_job(db)
    save_outreach_settings(target_russian_speakers=False, target_recruiters=True, db_path=db)

    templates = {"recruiter": "Hello ______,", "russian_speaker": ""}

    with patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=templates)), \
         patch("src.core.enrichment.contact_sample._run_apify_for_recruiters") as mock_rec:
        updated = await run_reclassify_pipeline(job_id)

    mock_rec.assert_not_called()
    # Template-only: existing contacts preserved
    assert len(updated.contacts) == 1
    assert updated.contacts[0].name == "Alice"
    assert "templates refreshed" in updated.enrichmentNote


@pytest.mark.asyncio
async def test_reclassify_both_toggles_off_uses_legacy_stream_cache(db):
    """Re-classify with both toggles off uses legacy stream='' cache for cache check."""
    from src.core.enrichment.contact_sample import company_cache_slug
    from src.db.cache import set_contact_sample
    from src.db.settings import save_outreach_settings
    from src.pipelines import run_reclassify_pipeline

    job_id = _make_accepted_job(db)
    slug = company_cache_slug("Acme", "https://www.linkedin.com/company/acme/")
    set_contact_sample(
        slug,
        [{"firstName": "Alice", "linkedinUrl": "https://linkedin.com/in/alice", "headline": "Recruiter"}],
        stream="",
        db_path=db,
    )
    save_outreach_settings(target_russian_speakers=False, target_recruiters=False, db_path=db)

    classified = [{"name": "Alice Smith", "title": "Recruiter", "url": "https://linkedin.com/in/alice",
                   "contacted": False, "russian_speaker": False, "is_recruiter": True}]
    templates = {"recruiter": "Hello Alice,", "russian_speaker": ""}

    with patch("src.core.enrichment.source.classify_contacts", new=AsyncMock(return_value=classified)), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=templates)), \
         patch("src.core.enrichment.contact_sample._run_apify_actor") as mock_apify:
        updated = await run_reclassify_pipeline(job_id)

    mock_apify.assert_not_called()
    assert updated.contacts[0].name == "Alice Smith"
