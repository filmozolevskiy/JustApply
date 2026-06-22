import os
import sys
import pytest
import json
import asyncio
from fastapi.testclient import TestClient

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src import db as database
import src.db.connection as _db_connection
import src.web.server as server_module
from src.web.server import app
from src.core.scraper import (
    scrape_linkedin_jobs, 
    normalize_brightdata_job, 
    match_company_size, 
    is_eastern_timezone,
    matches_position_keywords,
)

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MOCK_SCRAPER", "true")
    test_db = tmp_path / "test_job_tracker.db"
    test_db_str = str(test_db)
    monkeypatch.setattr(_db_connection, "DB_PATH", test_db_str)
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
    # The mock returns 3 jobs. ScaleLabs (senior, remote, 750 size) matches company size filter.
    # BrightFlow (150 size) and WebStart (25 size) are skipped by company size, not seniority.
    assert len(jobs) == 1
    assert jobs[0]["company"] == "ScaleLabs Inc."
    assert jobs[0]["remoteType"] == "remote"
    assert jobs[0]["seniority"] == "senior"

@pytest.mark.asyncio
async def test_scraper_missing_api_key_raises_value_error(monkeypatch):
    # Set MOCK_SCRAPER to false
    monkeypatch.setenv("MOCK_SCRAPER", "false")
    # Ensure BRIGHTDATA_API_KEY is not in environment
    monkeypatch.delenv("BRIGHTDATA_API_KEY", raising=False)
    
    with pytest.raises(ValueError) as excinfo:
        await scrape_linkedin_jobs(
            query="QA Engineer",
            location="New York",
        )
    assert "BRIGHTDATA_API_KEY" in str(excinfo.value)

@pytest.mark.asyncio
async def test_scraper_unset_mock_scraper_and_missing_api_key_raises_value_error(monkeypatch):
    monkeypatch.delenv("MOCK_SCRAPER", raising=False)
    monkeypatch.delenv("BRIGHTDATA_API_KEY", raising=False)
    
    with pytest.raises(ValueError) as excinfo:
        await scrape_linkedin_jobs(
            query="QA Engineer",
            location="New York",
        )
    assert "BRIGHTDATA_API_KEY" in str(excinfo.value)

def test_normalize_brightdata_job_preserves_company_url():
    raw_job = {
        "job_title": "Product Application Engineer",
        "company_name": "Trane Technologies",
        "company_url": "https://www.linkedin.com/company/tranetechnologies?trk=public_jobs_topcard-org-name",
        "url": "https://linkedin.com/jobs/view/1234",
        "job_location": "Montreal, QC",
        "is_remote": False,
    }
    result = normalize_brightdata_job(raw_job)
    assert result["companyUrl"] == (
        "https://www.linkedin.com/company/tranetechnologies?trk=public_jobs_topcard-org-name"
    )


def test_normalize_brightdata_job_sets_is_job_poster_flag():
    raw_job = {
        "job_title": "Senior QA",
        "company_name": "Acme",
        "url": "https://linkedin.com/jobs/1234",
        "job_location": "Remote",
        "is_remote": True,
        "job_poster": {
            "name": "Sarah Jenkins",
            "title": "Recruiting Director",
            "url": "https://linkedin.com/in/sarah-jenkins"
        }
    }
    result = normalize_brightdata_job(raw_job)
    assert len(result["contacts"]) == 1
    contact = result["contacts"][0]
    assert contact["is_job_poster"] is True
    assert contact["name"] == "Sarah Jenkins"


def test_normalize_brightdata_job_no_poster_yields_empty_contacts():
    raw_job = {
        "job_title": "Senior QA",
        "company_name": "Acme",
        "url": "https://linkedin.com/jobs/5678",
        "job_location": "Remote",
        "is_remote": True,
    }
    result = normalize_brightdata_job(raw_job)
    assert result["contacts"] == []


def test_company_size_matching():
    assert match_company_size("1-50", ["small"]) is True
    assert match_company_size("100-500", ["medium"]) is True
    assert match_company_size("1,000+", ["large"]) is True
    assert match_company_size("10,000+", ["large"]) is True
    assert match_company_size("2,500", ["large"]) is True
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


def test_api_logs_replay_reconnection():
    # Create a task state manually in active_tasks
    task_id = "test-reconnect-task-id"
    from src.web.server import active_tasks, TaskState
    
    state = TaskState({"query": "test"})
    # Manually append some logs
    state.logs = [
        {"level": "info", "message": "Log message 1"},
        {"level": "warning", "message": "Log message 2"}
    ]
    # Set status to completed so event generator completes immediately
    state.status = "completed"
    # Put None in queue so the stream loop exits immediately
    state.queue.put_nowait(None)
    
    active_tasks[task_id] = state
    
    try:
        # Retrieve logs using SSE endpoint
        with client.stream("GET", f"/api/logs/{task_id}") as stream_resp:
            assert stream_resp.status_code == 200
            
            events = []
            for line in stream_resp.iter_lines():
                if line.startswith("data:"):
                    data_json = json.loads(line[5:])
                    events.append(data_json)
                    
        # Verify the logs are replayed (result events are incremental job saves, not a batch summary)
        assert len(events) == 3  # log 1, log 2, done
        assert events[0] == {"type": "log", "level": "info", "message": "Log message 1"}
        assert events[1] == {"type": "log", "level": "warning", "message": "Log message 2"}
        assert events[2] == {"type": "done"}
    finally:
        # Clean up
        active_tasks.pop(task_id, None)


@pytest.mark.asyncio
async def test_scraper_trigger_fails_immediately(monkeypatch):
    from unittest.mock import patch, MagicMock, AsyncMock
    # Configure environment so we enter the real path
    monkeypatch.setenv("MOCK_SCRAPER", "false")
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "fake_key")
    
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    
    # We patch httpx.AsyncClient.post to return mock_response
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
        with pytest.raises(Exception) as excinfo:
            await scrape_linkedin_jobs(
                query="QA Engineer",
                location="New York",
                log_func=print
            )
        # Verify the exception message contains "Failed to trigger scraper"
        assert "Failed to trigger scraper" in str(excinfo.value)
        # Verify post was called once with discovery params
        assert mock_post.call_count == 1
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["params"]["type"] == "discover_new"
        assert call_kwargs["params"]["discover_by"] == "keyword"
        assert call_kwargs["json"][0]["keyword"] == "QA Engineer"


@pytest.mark.asyncio
async def test_scraper_polling_retry_on_transient_failure(monkeypatch):
    from unittest.mock import patch, MagicMock, AsyncMock
    # Configure environment
    monkeypatch.setenv("MOCK_SCRAPER", "false")
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "fake_key")
    
    # Mock post (trigger) response
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json = MagicMock(return_value={"snapshot_id": "snap_123"})
    
    # Mock progress check failures and then success
    mock_progress_fail = MagicMock()
    mock_progress_fail.status_code = 500
    mock_progress_fail.text = "Transient progress error"
    
    mock_progress_success = MagicMock()
    mock_progress_success.status_code = 200
    mock_progress_success.json = MagicMock(return_value={"status": "ready"})
    
    # Mock snapshot results response
    mock_snapshot_resp = MagicMock()
    mock_snapshot_resp.status_code = 200
    mock_snapshot_resp.json = MagicMock(return_value=[{
        "job_title": "Senior QA Engineer",
        "company_name": "ScaleLabs Inc.",
        "company_size": "750",
        "url": "https://linkedin.com/jobs/mock-991",
        "date_posted": "2026-06-07",
        "job_location": "New York, NY",
        "job_summary": "We are seeking a senior practitioner...",
        "job_seniority_level": "senior",
        "is_remote": True
    }])
    
    get_calls = []
    async def mock_get(url, **kwargs):
        get_calls.append(url)
        if "progress" in url:
            if len([u for u in get_calls if "progress" in u]) == 1:
                # First progress check fails
                return mock_progress_fail
            else:
                # Subsequent progress check succeeds
                return mock_progress_success
        elif "snapshot" in url:
            return mock_snapshot_resp
        raise Exception(f"Unexpected GET URL: {url}")
        
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_post_resp) as mock_post, \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=mock_get) as mock_get_patched, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
         
        jobs = await scrape_linkedin_jobs(
            query="QA Engineer",
            location="New York",
            log_func=print
        )
        
        # Verify we got the jobs
        assert len(jobs) == 1
        assert jobs[0]["company"] == "ScaleLabs Inc."
        
        # Verify get was called 3 times: 2 for progress, 1 for snapshot
        assert len(get_calls) == 3
        # Verify sleep was called for backoff and for polling wait.
        assert mock_sleep.call_count >= 2


@pytest.mark.asyncio
async def test_scraper_polling_fails_persistently(monkeypatch):
    from unittest.mock import patch, MagicMock, AsyncMock
    # Configure environment
    monkeypatch.setenv("MOCK_SCRAPER", "false")
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "fake_key")
    
    # Mock post (trigger) response
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json = MagicMock(return_value={"snapshot_id": "snap_123"})
    
    # Mock progress check failures
    mock_progress_fail = MagicMock()
    mock_progress_fail.status_code = 500
    mock_progress_fail.text = "Persistent progress error"
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_post_resp) as mock_post, \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_progress_fail) as mock_get_patched, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
         
        with pytest.raises(Exception) as excinfo:
            await scrape_linkedin_jobs(
                query="QA Engineer",
                location="New York",
                log_func=print
            )
            
        assert "Failed to check scraper progress after 3 attempts" in str(excinfo.value)
        # Verify get (polling progress) was called 3 times
        assert mock_get_patched.call_count == 3
        # Verify sleep was called for backoff retries and polling waits
        assert mock_sleep.call_count >= 3


@pytest.mark.asyncio
async def test_scraper_snapshot_fetch_retry_on_transient_failure(monkeypatch):
    from unittest.mock import patch, MagicMock, AsyncMock
    # Configure environment
    monkeypatch.setenv("MOCK_SCRAPER", "false")
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "fake_key")
    
    # Mock post (trigger) response
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json = MagicMock(return_value={"snapshot_id": "snap_123"})
    
    # Mock progress check success (ready immediately)
    mock_progress_success = MagicMock()
    mock_progress_success.status_code = 200
    mock_progress_success.json = MagicMock(return_value={"status": "ready"})
    
    # Mock snapshot results: first fails, second succeeds
    mock_snapshot_fail = MagicMock()
    mock_snapshot_fail.status_code = 500
    mock_snapshot_fail.text = "Transient snapshot error"
    
    mock_snapshot_success = MagicMock()
    mock_snapshot_success.status_code = 200
    mock_snapshot_success.json = MagicMock(return_value=[{
        "job_title": "Senior QA Engineer",
        "company_name": "ScaleLabs Inc.",
        "company_size": "750",
        "url": "https://linkedin.com/jobs/mock-991",
        "date_posted": "2026-06-07",
        "job_location": "New York, NY",
        "job_summary": "We are seeking a senior practitioner...",
        "job_seniority_level": "senior",
        "is_remote": True
    }])
    
    get_calls = []
    async def mock_get(url, **kwargs):
        get_calls.append(url)
        if "progress" in url:
            return mock_progress_success
        elif "snapshot" in url:
            if len([u for u in get_calls if "snapshot" in u]) == 1:
                return mock_snapshot_fail
            else:
                return mock_snapshot_success
        raise Exception(f"Unexpected GET URL: {url}")
        
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_post_resp) as mock_post, \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=mock_get) as mock_get_patched, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
         
        jobs = await scrape_linkedin_jobs(
            query="QA Engineer",
            location="New York",
            log_func=print
        )
        
        assert len(jobs) == 1
        assert jobs[0]["company"] == "ScaleLabs Inc."
        
        # Verify get was called 3 times: 1 for progress, 2 for snapshot
        assert len(get_calls) == 3


@pytest.mark.asyncio
async def test_scraper_snapshot_fetch_fails_persistently(monkeypatch):
    from unittest.mock import patch, MagicMock, AsyncMock
    # Configure environment
    monkeypatch.setenv("MOCK_SCRAPER", "false")
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "fake_key")
    
    # Mock post (trigger) response
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json = MagicMock(return_value={"snapshot_id": "snap_123"})
    
    # Mock progress check success (ready immediately)
    mock_progress_success = MagicMock()
    mock_progress_success.status_code = 200
    mock_progress_success.json = MagicMock(return_value={"status": "ready"})
    
    # Mock snapshot results: persistent failure
    mock_snapshot_fail = MagicMock()
    mock_snapshot_fail.status_code = 500
    mock_snapshot_fail.text = "Persistent snapshot error"
    
    get_calls = []
    async def mock_get(url, **kwargs):
        get_calls.append(url)
        if "progress" in url:
            return mock_progress_success
        elif "snapshot" in url:
            return mock_snapshot_fail
        raise Exception(f"Unexpected GET URL: {url}")
        
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_post_resp) as mock_post, \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=mock_get) as mock_get_patched, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
         
        with pytest.raises(Exception) as excinfo:
            await scrape_linkedin_jobs(
                query="QA Engineer",
                location="New York",
                log_func=print
            )
            
        assert "Failed to fetch snapshot results after 3 attempts: HTTP 500" in str(excinfo.value)
        # Verify get was called 4 times: 1 for progress, 3 for snapshot
        assert len(get_calls) == 4


@pytest.mark.asyncio
async def test_scraper_snapshot_polls_on_http_202(monkeypatch):
    from unittest.mock import patch, MagicMock, AsyncMock
    monkeypatch.setenv("MOCK_SCRAPER", "false")
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "fake_key")

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json = MagicMock(return_value={"snapshot_id": "snap_123"})

    mock_progress_success = MagicMock()
    mock_progress_success.status_code = 200
    mock_progress_success.json = MagicMock(return_value={"status": "ready"})

    mock_snapshot_pending = MagicMock()
    mock_snapshot_pending.status_code = 202
    mock_snapshot_pending.text = "Snapshot is not ready yet, try again in 10s"

    mock_snapshot_success = MagicMock()
    mock_snapshot_success.status_code = 200
    mock_snapshot_success.json = MagicMock(return_value=[{
        "job_title": "Data Analyst",
        "company_name": "Acme Corp",
        "company_size": "100",
        "url": "https://linkedin.com/jobs/mock-202",
        "date_posted": "2026-06-07",
        "job_location": "Montreal, QC",
        "job_summary": "Analyze data.",
        "job_seniority_level": "mid",
        "is_remote": True,
    }])

    get_calls = []

    async def mock_get(url, **kwargs):
        get_calls.append(url)
        if "progress" in url:
            return mock_progress_success
        if "snapshot" in url:
            snapshot_attempts = len([u for u in get_calls if "snapshot" in u])
            if snapshot_attempts <= 2:
                return mock_snapshot_pending
            return mock_snapshot_success
        raise Exception(f"Unexpected GET URL: {url}")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_post_resp), \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=mock_get), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        jobs = await scrape_linkedin_jobs(
            query="Data Analyst",
            location="Montreal",
            log_func=print,
        )

    assert len(jobs) == 1
    assert jobs[0]["company"] == "Acme Corp"
    assert len(get_calls) == 4  # 1 progress + 3 snapshot (2×202, then 200)
    assert mock_sleep.call_count >= 2


@pytest.mark.asyncio
async def test_scraper_poll_logs_status_once_when_repeated(monkeypatch):
    """'running' repeated three times before 'ready' — 'Scraper status: running' logged once."""
    from unittest.mock import patch, MagicMock, AsyncMock
    monkeypatch.setenv("MOCK_SCRAPER", "false")
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "fake_key")

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json = MagicMock(return_value={"snapshot_id": "snap_abc"})

    mock_snapshot_resp = MagicMock()
    mock_snapshot_resp.status_code = 200
    mock_snapshot_resp.json = MagicMock(return_value=[])

    progress_statuses = ["running", "running", "running", "ready"]
    progress_call_count = [0]

    async def mock_get(url, **kwargs):
        if "progress" in url:
            idx = min(progress_call_count[0], len(progress_statuses) - 1)
            status = progress_statuses[idx]
            progress_call_count[0] += 1
            m = MagicMock()
            m.status_code = 200
            m.json = MagicMock(return_value={"status": status})
            return m
        return mock_snapshot_resp

    logged = []
    def capture_log(msg, level="info"):
        logged.append(msg)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_post_resp), \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=mock_get), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        await scrape_linkedin_jobs(
            query="QA Engineer",
            location="New York",
            log_func=capture_log
        )

    status_logs = [m for m in logged if m.startswith("Scraper status:")]
    assert sum(1 for m in status_logs if "running" in m) == 1
    assert sum(1 for m in status_logs if "ready" in m) == 1
    assert len(status_logs) == 2


@pytest.mark.asyncio
async def test_scraper_poll_logs_failed_status_once(monkeypatch):
    """'failed' scraper status is logged once when status transitions to failed."""
    from unittest.mock import patch, MagicMock, AsyncMock
    monkeypatch.setenv("MOCK_SCRAPER", "false")
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "fake_key")

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json = MagicMock(return_value={"snapshot_id": "snap_fail"})

    progress_statuses = ["running", "failed"]
    progress_call_count = [0]

    async def mock_get(url, **kwargs):
        if "progress" in url:
            idx = min(progress_call_count[0], len(progress_statuses) - 1)
            status = progress_statuses[idx]
            progress_call_count[0] += 1
            m = MagicMock()
            m.status_code = 200
            m.json = MagicMock(return_value={"status": status})
            return m
        raise Exception(f"Unexpected GET: {url}")

    logged = []
    def capture_log(msg, level="info"):
        logged.append(msg)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_post_resp), \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=mock_get), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(Exception):
            await scrape_linkedin_jobs(
                query="QA Engineer",
                location="New York",
                log_func=capture_log
            )

    status_logs = [m for m in logged if m.startswith("Scraper status:")]
    assert sum(1 for m in status_logs if "running" in m) == 1
    assert sum(1 for m in status_logs if "failed" in m) == 1




