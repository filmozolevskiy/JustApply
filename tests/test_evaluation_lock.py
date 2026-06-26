import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src import db as database
from src.cli.cli import run_backfill, run_search
from src.core.evaluation_lock import (
    EvaluationLockError,
    assert_evaluation_lock_clear,
    cancel_in_flight_batches,
    get_evaluation_lock_status,
    is_evaluation_lock_active,
)
from src.db import batch_jobs
from src.web.server import app

client = TestClient(app)


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database.connection, "DB_PATH", str(db_path))
    database.init_db(str(db_path))
    return db_path


def test_lock_inactive_when_all_batches_terminal(tmp_db):
    batch_jobs.create_batch_job(
        batch_name="batches/done",
        display_name="done",
        state="JOB_STATE_SUCCEEDED",
        kind="search",
        job_ids=[1, 2],
        db_path=str(tmp_db),
    )

    status = get_evaluation_lock_status(db_path=str(tmp_db))
    assert status["active"] is False
    assert status["jobCount"] == 0
    assert status["batchCount"] == 0
    assert is_evaluation_lock_active(db_path=str(tmp_db)) is False
    assert_evaluation_lock_clear(db_path=str(tmp_db))


def test_lock_active_when_non_terminal_batch_exists(tmp_db):
    batch_jobs.create_batch_job(
        batch_name="batches/running",
        display_name="running",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[10, 11, 12],
        db_path=str(tmp_db),
    )

    status = get_evaluation_lock_status(db_path=str(tmp_db))
    assert status["active"] is True
    assert status["jobCount"] == 3
    assert status["batchCount"] == 1

    with pytest.raises(EvaluationLockError) as exc_info:
        assert_evaluation_lock_clear(db_path=str(tmp_db))
    assert exc_info.value.job_count == 3


@pytest.mark.asyncio
async def test_cancel_in_flight_batches_calls_gemini_and_marks_cancelled(tmp_db):
    batch_jobs.create_batch_job(
        batch_name="batches/a",
        display_name="a",
        state="JOB_STATE_PENDING",
        kind="search",
        job_ids=[1],
        db_path=str(tmp_db),
    )
    batch_jobs.create_batch_job(
        batch_name="batches/b",
        display_name="b",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[2],
        db_path=str(tmp_db),
    )

    mock_client = MagicMock()
    cancelled = await cancel_in_flight_batches(client=mock_client, db_path=str(tmp_db))

    assert cancelled == 2
    assert mock_client.batches.cancel.call_count == 2
    mock_client.batches.cancel.assert_any_call(name="batches/a")
    mock_client.batches.cancel.assert_any_call(name="batches/b")
    assert is_evaluation_lock_active(db_path=str(tmp_db)) is False


@pytest.mark.asyncio
async def test_cancel_without_client_still_marks_batches_cancelled(tmp_db):
    batch_jobs.create_batch_job(
        batch_name="batches/local",
        display_name="local",
        state="JOB_STATE_PENDING",
        kind="search",
        job_ids=[5],
        db_path=str(tmp_db),
    )

    cancelled = await cancel_in_flight_batches(client=None, db_path=str(tmp_db))

    assert cancelled == 1
    row = batch_jobs.get_batch_job(1, db_path=str(tmp_db))
    assert row["state"] == "JOB_STATE_CANCELLED"
    assert is_evaluation_lock_active(db_path=str(tmp_db)) is False


def test_api_evaluation_lock_status(tmp_db, monkeypatch):
    monkeypatch.setattr(
        "src.web.server.batch_jobs_db.list_in_flight_batch_jobs",
        lambda db_path=None: [
            {"id": 1, "batchName": "batches/x", "jobIds": [1, 2]},
        ],
    )
    monkeypatch.setattr(
        "src.web.server.batch_jobs_db.get_in_flight_job_ids",
        lambda db_path=None: {1, 2},
    )

    response = client.get("/api/evaluation-lock")
    assert response.status_code == 200
    body = response.json()
    assert body["active"] is True
    assert body["jobCount"] == 2
    assert body["batchCount"] == 1


def test_api_search_blocked_when_lock_active(monkeypatch):
    monkeypatch.setattr(
        "src.web.server.batch_jobs_db.list_in_flight_batch_jobs",
        lambda db_path=None: [{"id": 1, "batchName": "batches/x", "jobIds": [1]}],
    )
    monkeypatch.setattr(
        "src.web.server.batch_jobs_db.get_in_flight_job_ids",
        lambda db_path=None: {1},
    )

    payload = {
        "query": "QA",
        "search_regions": [{"country": "US", "region": "California"}],
        "per_region_limit": 200,
        "platform": "brightdata_linkedin",
        "active_resume": "general_cv.md",
        "mock_eval": False,
        "remote_type": "any",
        "seniority": "any",
        "salary": "",
        "company_size": "any",
        "countries": "us",
        "time_range": "any",
    }
    response = client.post("/api/search", json=payload)
    assert response.status_code == 409
    assert "Evaluation in progress" in response.json()["message"]


@pytest.mark.asyncio
async def test_cli_search_refuses_when_lock_active(tmp_db, monkeypatch):
    batch_jobs.create_batch_job(
        batch_name="batches/block",
        display_name="block",
        state="JOB_STATE_RUNNING",
        kind="search",
        job_ids=[99],
        db_path=str(tmp_db),
    )

    with patch("src.pipelines.scrape_linkedin_jobs", return_value=[]), \
         patch("src.pipelines.database.init_db"), \
         pytest.raises(SystemExit) as exc_info:
        await run_search("QA", mock_eval=False)

    assert exc_info.value.code == 1


@pytest.mark.asyncio
async def test_cli_backfill_refuses_when_lock_active(tmp_db, monkeypatch):
    batch_jobs.create_batch_job(
        batch_name="batches/block",
        display_name="block",
        state="JOB_STATE_PENDING",
        kind="backfill",
        job_ids=[7, 8],
        db_path=str(tmp_db),
    )

    with pytest.raises(SystemExit) as exc_info:
        await run_backfill()

    assert exc_info.value.code == 1


def test_dashboard_html_has_evaluation_lock_ui():
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path, encoding="utf-8") as handle:
        html = handle.read()

    assert 'id="evaluation-lock-indicator"' in html
    assert "Assessing" in html
    assert "cancelEvaluation" in html
    assert "/api/evaluation-lock" in html
