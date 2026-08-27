"""Annual Posted Salary schema persistence (PRD #171 / issue #178)."""

import sqlite3

import src.db.connection as _db_connection
from src import db as database
from src.db.migrations import CURRENT_SCHEMA_VERSION, get_schema_version
from src.schemas import Job


def test_job_model_stores_nullable_annual_band(tmp_path, monkeypatch):
    db_path = str(tmp_path / "annual_schema.db")
    monkeypatch.setattr(_db_connection, "DB_PATH", db_path)
    database.init_db(db_path)

    job_id = database.add_job(
        {
            "title": "QA Engineer",
            "company": "Acme",
            "link": "https://linkedin.com/jobs/annual-1",
            "salary": "$130,000",
        },
        db_path=db_path,
    )
    database.update_job_evaluation(
        job_id,
        {
            "matchScore": 80,
            "matchType": "match",
            "shouldProceed": True,
            "salary": "$130,000",
            "annualMin": 130000,
            "annualMax": 130000,
            "annualCurrency": "USD",
            "remoteType": "remote",
            "seniority": "mid",
            "employmentType": "Full-time",
        },
        db_path=db_path,
    )

    job = database.get_job(job_id, db_path=db_path)
    assert isinstance(job, Job)
    assert job.salary == "$130,000"
    assert job.annualMin == 130000
    assert job.annualMax == 130000
    assert job.annualCurrency == "USD"

    blank = database.get_job(
        database.add_job(
            {
                "title": "No Band",
                "company": "BlankCo",
                "link": "https://linkedin.com/jobs/annual-2",
            },
            db_path=db_path,
        ),
        db_path=db_path,
    )
    assert blank.annualMin is None
    assert blank.annualMax is None
    assert blank.annualCurrency is None


def test_migration_adds_annual_posted_salary_columns(tmp_path):
    db_path = str(tmp_path / "legacy_annual.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '',
            company TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'found',
            matchType TEXT DEFAULT '',
            salary TEXT DEFAULT ''
        )
        """
    )
    conn.execute(
        "INSERT INTO jobs (title, company, status, salary) VALUES ('Legacy', 'Co', 'found', '$100k')"
    )
    conn.commit()
    conn.close()

    database.init_db(db_path)

    conn2 = _db_connection.get_db_connection(db_path)
    try:
        assert get_schema_version(conn2) == CURRENT_SCHEMA_VERSION
        cols = {row[1] for row in conn2.execute("PRAGMA table_info(jobs)")}
        assert "annualMin" in cols
        assert "annualMax" in cols
        assert "annualCurrency" in cols
    finally:
        conn2.close()

    job = database.get_jobs(db_path)[0]
    assert job.salary == "$100k"
    assert job.annualMin is None
    assert job.annualMax is None
    assert job.annualCurrency is None
