"""Region-scoped scrape backend: /api/search validation and Bright Data payload."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import db as database
import src.db.connection as _db_connection
from src.core.regions import clamp_per_region_limit, validate_search_regions
from src.core.scraper import scrape_linkedin_jobs
from src.web.server import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MOCK_SCRAPER", "true")
    test_db = tmp_path / "test_just_apply.db"
    test_db_str = str(test_db)
    monkeypatch.setattr(_db_connection, "DB_PATH", test_db_str)
    database.init_db(test_db_str)
    yield test_db_str


def _valid_payload(**overrides):
    payload = {
        "query": "QA Engineer",
        "search_regions": [{"country": "US", "region": "California"}],
        "per_region_limit": 200,
        "platform": "brightdata_linkedin",
        "active_resume": "qa.md",
        "mock_eval": True,
        "remote_type": "any",
        "seniority": "any",
        "salary": "",
        "company_size": "any",
        "countries": "us",
        "time_range": "any",
    }
    payload.update(overrides)
    return payload


def test_clamp_per_region_limit():
    assert clamp_per_region_limit(10) == 25
    assert clamp_per_region_limit(25) == 25
    assert clamp_per_region_limit(200) == 200
    assert clamp_per_region_limit(1000) == 1000
    assert clamp_per_region_limit(1500) == 1000


def test_validate_search_regions_rejects_remote():
    with pytest.raises(ValueError, match="Remote"):
        validate_search_regions(["US"], [("US", "Remote")])


def test_validate_search_regions_rejects_unknown():
    with pytest.raises(ValueError, match="Unknown region"):
        validate_search_regions(["US"], [("US", "Atlantis")])


def test_validate_search_regions_rejects_country_with_no_regions():
    with pytest.raises(ValueError, match="at least one Search Region"):
        validate_search_regions(["US", "CA"], [("US", "California")])


def test_api_search_accepts_valid_regions_and_triggers():
    with patch("src.web.server.run_scraping_task"):
        response = client.post("/api/search", json=_valid_payload())
    assert response.status_code == 200
    assert response.json()["status"] == "triggered"
    assert response.json()["task_id"]


def test_api_search_rejects_remote_region():
    payload = _valid_payload(search_regions=[{"country": "US", "region": "Remote"}])
    response = client.post("/api/search", json=payload)
    assert response.status_code == 422


def test_api_search_rejects_unknown_region():
    payload = _valid_payload(search_regions=[{"country": "US", "region": "Narnia"}])
    response = client.post("/api/search", json=payload)
    assert response.status_code == 422


def test_api_search_rejects_country_without_regions():
    payload = _valid_payload(
        countries="us,ca",
        search_regions=[{"country": "US", "region": "California"}],
    )
    response = client.post("/api/search", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_brightdata_payload_one_item_per_region(monkeypatch):
    monkeypatch.setenv("MOCK_SCRAPER", "false")
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "fake_key")

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 500
    mock_post_resp.text = "fail fast"

    captured_payload = []

    async def capture_post(url, **kwargs):
        captured_payload.append(kwargs.get("json"))
        return mock_post_resp

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=capture_post):
        with pytest.raises(Exception):
            await scrape_linkedin_jobs(
                query="QA Engineer",
                search_regions=[
                    ("US", "California"),
                    ("US", "New York"),
                    ("CA", "Ontario"),
                ],
                per_region_limit=150,
                log_func=print,
            )

    assert len(captured_payload) == 1
    payload = captured_payload[0]
    assert len(payload) == 3
    assert payload[0] == {
        "keyword": "QA Engineer",
        "location": "California",
        "country": "US",
        "limit_per_input": 150,
    }
    assert payload[1] == {
        "keyword": "QA Engineer",
        "location": "New York",
        "country": "US",
        "limit_per_input": 150,
    }
    assert payload[2] == {
        "keyword": "QA Engineer",
        "location": "Ontario",
        "country": "CA",
        "limit_per_input": 150,
    }


@pytest.mark.asyncio
async def test_brightdata_payload_clamps_per_region_limit(monkeypatch):
    monkeypatch.setenv("MOCK_SCRAPER", "false")
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "fake_key")

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 500
    mock_post_resp.text = "fail fast"

    captured_payload = []

    async def capture_post(url, **kwargs):
        captured_payload.append(kwargs.get("json"))
        return mock_post_resp

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=capture_post):
        with pytest.raises(Exception):
            await scrape_linkedin_jobs(
                query="QA",
                search_regions=[("US", "Texas")],
                per_region_limit=10,
                log_func=print,
            )

    assert captured_payload[0][0]["limit_per_input"] == 25
