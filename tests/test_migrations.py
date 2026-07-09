"""Tests for versioned Job Tracker Database migrations (PRD #113 / issue #147)."""

import sqlite3

from src.db import add_job, get_jobs, init_db
from src.db import batch_jobs as batch_jobs_module
from src.db.connection import get_db_connection
from src.db.migrations import CURRENT_SCHEMA_VERSION, get_schema_version, run_migrations


def test_fresh_db_has_current_schema_version(tmp_path):
    db_path = str(tmp_path / "fresh.db")
    init_db(db_path)
    conn = get_db_connection(db_path)
    try:
        assert get_schema_version(conn) == CURRENT_SCHEMA_VERSION
    finally:
        conn.close()

def test_schema_version_unchanged_on_second_init(tmp_path):
    db_path = str(tmp_path / "fresh.db")
    init_db(db_path)
    conn = get_db_connection(db_path)
    try:
        version_after_first = get_schema_version(conn)
    finally:
        conn.close()

    init_db(db_path)
    conn = get_db_connection(db_path)
    try:
        assert get_schema_version(conn) == version_after_first == CURRENT_SCHEMA_VERSION
    finally:
        conn.close()

def test_legacy_minimal_jobs_schema_upgrades_in_place(tmp_path):
    """Legacy fixture with only core jobs columns reaches current schema."""
    db_path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '',
            company TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'found',
            matchType TEXT DEFAULT ''
        )
        """
    )
    conn.execute(
        "INSERT INTO jobs (title, company, status, matchType) VALUES ('Legacy', 'Co', 'found', '')"
    )
    conn.commit()
    conn.close()

    init_db(db_path)

    conn2 = get_db_connection(db_path)
    try:
        assert get_schema_version(conn2) == CURRENT_SCHEMA_VERSION
        cols = {row[1] for row in conn2.execute("PRAGMA table_info(jobs)")}
        assert "archived" in cols
        assert "rejectedAt" in cols
        assert "companyResearch" in cols
        tables = {
            row[0]
            for row in conn2.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "batch_jobs" in tables
        assert "contact_sample_cache" in tables
        assert "company_research_cache" in tables
    finally:
        conn2.close()

    job = get_jobs(db_path)[0]
    assert job.title == "Legacy"
    assert job.status == "scraped"

def test_legacy_populated_db_preserves_job_data(tmp_path):
    db_path = str(tmp_path / "populated.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'accepted',
            contacts TEXT DEFAULT '[]',
            matchType TEXT DEFAULT 'full_match'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE contact_sample_cache (
            company_slug TEXT PRIMARY KEY,
            profiles TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            pages_fetched INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        INSERT INTO contact_sample_cache
            (company_slug, profiles, fetched_at, display_name, pages_fetched)
        VALUES ('acme', '[{"firstName":"Ada"}]', '2026-01-01', 'Acme', 2)
        """
    )
    conn.execute(
        "INSERT INTO jobs (title, company, status, contacts) VALUES ('PM', 'Acme', 'accepted', '[]')"
    )
    conn.commit()
    conn.close()

    init_db(db_path)

    jobs = get_jobs(db_path)
    assert len(jobs) == 1
    assert jobs[0].title == "PM"
    assert jobs[0].status == "accepted"

    conn2 = get_db_connection(db_path)
    try:
        row = conn2.execute(
            "SELECT company_slug, stream, profiles FROM contact_sample_cache WHERE company_slug='acme'"
        ).fetchone()
        assert row is not None
        assert row["stream"] == ""
        assert "Ada" in row["profiles"]
    finally:
        conn2.close()

def test_legacy_db_gets_batch_jobs_table_for_poller(tmp_path):
    db_path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'scraped'
        )
        """
    )
    conn.commit()
    conn.close()

    init_db(db_path)
    job_id = add_job({"title": "QA", "company": "Beta"}, db_path)
    row = batch_jobs_module.create_batch_job(
        batch_name="batches/test",
        display_name="test-batch",
        state="JOB_STATE_PENDING",
        kind="search",
        job_ids=[job_id],
        db_path=db_path,
    )
    assert row["jobIds"] == [job_id]

def test_run_migrations_is_idempotent(tmp_path):
    db_path = str(tmp_path / "manual.db")
    conn = get_db_connection(db_path)
    try:
        run_migrations(conn)
        version = get_schema_version(conn)
        run_migrations(conn)
        assert get_schema_version(conn) == version == CURRENT_SCHEMA_VERSION
    finally:
        conn.close()
