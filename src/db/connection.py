import sqlite3
import os

from .seed import _seed_db

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(_PROJECT_ROOT, "data", "job_tracker.db")


def get_db_connection(db_path=None):
    if db_path is None:
        db_path = DB_PATH
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=None):
    if db_path is None:
        db_path = DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
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
            status TEXT NOT NULL DEFAULT 'sourced',
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
    """)
    conn.commit()

    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN isRecruiter INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN enrichmentNote TEXT DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN recruiterOutreachTemplate TEXT DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN russianSpeakerOutreachTemplate TEXT DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN activityLog TEXT DEFAULT '[]'")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS outreach_settings (
            id INTEGER PRIMARY KEY,
            target_russian_speakers INTEGER NOT NULL DEFAULT 1,
            target_recruiters INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM jobs")
    count = cursor.fetchone()[0]
    if count == 0:
        _seed_db(cursor)
        conn.commit()
    conn.close()
