"""Tests for Job Tracker Database connection settings (PRD #113 / issue #149)."""


from src.db.connection import get_db_connection

# Milliseconds — must match get_db_connection busy_timeout pragma.
EXPECTED_BUSY_TIMEOUT_MS = 5000

def test_get_db_connection_enables_wal_mode(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = get_db_connection(db_path)
    try:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert journal_mode.lower() == "wal"
    finally:
        conn.close()

def test_get_db_connection_sets_busy_timeout(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = get_db_connection(db_path)
    try:
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert busy_timeout == EXPECTED_BUSY_TIMEOUT_MS
    finally:
        conn.close()
