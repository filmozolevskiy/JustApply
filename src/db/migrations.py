"""Versioned schema migrations for the Job Tracker Database.

Schema version is stored in SQLite ``PRAGMA user_version``. On ``init_db``,
``run_migrations`` applies numbered steps from ``current_version + 1`` through
``CURRENT_SCHEMA_VERSION``, bumping ``user_version`` after each step.

Adding the next migration:
1. Increment ``CURRENT_SCHEMA_VERSION``.
2. Add ``_migration_NNN_<short_name>`` with idempotent DDL (check columns/tables
   before ``ALTER``/``CREATE``).
3. Register it in ``_MIGRATIONS``.
4. Extend ``tests/test_migrations.py`` if the change needs upgrade coverage.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

CURRENT_SCHEMA_VERSION = 15

MigrationFn = Callable[[sqlite3.Connection], None]


def get_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    ddl: str,
) -> None:
    if column in _table_columns(conn, table):
        return
    conn.execute(ddl)
    conn.commit()


def _migration_001_create_jobs_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            size TEXT,
            link TEXT,
            date TEXT,
            location TEXT,
            remoteType TEXT,
            seniority TEXT,
            salary TEXT,
            description TEXT,
            matchScore INTEGER,
            matchType TEXT,
            shouldProceed INTEGER DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'scraped',
            resumeUsed TEXT,
            strengths TEXT,
            gaps TEXT,
            contacts TEXT,
            outreachMessage TEXT,
            comment TEXT,
            isRecruiter INTEGER DEFAULT 0,
            enrichmentNote TEXT DEFAULT '',
            recruiterOutreachTemplate TEXT DEFAULT '',
            russianSpeakerOutreachTemplate TEXT DEFAULT ''
        )
        """
    )
    conn.commit()


_JOBS_COLUMN_DDLS: tuple[tuple[str, str], ...] = (
    ("size", "ALTER TABLE jobs ADD COLUMN size TEXT DEFAULT ''"),
    ("link", "ALTER TABLE jobs ADD COLUMN link TEXT DEFAULT ''"),
    ("date", "ALTER TABLE jobs ADD COLUMN date TEXT DEFAULT ''"),
    ("location", "ALTER TABLE jobs ADD COLUMN location TEXT DEFAULT ''"),
    ("remoteType", "ALTER TABLE jobs ADD COLUMN remoteType TEXT DEFAULT ''"),
    ("seniority", "ALTER TABLE jobs ADD COLUMN seniority TEXT DEFAULT ''"),
    ("salary", "ALTER TABLE jobs ADD COLUMN salary TEXT DEFAULT ''"),
    ("description", "ALTER TABLE jobs ADD COLUMN description TEXT DEFAULT ''"),
    ("matchScore", "ALTER TABLE jobs ADD COLUMN matchScore INTEGER DEFAULT 0"),
    ("matchType", "ALTER TABLE jobs ADD COLUMN matchType TEXT DEFAULT ''"),
    ("shouldProceed", "ALTER TABLE jobs ADD COLUMN shouldProceed INTEGER DEFAULT 0"),
    ("resumeUsed", "ALTER TABLE jobs ADD COLUMN resumeUsed TEXT DEFAULT ''"),
    ("strengths", "ALTER TABLE jobs ADD COLUMN strengths TEXT DEFAULT '[]'"),
    ("gaps", "ALTER TABLE jobs ADD COLUMN gaps TEXT DEFAULT '[]'"),
    ("contacts", "ALTER TABLE jobs ADD COLUMN contacts TEXT DEFAULT '[]'"),
    ("outreachMessage", "ALTER TABLE jobs ADD COLUMN outreachMessage TEXT DEFAULT ''"),
    ("comment", "ALTER TABLE jobs ADD COLUMN comment TEXT DEFAULT ''"),
    ("isRecruiter", "ALTER TABLE jobs ADD COLUMN isRecruiter INTEGER DEFAULT 0"),
    ("enrichmentNote", "ALTER TABLE jobs ADD COLUMN enrichmentNote TEXT DEFAULT ''"),
    (
        "recruiterOutreachTemplate",
        "ALTER TABLE jobs ADD COLUMN recruiterOutreachTemplate TEXT DEFAULT ''",
    ),
    (
        "russianSpeakerOutreachTemplate",
        "ALTER TABLE jobs ADD COLUMN russianSpeakerOutreachTemplate TEXT DEFAULT ''",
    ),
    ("activityLog", "ALTER TABLE jobs ADD COLUMN activityLog TEXT DEFAULT '[]'"),
    ("companyUrl", "ALTER TABLE jobs ADD COLUMN companyUrl TEXT DEFAULT ''"),
    ("archived", "ALTER TABLE jobs ADD COLUMN archived INTEGER DEFAULT 0"),
    ("rejectedAt", "ALTER TABLE jobs ADD COLUMN rejectedAt TEXT DEFAULT ''"),
    ("autoArchiveExempt", "ALTER TABLE jobs ADD COLUMN autoArchiveExempt INTEGER DEFAULT 0"),
    ("enrichmentNoteKind", "ALTER TABLE jobs ADD COLUMN enrichmentNoteKind TEXT DEFAULT ''"),
    ("unclassified", "ALTER TABLE jobs ADD COLUMN unclassified INTEGER DEFAULT 0"),
    ("batchAttempts", "ALTER TABLE jobs ADD COLUMN batchAttempts INTEGER DEFAULT 0"),
    ("companyResearch", "ALTER TABLE jobs ADD COLUMN companyResearch TEXT DEFAULT ''"),
)


def _migration_002_jobs_extra_columns(conn: sqlite3.Connection) -> None:
    for column, ddl in _JOBS_COLUMN_DDLS:
        _add_column_if_missing(conn, "jobs", column, ddl)


def _migration_003_batch_jobs_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS batch_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batchName TEXT NOT NULL UNIQUE,
            displayName TEXT NOT NULL,
            state TEXT NOT NULL,
            kind TEXT NOT NULL,
            submittedAt TEXT NOT NULL,
            lastPolledAt TEXT,
            resultFileName TEXT,
            jobIds TEXT NOT NULL,
            searchRemoteTypes TEXT,
            searchSeniorities TEXT
        )
        """
    )
    conn.commit()
    for column, ddl in (
        ("searchRemoteTypes", "ALTER TABLE batch_jobs ADD COLUMN searchRemoteTypes TEXT"),
        ("searchSeniorities", "ALTER TABLE batch_jobs ADD COLUMN searchSeniorities TEXT"),
    ):
        _add_column_if_missing(conn, "batch_jobs", column, ddl)


def _migration_004_outreach_settings_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS outreach_settings (
            id INTEGER PRIMARY KEY,
            target_russian_speakers INTEGER NOT NULL DEFAULT 1,
            target_recruiters INTEGER NOT NULL DEFAULT 1,
            short_connection_note INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.commit()


def _migration_005_contact_sample_cache(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS contact_sample_cache (
            company_slug TEXT NOT NULL,
            stream TEXT NOT NULL DEFAULT '',
            profiles TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            pages_fetched INTEGER DEFAULT 1,
            last_fetch_empty INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (company_slug, stream)
        )
        """
    )
    conn.commit()
    _add_column_if_missing(
        conn,
        "contact_sample_cache",
        "last_fetch_empty",
        "ALTER TABLE contact_sample_cache ADD COLUMN last_fetch_empty INTEGER NOT NULL DEFAULT 0",
    )

    cols = _table_columns(conn, "contact_sample_cache")
    if "stream" not in cols:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS contact_sample_cache_new (
                company_slug TEXT NOT NULL,
                stream TEXT NOT NULL DEFAULT '',
                profiles TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                display_name TEXT DEFAULT '',
                pages_fetched INTEGER DEFAULT 1,
                PRIMARY KEY (company_slug, stream)
            );
            INSERT OR IGNORE INTO contact_sample_cache_new
                (company_slug, stream, profiles, fetched_at, display_name, pages_fetched)
            SELECT company_slug, '', profiles, fetched_at, display_name, pages_fetched
            FROM contact_sample_cache;
            DROP TABLE contact_sample_cache;
            ALTER TABLE contact_sample_cache_new RENAME TO contact_sample_cache;
            """
        )
        conn.commit()
        _add_column_if_missing(
            conn,
            "contact_sample_cache",
            "last_fetch_empty",
            "ALTER TABLE contact_sample_cache ADD COLUMN last_fetch_empty INTEGER NOT NULL DEFAULT 0",
        )


def _migration_006_outreach_settings_short_note(conn: sqlite3.Connection) -> None:
    _add_column_if_missing(
        conn,
        "outreach_settings",
        "short_connection_note",
        "ALTER TABLE outreach_settings ADD COLUMN short_connection_note INTEGER NOT NULL DEFAULT 1",
    )


def _migration_007_company_research_cache(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS company_research_cache (
            company_key TEXT PRIMARY KEY,
            glassdoor_company_id TEXT DEFAULT '',
            matched_name TEXT DEFAULT '',
            company_size TEXT DEFAULT '',
            rating REAL,
            review_count INTEGER,
            recommend_percent REAL,
            salaries_by_title TEXT DEFAULT '{}',
            interviews_by_title TEXT DEFAULT '{}',
            fetched_at TEXT DEFAULT ''
        )
        """
    )
    conn.commit()


def apply_pipeline_status_backfill(conn: sqlite3.Connection) -> None:
    """Idempotent legacy status normalization — also run after seed on each init."""
    if "matchType" not in _table_columns(conn, "jobs"):
        return
    conn.execute(
        "UPDATE jobs SET status = 'scraped' "
        "WHERE (matchType = '' OR matchType IS NULL) AND status IN ('found', 'rejected')"
    )
    conn.execute(
        "UPDATE jobs SET status = 'matched' "
        "WHERE (matchType != '' AND matchType IS NOT NULL) AND status = 'found'"
    )
    conn.execute("UPDATE jobs SET status = 'scraped' WHERE status = 'sourced'")
    conn.execute("UPDATE jobs SET status = 'accepted' WHERE status IN ('enriching', 'enriched')")
    conn.execute("UPDATE jobs SET status = 'applied' WHERE status = 'contacted'")
    conn.commit()


def apply_rejected_at_backfill(conn: sqlite3.Connection) -> None:
    """Idempotent rejectedAt fill for legacy Rejected rows."""
    if "rejectedAt" not in _table_columns(conn, "jobs"):
        return
    conn.execute(
        "UPDATE jobs SET rejectedAt = datetime('now') "
        "WHERE status = 'rejected' AND (rejectedAt IS NULL OR rejectedAt = '')"
    )
    conn.commit()


def _migration_008_pipeline_status_backfill(conn: sqlite3.Connection) -> None:
    apply_pipeline_status_backfill(conn)


def _migration_009_rejected_at_backfill(conn: sqlite3.Connection) -> None:
    apply_rejected_at_backfill(conn)


def _migration_010_jobs_favorited(conn: sqlite3.Connection) -> None:
    _add_column_if_missing(
        conn,
        "jobs",
        "favorited",
        "ALTER TABLE jobs ADD COLUMN favorited INTEGER DEFAULT 0",
    )


def _migration_011_jobs_employment_type(conn: sqlite3.Connection) -> None:
    _add_column_if_missing(
        conn,
        "jobs",
        "employmentType",
        "ALTER TABLE jobs ADD COLUMN employmentType TEXT DEFAULT ''",
    )


def _migration_012_batch_jobs_search_employment_types(conn: sqlite3.Connection) -> None:
    _add_column_if_missing(
        conn,
        "batch_jobs",
        "searchEmploymentTypes",
        "ALTER TABLE batch_jobs ADD COLUMN searchEmploymentTypes TEXT DEFAULT 'any'",
    )


def _migration_013_jobs_annual_posted_salary(conn: sqlite3.Connection) -> None:
    """Nullable Annual Posted Salary band alongside free-text Posted Salary."""
    for column, ddl in (
        ("annualMin", "ALTER TABLE jobs ADD COLUMN annualMin INTEGER"),
        ("annualMax", "ALTER TABLE jobs ADD COLUMN annualMax INTEGER"),
        ("annualCurrency", "ALTER TABLE jobs ADD COLUMN annualCurrency TEXT"),
    ):
        _add_column_if_missing(conn, "jobs", column, ddl)


def _migration_014_batch_jobs_search_salary_min(conn: sqlite3.Connection) -> None:
    """Parsed Salary Min (annual integer) for attribute gating at writeback."""
    _add_column_if_missing(
        conn,
        "batch_jobs",
        "searchSalaryMin",
        "ALTER TABLE batch_jobs ADD COLUMN searchSalaryMin INTEGER",
    )


def _migration_015_jobs_comments_json(conn: sqlite3.Connection) -> None:
    """Replace overwriteable notes blob with Job Comments JSON list."""
    _add_column_if_missing(
        conn,
        "jobs",
        "comments",
        "ALTER TABLE jobs ADD COLUMN comments TEXT DEFAULT '[]'",
    )
    apply_legacy_comment_blob_migration(conn)


def apply_legacy_comment_blob_migration(conn: sqlite3.Connection) -> None:
    """Idempotent: non-empty legacy ``comment`` TEXT → one root in ``comments``."""
    cols = _table_columns(conn, "jobs")
    if "comments" not in cols or "comment" not in cols:
        return
    rows = conn.execute(
        "SELECT id, comment, comments FROM jobs "
        "WHERE comment IS NOT NULL AND TRIM(comment) != ''"
    ).fetchall()
    migrated_at = datetime.now(UTC).isoformat()
    for row in rows:
        job_id, blob, raw_comments = row[0], row[1], row[2]
        try:
            existing = json.loads(raw_comments) if raw_comments else []
        except Exception:
            existing = []
        if isinstance(existing, list) and existing:
            conn.execute("UPDATE jobs SET comment = '' WHERE id = ?", (job_id,))
            continue
        root = {
            "id": f"c{uuid.uuid4().hex[:12]}",
            "parentId": None,
            "body": str(blob).strip(),
            "createdAt": migrated_at,
            "editedAt": None,
        }
        conn.execute(
            "UPDATE jobs SET comments = ?, comment = '' WHERE id = ?",
            (json.dumps([root]), job_id),
        )
    conn.commit()


_MIGRATIONS: dict[int, MigrationFn] = {
    1: _migration_001_create_jobs_table,
    2: _migration_002_jobs_extra_columns,
    3: _migration_003_batch_jobs_table,
    4: _migration_004_outreach_settings_table,
    5: _migration_005_contact_sample_cache,
    6: _migration_006_outreach_settings_short_note,
    7: _migration_007_company_research_cache,
    8: _migration_008_pipeline_status_backfill,
    9: _migration_009_rejected_at_backfill,
    10: _migration_010_jobs_favorited,
    11: _migration_011_jobs_employment_type,
    12: _migration_012_batch_jobs_search_employment_types,
    13: _migration_013_jobs_annual_posted_salary,
    14: _migration_014_batch_jobs_search_salary_min,
    15: _migration_015_jobs_comments_json,
}


def run_migrations(conn: sqlite3.Connection) -> int:
    """Apply pending migrations in order; return final schema version."""
    current = get_schema_version(conn)
    while current < CURRENT_SCHEMA_VERSION:
        next_version = current + 1
        migration = _MIGRATIONS.get(next_version)
        if migration is None:
            raise RuntimeError(f"Missing migration for schema version {next_version}")
        migration(conn)
        _set_schema_version(conn, next_version)
        current = next_version
    return current
