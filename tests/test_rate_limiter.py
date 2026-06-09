import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from src.server import app
from src.cli import run_search
import src.rate_limiter as rate_limiter_module
from src.rate_limiter import RateLimiter, RateLimitError

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_lock_file(tmp_path):
    lock = str(tmp_path / ".last_trigger")
    rate_limiter_module.scrape_limiter._lock_file = lock
    yield lock
    rate_limiter_module.scrape_limiter._lock_file = rate_limiter_module.LOCK_FILE


class TestRateLimiter:
    def test_first_acquire_succeeds(self, tmp_path):
        limiter = RateLimiter(str(tmp_path / ".lock"))
        limiter.acquire()  # must not raise

    def test_second_acquire_within_window_raises(self, tmp_path):
        limiter = RateLimiter(str(tmp_path / ".lock"))
        with patch("time.time", return_value=1000.0):
            limiter.acquire()
        with patch("time.time", return_value=1030.0):
            with pytest.raises(RateLimitError) as exc_info:
                limiter.acquire()
        assert exc_info.value.wait_seconds == 30

    def test_acquire_after_window_succeeds(self, tmp_path):
        limiter = RateLimiter(str(tmp_path / ".lock"))
        with patch("time.time", return_value=1000.0):
            limiter.acquire()
        with patch("time.time", return_value=1065.0):
            limiter.acquire()  # must not raise

    def test_corrupt_lock_file_is_ignored(self, tmp_path):
        lock = tmp_path / ".lock"
        lock.write_text("not-a-float")
        limiter = RateLimiter(str(lock))
        limiter.acquire()  # must not raise


@pytest.mark.asyncio
async def test_server_search_rate_limit(monkeypatch):
    monkeypatch.setenv("MOCK_SCRAPER", "false")
    with patch("src.server.run_scraping_task"), patch("time.time") as mock_time:
        payload = {
            "query": "QA Engineer", "location": "Remote",
            "platform": "brightdata_linkedin", "active_resume": "qa.md",
            "mock_eval": False, "remote_type": "any",
            "seniority": "any", "salary": "", "company_size": "any",
        }
        mock_time.return_value = 1000.0
        assert client.post("/api/search", json=payload).status_code == 200

        mock_time.return_value = 1030.0
        r = client.post("/api/search", json=payload)
        assert r.status_code == 429
        assert "Too many requests" in r.json()["message"]

        mock_time.return_value = 1065.0
        assert client.post("/api/search", json=payload).status_code == 200


@pytest.mark.asyncio
async def test_server_scrape_rate_limit(monkeypatch):
    monkeypatch.setenv("MOCK_SCRAPER", "false")
    with patch("src.server.run_scraping_task"), patch("time.time") as mock_time:
        mock_time.return_value = 1000.0
        assert client.post("/api/scrape?mock_eval=false").status_code == 200

        mock_time.return_value = 1030.0
        r = client.post("/api/scrape?mock_eval=false")
        assert r.status_code == 429

        mock_time.return_value = 1065.0
        assert client.post("/api/scrape?mock_eval=false").status_code == 200


@pytest.mark.asyncio
async def test_mock_mode_bypasses_rate_limit(monkeypatch):
    monkeypatch.setenv("MOCK_SCRAPER", "true")
    with patch("src.server.run_scraping_task"), patch("time.time") as mock_time:
        payload = {
            "query": "QA", "location": "Remote", "platform": "brightdata_linkedin",
            "active_resume": "qa.md", "mock_eval": True, "remote_type": "any",
            "seniority": "any", "salary": "", "company_size": "any",
        }
        mock_time.return_value = 1000.0
        client.post("/api/search", json=payload)
        mock_time.return_value = 1010.0
        assert client.post("/api/search", json=payload).status_code == 200


@pytest.mark.asyncio
async def test_cli_rate_limit(monkeypatch):
    monkeypatch.setenv("MOCK_SCRAPER", "false")
    with patch("src.cli.scrape_linkedin_jobs", return_value=[]), \
         patch("src.cli.database.init_db"), \
         patch("src.cli.database.add_job"), \
         patch("time.time") as mock_time:

        mock_time.return_value = 1000.0
        await run_search("QA", mock_eval=False)

        mock_time.return_value = 1030.0
        with pytest.raises(SystemExit) as exc_info:
            await run_search("QA", mock_eval=False)
        assert exc_info.value.code == 1

        mock_time.return_value = 1065.0
        await run_search("QA", mock_eval=False)


@pytest.mark.asyncio
async def test_cli_and_server_share_state(monkeypatch):
    """CLI trigger is visible to server — bypass via process switch is impossible."""
    monkeypatch.setenv("MOCK_SCRAPER", "false")
    with patch("src.cli.scrape_linkedin_jobs", return_value=[]), \
         patch("src.cli.database.init_db"), \
         patch("src.cli.database.add_job"), \
         patch("src.server.run_scraping_task"), \
         patch("time.time") as mock_time:

        mock_time.return_value = 1000.0
        await run_search("QA", mock_eval=False)  # CLI trigger

        mock_time.return_value = 1030.0
        payload = {
            "query": "QA", "location": "Remote", "platform": "brightdata_linkedin",
            "active_resume": "qa.md", "mock_eval": False, "remote_type": "any",
            "seniority": "any", "salary": "", "company_size": "any",
        }
        r = client.post("/api/search", json=payload)  # server should see CLI's trigger
        assert r.status_code == 429
