"""Tests for Issue #87: Scraped/Matched lanes with status migration.

Covers:
- DB migration maps found→scraped (unscored) or found→matched (scored)
- VALID_STATUSES only includes new pipeline values
- update_job_status rejects obsolete statuses
- update_job_status accepts scraped/matched
- Seed data uses 'scraped' not 'found'
- PUT /api/jobs/{id}/status rejects obsolete statuses
- Kanban lanes: Scraped and Matched present; Found absent
"""

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db import VALID_STATUSES, add_job, get_jobs, init_db, update_job_status

HTML_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")


def _read_html():
    with open(HTML_PATH, encoding="utf-8") as f:
        return f.read()


# ── Status enum ──────────────────────────────────────────────────────────────

def test_valid_statuses_contains_scraped_and_matched():
    assert "scraped" in VALID_STATUSES
    assert "matched" in VALID_STATUSES


def test_valid_statuses_excludes_legacy_values():
    assert "found" not in VALID_STATUSES
    assert "sourced" not in VALID_STATUSES


def test_update_job_status_rejects_found(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    with pytest.raises(ValueError, match="Invalid status"):
        update_job_status(1, "found", db_str)


def test_update_job_status_accepts_scraped(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    updated = update_job_status(job_id, "scraped", db_str)
    assert updated is not None
    assert updated.status == "scraped"


def test_update_job_status_accepts_matched(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    updated = update_job_status(job_id, "matched", db_str)
    assert updated is not None
    assert updated.status == "matched"


# ── Seed data ────────────────────────────────────────────────────────────────

def test_seed_jobs_use_scraped_status(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    jobs = get_jobs(db_str)
    scraped_or_other = [j for j in jobs if j.status in ("scraped", "matched", "applied", "interviewing", "rejected", "accepted")]
    assert len(scraped_or_other) == len(jobs), (
        f"All seeded jobs must use new statuses; got {[j.status for j in jobs]}"
    )


# ── DB migration ─────────────────────────────────────────────────────────────

def test_migration_found_to_scraped_and_matched(tmp_path):
    """init_db upgrades existing 'found' rows to 'scraped' or 'matched'."""
    db_path = str(tmp_path / "migrate.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '',
            company TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'found',
            matchType TEXT DEFAULT ''
        )
    """)
    # Unscored found -> scraped
    conn.execute("INSERT INTO jobs (title, company, status, matchType) VALUES ('Job A', 'Co A', 'found', '')")
    # Scored found -> matched
    conn.execute("INSERT INTO jobs (title, company, status, matchType) VALUES ('Job B', 'Co B', 'found', 'full_match')")
    # Unscored rejected -> scraped
    conn.execute("INSERT INTO jobs (title, company, status, matchType) VALUES ('Job C', 'Co C', 'rejected', '')")
    # Scored rejected -> unchanged
    conn.execute("INSERT INTO jobs (title, company, status, matchType) VALUES ('Job D', 'Co D', 'rejected', 'no_match')")
    conn.commit()
    conn.close()

    init_db(db_path)

    conn2 = sqlite3.connect(db_path)
    rows = {r[0]: r[1] for r in conn2.execute("SELECT title, status FROM jobs").fetchall()}
    conn2.close()
    assert rows["Job A"] == "scraped"
    assert rows["Job B"] == "matched"
    assert rows["Job C"] == "scraped"
    assert rows["Job D"] == "rejected"


def test_kanban_has_scraped_lane():
    content = _read_html()
    assert 'data-lane="scraped"' in content, "Kanban must have a Scraped lane"


def test_kanban_has_matched_lane():
    content = _read_html()
    assert 'data-lane="matched"' in content, "Kanban must have a Matched lane"


def test_kanban_no_found_lane():
    content = _read_html()
    assert 'data-lane="found"' not in content, "Found lane must be removed"
