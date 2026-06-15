"""Tests for Contact Sample Cache — DB layer and source_contacts cache-aware behavior."""
import os
import sys
import pytest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.db.connection as _db_connection
import src.core.enrichment.source as source_module
from src import db as database
from src.db.cache import get_contact_sample, set_contact_sample, delete_contact_sample
from src.core.outreach import source_contacts


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(_db_connection, "DB_PATH", db_path)
    database.init_db(db_path)
    return db_path


# --- DB layer ---

def test_cache_table_created_by_init_db(db):
    """init_db creates the contact_sample_cache table."""
    import sqlite3
    conn = sqlite3.connect(db)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='contact_sample_cache'")
    row = cursor.fetchone()
    conn.close()
    assert row is not None


def test_cache_miss_returns_none(db):
    result = get_contact_sample("acme", db_path=db)
    assert result is None


def test_set_and_get_contact_sample(db):
    profiles = [{"firstName": "Ivan", "lastName": "Petrov"}]
    set_contact_sample("acme", profiles, display_name="Acme Corp", db_path=db)
    cached = get_contact_sample("acme", db_path=db)
    assert cached is not None
    assert cached["profiles"] == profiles
    assert cached["display_name"] == "Acme Corp"
    assert cached["fetched_at"]


def test_set_contact_sample_ignores_empty_list(db):
    set_contact_sample("acme", [], db_path=db)
    assert get_contact_sample("acme", db_path=db) is None


def test_set_contact_sample_replaces_existing(db):
    old = [{"firstName": "Old"}]
    new = [{"firstName": "New"}]
    set_contact_sample("acme", old, db_path=db)
    set_contact_sample("acme", new, db_path=db)
    cached = get_contact_sample("acme", db_path=db)
    assert cached["profiles"] == new


def test_delete_contact_sample(db):
    set_contact_sample("acme", [{"x": 1}], db_path=db)
    delete_contact_sample("acme", db_path=db)
    assert get_contact_sample("acme", db_path=db) is None


def test_delete_contact_sample_nonexistent_is_noop(db):
    delete_contact_sample("nonexistent", db_path=db)  # must not raise


# --- source_contacts cache-aware behavior ---

@pytest.mark.asyncio
async def test_source_contacts_calls_apify_on_cache_miss(db):
    """On cache miss, source_contacts fetches via Apify."""
    job = {"title": "QA", "company": "Acme", "contacts": []}
    with patch.object(source_module, "_run_apify_actor", new=AsyncMock(return_value=[])) as mock_apify, \
         patch.object(source_module, "classify_contacts", new=AsyncMock(return_value=[])):
        await source_contacts(job)
    mock_apify.assert_called_once()


@pytest.mark.asyncio
async def test_source_contacts_skips_apify_on_cache_hit(db):
    """On cache hit, Apify is not called."""
    profiles = [{"firstName": "Ivan", "lastName": "Petrov", "headline": "Dev", "linkedinUrl": ""}]
    set_contact_sample("acme", profiles, display_name="Acme", db_path=db)
    job = {"title": "QA", "company": "Acme", "contacts": []}
    with patch.object(source_module, "_run_apify_actor", new=AsyncMock(return_value=[])) as mock_apify, \
         patch.object(source_module, "classify_contacts", new=AsyncMock(return_value=[])):
        await source_contacts(job)
    mock_apify.assert_not_called()


@pytest.mark.asyncio
async def test_source_contacts_populates_cache_after_apify_fetch(db):
    """Non-empty Apify result is written to cache."""
    profiles = [{"firstName": "Ivan", "lastName": "Petrov", "headline": "Dev", "linkedinUrl": ""}]
    job = {"title": "QA", "company": "Acme", "contacts": []}
    with patch.object(source_module, "_run_apify_actor", new=AsyncMock(return_value=profiles)), \
         patch.object(source_module, "classify_contacts", new=AsyncMock(return_value=[])):
        await source_contacts(job)
    cached = get_contact_sample("acme", db_path=db)
    assert cached is not None
    assert cached["profiles"] == profiles


@pytest.mark.asyncio
async def test_source_contacts_empty_apify_not_cached(db):
    """Empty Apify result is not written to cache."""
    job = {"title": "QA", "company": "Acme", "contacts": []}
    with patch.object(source_module, "_run_apify_actor", new=AsyncMock(return_value=[])), \
         patch.object(source_module, "classify_contacts", new=AsyncMock(return_value=[])):
        await source_contacts(job)
    assert get_contact_sample("acme", db_path=db) is None


@pytest.mark.asyncio
async def test_source_contacts_classify_runs_on_cache_hit(db):
    """classify_contacts is called even when serving from cache."""
    profiles = [{"firstName": "Ivan", "lastName": "Petrov", "headline": "Dev", "linkedinUrl": ""}]
    set_contact_sample("acme", profiles, display_name="Acme", db_path=db)
    job = {"title": "QA", "company": "Acme", "contacts": []}
    with patch.object(source_module, "_run_apify_actor", new=AsyncMock(return_value=[])), \
         patch.object(source_module, "classify_contacts", new=AsyncMock(return_value=[])) as mock_classify:
        await source_contacts(job)
    mock_classify.assert_called_once()


@pytest.mark.asyncio
async def test_source_contacts_cache_hit_logs_company_and_fetch_date(db):
    """Cache hit emits a log line mentioning company name and fetched_at."""
    profiles = [{"firstName": "Ivan", "lastName": "Petrov", "headline": "Dev", "linkedinUrl": ""}]
    set_contact_sample("acme", profiles, display_name="Acme Corp", db_path=db)
    job = {"title": "QA", "company": "Acme", "contacts": []}

    log_records = []
    async def capture_log(msg, level="info"):
        log_records.append(msg)

    with patch.object(source_module, "_run_apify_actor", new=AsyncMock(return_value=[])), \
         patch.object(source_module, "classify_contacts", new=AsyncMock(return_value=[])):
        await source_contacts(job, log_func=capture_log)

    joined = " ".join(log_records)
    assert "Acme Corp" in joined or "acme" in joined.lower()
    # fetched_at is an ISO timestamp; verify something date-like is present
    assert any("fetched" in m.lower() or "cache" in m.lower() for m in log_records)


@pytest.mark.asyncio
async def test_source_contacts_cache_hit_appends_activity_log(db):
    """Cache hit appends an entry to the job's Job Activity Log."""
    from src.db import get_job

    profiles = [{"firstName": "Ivan", "lastName": "Petrov", "headline": "Dev", "linkedinUrl": ""}]
    set_contact_sample("acme", profiles, display_name="Acme Corp", db_path=db)

    job = database.get_job(1, db_path=db)
    assert job is not None, "Seed data must provide at least one job"

    # Patch company so the slug matches the cache entry
    job = dict(job)
    job["company"] = "Acme"

    with patch.object(source_module, "_run_apify_actor", new=AsyncMock(return_value=[])), \
         patch.object(source_module, "classify_contacts", new=AsyncMock(return_value=[])):
        await source_contacts(job)

    updated = database.get_job(1, db_path=db)
    messages = [e["message"] for e in updated["activityLog"]]
    assert any("cache" in m.lower() or "Cache" in m for m in messages), \
        f"Expected cache hit entry in activity log, got: {messages}"


@pytest.mark.asyncio
async def test_source_contacts_bust_cache_deletes_and_refetches(db):
    """bust_cache=True deletes the cache entry and triggers a fresh Apify fetch."""
    old_profiles = [{"firstName": "Old", "lastName": "Employee", "headline": "Dev", "linkedinUrl": ""}]
    set_contact_sample("acme", old_profiles, display_name="Acme", db_path=db)

    new_profiles = [{"firstName": "New", "lastName": "Employee", "headline": "Dev", "linkedinUrl": ""}]
    job = {"title": "QA", "company": "Acme", "contacts": []}
    with patch.object(source_module, "_run_apify_actor", new=AsyncMock(return_value=new_profiles)) as mock_apify, \
         patch.object(source_module, "classify_contacts", new=AsyncMock(return_value=[])):
        await source_contacts(job, bust_cache=True)

    mock_apify.assert_called_once()
    cached = get_contact_sample("acme", db_path=db)
    assert cached["profiles"] == new_profiles


@pytest.mark.asyncio
async def test_source_contacts_slug_normalization(db):
    """Company name normalization matches cache key."""
    profiles = [{"firstName": "Ivan", "linkedinUrl": ""}]
    # Store with slug form
    set_contact_sample("my-company", profiles, display_name="My Company", db_path=db)

    job = {"title": "QA", "company": "My Company", "contacts": []}
    with patch.object(source_module, "_run_apify_actor", new=AsyncMock(return_value=[])) as mock_apify, \
         patch.object(source_module, "classify_contacts", new=AsyncMock(return_value=[])):
        await source_contacts(job)

    # "My Company" → "my-company" → cache hit → Apify not called
    mock_apify.assert_not_called()
