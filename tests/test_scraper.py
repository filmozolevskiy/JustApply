import os
import sys
import pytest
import json
import asyncio
from fastapi.testclient import TestClient

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import database
import prototype_dashboard
from prototype_dashboard import app
from src.core.scraper import (
    scrape_linkedin_jobs, 
    normalize_brightdata_job, 
    match_company_size, 
    is_eastern_timezone,
    matches_position_keywords
)

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_job_tracker.db"
    test_db_str = str(test_db)
    monkeypatch.setattr(database, "DB_PATH", test_db_str)
    database.init_db(test_db_str)
    yield test_db_str

@pytest.mark.asyncio
async def test_scraper_mock_yields():
    # Test scrape_linkedin_jobs directly in mock mode
    jobs = await scrape_linkedin_jobs(
        query="QA Engineer",
        location="New York",
        remote_types="remote",
        seniorities="senior",
        company_sizes="large",
        log_func=print
    )
    # The mock returns 3 jobs. ScaleLabs (senior, remote, 750 size) matches all.
    # BrightFlow (senior, hybrid/in-office, 150 size) is hybrid, so skipped.
    # WebStart (junior, San Francisco, 25 size) is skipped because it's junior and SF.
    assert len(jobs) == 1
    assert jobs[0]["company"] == "ScaleLabs Inc."
    assert jobs[0]["remoteType"] == "remote"
    assert jobs[0]["seniority"] == "senior"

def test_company_size_matching():
    assert match_company_size("1-50", ["small"]) is True
    assert match_company_size("100-500", ["medium"]) is True
    assert match_company_size("1000+", ["large"]) is True
    assert match_company_size("2500", ["large"]) is True
    assert match_company_size("10-50", ["medium"]) is False

def test_matches_position_keywords():
    assert matches_position_keywords("Senior QA Automation", ["qa"]) is True
    assert matches_position_keywords("Senior Developer", ["qa"]) is False

def test_is_eastern_timezone():
    assert is_eastern_timezone("Remote", "Est timezone preferred", True) is True
    assert is_eastern_timezone("San Francisco, CA", "Work in PST timezone only.", False) is False
    assert is_eastern_timezone("New York, NY", "", False) is True

def test_api_search_and_sse_logs():
    # Call POST /api/search
    search_payload = {
        "query": "QA Engineer",
        "location": "New York",
        "platform": "brightdata_linkedin",
        "active_resume": "qa.md",
        "mock_eval": True,
        "remote_type": "any",
        "seniority": "any",
        "salary": "",
        "company_size": "any"
    }
    response = client.post("/api/search", json=search_payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "triggered"
    task_id = res_data["task_id"]
    assert task_id is not None

    # Retrieve logs using SSE endpoint
    with client.stream("GET", f"/api/logs/{task_id}") as stream_resp:
        assert stream_resp.status_code == 200
        
        events = []
        for line in stream_resp.iter_lines():
            if line.startswith("data:"):
                data_json = json.loads(line[5:])
                events.append(data_json)
                
    # Verify that we have some log lines and done/result events
    assert len(events) > 0
    log_types = [e.get("type") for e in events]
    assert "log" in log_types
    assert "done" in log_types
    assert "result" in log_types
    
    # Verify results are merged in the database
    db_jobs = database.get_jobs()
    # The mock returns 2-3 jobs depending on filtering. In search_payload we passed "any" for all filters,
    # so we should get multiple matching jobs.
    assert len(db_jobs) > 6
