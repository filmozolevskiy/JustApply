"""Tests for Issue #58: Found/Accepted lanes with status migration.

Covers:
- DB migration maps sourced→found and enriching/enriched→accepted on upgrade
- VALID_STATUSES only includes new pipeline values
- update_job_status rejects obsolete statuses
- update_job_status accepts found/accepted
- Seed data uses 'found' not 'sourced'
- PUT /api/jobs/{id}/status rejects obsolete statuses
- Kanban lanes: Found and Accepted present; Sourced/Enriching/Enriched absent
- Lane drag does not trigger enrichment (no enriching-lane hook in JS)
"""

import os
import sys
import sqlite3

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db import init_db, add_job, get_jobs, get_job, update_job_status, VALID_STATUSES

HTML_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")


def _read_html():
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        return f.read()


# ── Status enum ──────────────────────────────────────────────────────────────

def test_valid_statuses_contains_found_and_accepted():
    assert "found" in VALID_STATUSES
    assert "accepted" in VALID_STATUSES


def test_valid_statuses_excludes_legacy_values():
    assert "sourced" not in VALID_STATUSES
    assert "enriching" not in VALID_STATUSES
    assert "enriched" not in VALID_STATUSES


def test_update_job_status_rejects_sourced(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    with pytest.raises(ValueError, match="Invalid status"):
        update_job_status(1, "sourced", db_str)


def test_update_job_status_rejects_enriching(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    with pytest.raises(ValueError, match="Invalid status"):
        update_job_status(1, "enriching", db_str)


def test_update_job_status_rejects_enriched(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    with pytest.raises(ValueError, match="Invalid status"):
        update_job_status(1, "enriched", db_str)


def test_update_job_status_accepts_found(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    updated = update_job_status(job_id, "found", db_str)
    assert updated is not None
    assert updated.status == "found"


def test_update_job_status_accepts_accepted(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    job_id = add_job({"title": "QA", "company": "Acme"}, db_str)
    updated = update_job_status(job_id, "accepted", db_str)
    assert updated is not None
    assert updated.status == "accepted"


# ── Seed data ────────────────────────────────────────────────────────────────

def test_seed_jobs_use_found_status(tmp_path):
    db_str = str(tmp_path / "test.db")
    init_db(db_str)
    jobs = get_jobs(db_str)
    found_or_other = [j for j in jobs if j.status in ("found", "contacted", "interviewing", "rejected", "accepted")]
    assert len(found_or_other) == len(jobs), (
        f"All seeded jobs must use new statuses; got {[j.status for j in jobs]}"
    )


# ── DB migration ─────────────────────────────────────────────────────────────

def test_migration_sourced_to_found(tmp_path):
    """init_db upgrades existing 'sourced' rows to 'found'."""
    db_path = str(tmp_path / "migrate.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '',
            company TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'sourced'
        )
    """)
    conn.execute("INSERT INTO jobs (title, company, status) VALUES ('Job A', 'Co A', 'sourced')")
    conn.execute("INSERT INTO jobs (title, company, status) VALUES ('Job B', 'Co B', 'sourced')")
    conn.commit()
    conn.close()

    init_db(db_path)

    conn2 = sqlite3.connect(db_path)
    rows = conn2.execute("SELECT status FROM jobs ORDER BY id").fetchall()
    conn2.close()
    assert all(r[0] == "found" for r in rows), f"Expected all 'found', got {rows}"


def test_migration_enriching_and_enriched_to_accepted(tmp_path):
    """init_db upgrades 'enriching' and 'enriched' rows to 'accepted'."""
    db_path = str(tmp_path / "migrate2.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '',
            company TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'sourced'
        )
    """)
    conn.execute("INSERT INTO jobs (title, company, status) VALUES ('Job C', 'Co C', 'enriching')")
    conn.execute("INSERT INTO jobs (title, company, status) VALUES ('Job D', 'Co D', 'enriched')")
    conn.execute("INSERT INTO jobs (title, company, status) VALUES ('Job E', 'Co E', 'contacted')")
    conn.commit()
    conn.close()

    init_db(db_path)

    conn2 = sqlite3.connect(db_path)
    rows = {r[0]: r[1] for r in conn2.execute("SELECT title, status FROM jobs").fetchall()}
    conn2.close()
    assert rows["Job C"] == "accepted"
    assert rows["Job D"] == "accepted"
    assert rows["Job E"] == "contacted"


# ── Dashboard HTML: lanes ────────────────────────────────────────────────────

def test_kanban_has_found_lane():
    content = _read_html()
    assert 'data-lane="found"' in content, "Kanban must have a Found lane"


def test_kanban_has_accepted_lane():
    content = _read_html()
    assert 'data-lane="accepted"' in content, "Kanban must have an Accepted lane"


def test_kanban_no_sourced_lane():
    content = _read_html()
    assert 'data-lane="sourced"' not in content, "Sourced lane must be removed"


def test_kanban_no_enriching_lane():
    content = _read_html()
    assert 'data-lane="enriching"' not in content, "Enriching lane must be removed"


def test_kanban_no_enriched_lane():
    content = _read_html()
    assert 'data-lane="enriched"' not in content, "Enriched lane must be removed"


def test_drag_does_not_trigger_enrichment():
    """Lane drop must never call enrichJob — drag is status-only."""
    content = _read_html()
    # The old enriching-lane hook that called enrich must be gone
    assert "newStatus === 'enriching'" not in content, (
        "Drag must not route to enrichJob via enriching status check"
    )
