import os
import sys
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import database
import src.server as server_module
from src.server import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_job_tracker.db"
    test_db_str = str(test_db)

    monkeypatch.setattr(database, "DB_PATH", test_db_str)

    database.init_db(test_db_str)

    yield test_db_str


def test_get_jobs_endpoint():
    response = client.get("/api/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 7
    job1 = next(j for j in jobs if j["id"] == 1)
    assert job1["title"] == "Senior QA Automation Engineer"
    assert job1["company"] == "TechCorp"
    assert job1["status"] == "sourced"
    assert job1["shouldProceed"] is True
    assert isinstance(job1["strengths"], list)
    assert isinstance(job1["contacts"], list)

    job7 = next(j for j in jobs if j["id"] == 7)
    assert job7["title"] == "QA Automation Contractor"
    assert job7["company"] == "Fuze HR Solutions"
    assert job7["isRecruiter"] is True
    assert job7["shouldProceed"] is False
    assert job7["salary"] == "$70 - $80 / hr"
    assert "Posted by a recruiting agency/staffing firm" in job7["gaps"]


def test_put_job_status_endpoint():
    response = client.get("/api/jobs")
    jobs = response.json()
    job1 = next(j for j in jobs if j["id"] == 1)
    assert job1["status"] == "sourced"

    put_response = client.put("/api/jobs/1/status", json={"status": "enriching"})
    assert put_response.status_code == 200
    updated_job = put_response.json()
    assert updated_job["status"] == "enriching"

    response = client.get("/api/jobs")
    jobs = response.json()
    job1_updated = next(j for j in jobs if j["id"] == 1)
    assert job1_updated["status"] == "enriching"


def test_put_job_status_nonexistent():
    put_response = client.put("/api/jobs/999/status", json={"status": "enriching"})
    assert put_response.status_code == 404
    assert put_response.json() == {"message": "Job not found"}


def test_put_job_comment_endpoint():
    response = client.get("/api/jobs")
    jobs = response.json()
    job1 = next(j for j in jobs if j["id"] == 1)
    assert job1["comment"] == "Excellent match. Framework matches 100%."

    put_response = client.put("/api/jobs/1/comment", json={"comment": "Verified API testing framework."})
    assert put_response.status_code == 200
    updated_job = put_response.json()
    assert updated_job["comment"] == "Verified API testing framework."

    response = client.get("/api/jobs")
    jobs = response.json()
    job1_updated = next(j for j in jobs if j["id"] == 1)
    assert job1_updated["comment"] == "Verified API testing framework."


def test_put_job_comment_nonexistent():
    put_response = client.put("/api/jobs/999/comment", json={"comment": "No job here"})
    assert put_response.status_code == 404
    assert put_response.json() == {"message": "Job not found"}


def test_post_job_enrich_endpoint():
    from unittest.mock import patch
    
    with patch("src.server.run_enrichment_task") as mock_enrich_task:
        response = client.post("/api/jobs/1/enrich")
        assert response.status_code == 200
        assert response.json() == {"status": "enriching", "job_id": 1}
        
        # Verify status changed to enriching
        get_response = client.get("/api/jobs")
        jobs = get_response.json()
        job1 = next(j for j in jobs if j["id"] == 1)
        assert job1["status"] == "enriching"
        assert mock_enrich_task.called


def test_post_job_enrich_nonexistent():
    response = client.post("/api/jobs/999/enrich")
    assert response.status_code == 404
    assert response.json() == {"message": "Job not found"}


# --- run_enrichment_task integration ---

@pytest.mark.asyncio
async def test_run_enrichment_task_writes_enriched_results(setup_test_db):
    from src.server import run_enrichment_task
    mock_contacts = [{"name": "Test Contact", "url": "https://linkedin.com/in/test", "contacted": False, "russian_speaker": False}]
    with patch("src.pipelines.source_contacts", new=AsyncMock(return_value=mock_contacts)), \
         patch("src.pipelines.generate_outreach_for_job", new=AsyncMock(return_value="Hello")), \
         patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        await run_enrichment_task(1)
    job = database.get_job(1)
    assert job["status"] == "enriched"
    assert len(job["contacts"]) == 1
    assert job["contacts"][0]["name"] == "Test Contact"
    assert job["outreachMessage"] != ""


@pytest.mark.asyncio
async def test_run_enrichment_task_noop_for_missing_job():
    from src.server import run_enrichment_task
    # Should return without raising for a non-existent job ID
    await run_enrichment_task(99999)
