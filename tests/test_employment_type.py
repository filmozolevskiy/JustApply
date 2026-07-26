"""Employment Type persist path: scrape → Job model → API → drawer (#172)."""

import sqlite3

import pytest
import src.db.connection as _db_connection
from fastapi.testclient import TestClient
from src import db as database
from src.db.migrations import CURRENT_SCHEMA_VERSION, get_schema_version
from src.schemas import Job
from src.web.server import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_employment_type.db"
    test_db_str = str(test_db)
    monkeypatch.setattr(_db_connection, "DB_PATH", test_db_str)
    database.init_db(test_db_str)
    yield test_db_str


def test_job_model_persists_employment_type(setup_test_db):
    """Jobs table / Job model store Employment Type; blank defaults for legacy."""
    job_id = database.add_job(
        {
            "title": "Contract QA",
            "company": "Acme",
            "link": "https://linkedin.com/jobs/et-persist-1",
            "employmentType": "Contract",
        },
        db_path=setup_test_db,
    )
    job = database.get_job(job_id, db_path=setup_test_db)
    assert isinstance(job, Job)
    assert job.employmentType == "Contract"

    blank_id = database.add_job(
        {
            "title": "Unknown Type QA",
            "company": "BlankCo",
            "link": "https://linkedin.com/jobs/et-persist-2",
        },
        db_path=setup_test_db,
    )
    blank = database.get_job(blank_id, db_path=setup_test_db)
    assert blank.employmentType == ""


def test_migration_adds_employment_type_default_empty(tmp_path):
    """Versioned migration adds employmentType; existing rows stay empty/unknown."""
    db_path = str(tmp_path / "legacy_et.db")
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
        "INSERT INTO jobs (title, company, status) VALUES ('Legacy', 'Co', 'found')"
    )
    conn.commit()
    conn.close()

    database.init_db(db_path)

    conn2 = _db_connection.get_db_connection(db_path)
    try:
        assert get_schema_version(conn2) == CURRENT_SCHEMA_VERSION
        cols = {row[1] for row in conn2.execute("PRAGMA table_info(jobs)")}
        assert "employmentType" in cols
    finally:
        conn2.close()

    job = database.get_jobs(db_path)[0]
    assert job.employmentType == ""


def test_get_jobs_api_includes_employment_type(setup_test_db):
    """GET /api/jobs and job detail expose Employment Type."""
    job_id = database.add_job(
        {
            "title": "Full-time QA",
            "company": "ApiCo",
            "link": "https://linkedin.com/jobs/et-api-1",
            "employmentType": "Full-time",
        },
        db_path=setup_test_db,
    )

    listing = client.get("/api/jobs?archived=all").json()
    found = next(j for j in listing if j["id"] == job_id)
    assert found["employmentType"] == "Full-time"

    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["employmentType"] == "Full-time"


@pytest.mark.asyncio
async def test_mock_scrape_supplies_employment_type(monkeypatch):
    """Mock scrape path supplies Employment Type for local demos."""
    monkeypatch.setenv("MOCK_SCRAPER", "true")
    from src.core.scraper import scrape_linkedin_jobs

    jobs = await scrape_linkedin_jobs(
        query="QA Engineer",
        location="Toronto",
        company_sizes="large",
        log_func=print,
    )
    assert len(jobs) == 1
    assert jobs[0]["employmentType"] == "Full-time"


def test_seed_jobs_include_employment_type(setup_test_db):
    """Seed path supplies Employment Type for local demos."""
    jobs = database.get_jobs(setup_test_db)
    seeded = next(j for j in jobs if j.id == 1)
    assert seeded.employmentType == "Full-time"
    contractor = next(j for j in jobs if j.id == 7)
    assert contractor.employmentType == "Contract"


def test_drawer_job_info_shows_employment_type_when_known():
    """Drawer Job Info shows Employment Type when known; omits blank; no card badge."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    drawer = (root / "src/web/static/js/drawerController.js").read_text()
    board = (root / "src/web/static/js/boardRenderer.js").read_text()

    assert "Employment Type" in drawer
    assert "employmentType" in drawer
    assert "${job.employmentType ?" in drawer or "job.employmentType ?" in drawer
    assert "Employment Type" not in board
    assert "employmentType" not in board
