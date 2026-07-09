"""Tests for Company Research Cache — DB layer."""
import sqlite3

import pytest
import src.db.connection as _db_connection
from src import db as database
from src.db.company_research_cache import (
    delete_company_research_cache,
    get_company_research_cache,
    normalize_company_name,
    normalize_glassdoor_job_title,
    set_company_research_cache,
)


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(_db_connection, "DB_PATH", db_path)
    database.init_db(db_path)
    return db_path

def test_cache_table_created_by_init_db(db):
    conn = sqlite3.connect(db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='company_research_cache'"
    )
    assert cursor.fetchone() is not None
    cursor.execute("PRAGMA table_info(jobs)")
    cols = {row[1] for row in cursor.fetchall()}
    assert "companyResearch" in cols
    conn.close()

def test_normalize_company_name():
    assert normalize_company_name("  FlightHub  ") == "flighthub"
    assert normalize_company_name("My   Company") == "my company"

def test_normalize_glassdoor_job_title():
    assert normalize_glassdoor_job_title("  QA Engineer  ") == "qa engineer"

def test_cache_miss_returns_none(db):
    assert get_company_research_cache("acme", db_path=db) is None

def test_set_and_get_company_research_cache(db):
    set_company_research_cache(
        "flighthub",
        {
            "glassdoorCompanyId": "882104",
            "matchedName": "FlightHub",
            "companySize": "51 to 200 Employees",
            "rating": 2.8,
            "reviewCount": 246,
            "recommendPercent": 40.0,
            "salariesByTitle": {"qa engineer": {"medianBaseSalary": 85000, "currency": "USD"}},
            "interviewsByTitle": {"qa engineer": []},
        },
        db_path=db,
    )
    cached = get_company_research_cache("flighthub", db_path=db)
    assert cached is not None
    assert cached["glassdoorCompanyId"] == "882104"
    assert cached["matchedName"] == "FlightHub"
    assert cached["salariesByTitle"]["qa engineer"]["medianBaseSalary"] == 85000
    assert cached["fetchedAt"]

def test_empty_title_slice_cached(db):
    set_company_research_cache(
        "flighthub",
        {
            "glassdoorCompanyId": "882104",
            "matchedName": "FlightHub",
            "salariesByTitle": {"qa engineer": None},
            "interviewsByTitle": {"qa engineer": []},
        },
        db_path=db,
    )
    cached = get_company_research_cache("flighthub", db_path=db)
    assert "qa engineer" in cached["salariesByTitle"]
    assert cached["interviewsByTitle"]["qa engineer"] == []

def test_delete_company_research_cache(db):
    set_company_research_cache("acme", {"glassdoorCompanyId": "1"}, db_path=db)
    delete_company_research_cache("acme", db_path=db)
    assert get_company_research_cache("acme", db_path=db) is None
