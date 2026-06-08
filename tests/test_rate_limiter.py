import os
import pytest
import time
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.server import app
import src.server as server_module
from src.cli import run_search

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_globals():
    server_module.last_trigger_time = None
    yield
    server_module.last_trigger_time = None


@pytest.mark.asyncio
async def test_server_rate_limiter_search(monkeypatch):
    # Set MOCK_SCRAPER to false to force real run logic
    monkeypatch.setenv("MOCK_SCRAPER", "false")

    # Mock run_scraping_task to avoid running actual scraping
    with patch("src.server.run_scraping_task"), patch("time.time") as mock_time:
        search_payload = {
            "query": "QA Engineer",
            "location": "New York",
            "platform": "brightdata_linkedin",
            "active_resume": "qa.md",
            "mock_eval": False,
            "remote_type": "any",
            "seniority": "any",
            "salary": "",
            "company_size": "any"
        }

        # 1. First trigger is allowed
        mock_time.return_value = 1000.0
        response = client.post("/api/search", json=search_payload)
        assert response.status_code == 200
        assert response.json()["status"] == "triggered"

        # 2. Second trigger within 60 seconds -> HTTP 429
        mock_time.return_value = 1030.0
        response = client.post("/api/search", json=search_payload)
        assert response.status_code == 429
        assert "Too many requests" in response.json()["message"]

        # 3. Third trigger after 60 seconds -> HTTP 200
        mock_time.return_value = 1065.0
        response = client.post("/api/search", json=search_payload)
        assert response.status_code == 200
        assert response.json()["status"] == "triggered"

        # 4. Trigger with mock_eval=True AND MOCK_SCRAPER=true should bypass rate limiting
        monkeypatch.setenv("MOCK_SCRAPER", "true")
        mock_payload = dict(search_payload)
        mock_payload["mock_eval"] = True
        mock_time.return_value = 1070.0
        response = client.post("/api/search", json=mock_payload)
        assert response.status_code == 200
        assert response.json()["status"] == "triggered"


@pytest.mark.asyncio
async def test_server_rate_limiter_scrape(monkeypatch):
    # Set MOCK_SCRAPER to false to force real run logic
    monkeypatch.setenv("MOCK_SCRAPER", "false")

    with patch("src.server.run_scraping_task"), patch("time.time") as mock_time:
        # 1. First trigger is allowed
        mock_time.return_value = 1000.0
        response = client.post("/api/scrape?mock_eval=false")
        assert response.status_code == 200
        assert response.json()["status"] == "triggered"

        # 2. Second trigger within 60s -> HTTP 429
        mock_time.return_value = 1030.0
        response = client.post("/api/scrape?mock_eval=false")
        assert response.status_code == 429
        assert "Too many requests" in response.json()["message"]

        # 3. Third trigger after 60s -> HTTP 200
        mock_time.return_value = 1065.0
        response = client.post("/api/scrape?mock_eval=false")
        assert response.status_code == 200
        assert response.json()["status"] == "triggered"

        # 4. Mock trigger (mock_eval=true and MOCK_SCRAPER=true) -> bypasses
        monkeypatch.setenv("MOCK_SCRAPER", "true")
        mock_time.return_value = 1070.0
        response = client.post("/api/scrape?mock_eval=true")
        assert response.status_code == 200
        assert response.json()["status"] == "triggered"


@pytest.mark.asyncio
async def test_cli_rate_limiter(tmp_path, monkeypatch):
    lock_file = tmp_path / ".last_trigger"
    monkeypatch.setenv("MOCK_SCRAPER", "false")

    with patch("src.cli.LOCK_FILE_PATH", str(lock_file)), \
         patch("src.cli.scrape_linkedin_jobs", return_value=[]), \
         patch("src.cli.database.init_db"), \
         patch("src.cli.database.add_job"), \
         patch("time.time") as mock_time:

        # 1. First run (mock_eval=False) -> allowed, creates lock file
        mock_time.return_value = 1000.0
        await run_search("QA", mock_eval=False)
        assert lock_file.exists()
        assert float(lock_file.read_text().strip()) == 1000.0

        # 2. Second run within 60s -> exits with 1
        mock_time.return_value = 1030.0
        with pytest.raises(SystemExit) as excinfo:
            await run_search("QA", mock_eval=False)
        assert excinfo.value.code == 1

        # 3. Third run after 60s -> allowed, updates lock file
        mock_time.return_value = 1065.0
        await run_search("QA", mock_eval=False)
        assert float(lock_file.read_text().strip()) == 1065.0

        # 4. Mock run (mock_eval=True, MOCK_SCRAPER=true) -> bypasses rate limiter and does not write lock file
        monkeypatch.setenv("MOCK_SCRAPER", "true")
        if lock_file.exists():
            lock_file.unlink()
        mock_time.return_value = 1070.0
        await run_search("QA", mock_eval=True)
        assert not lock_file.exists()
