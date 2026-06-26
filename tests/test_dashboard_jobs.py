import os
import sys
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import db as database
import src.db.connection as _db_connection
import src.web.server as server_module
from src.web.server import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_just_apply.db"
    test_db_str = str(test_db)

    monkeypatch.setattr(_db_connection, "DB_PATH", test_db_str)

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
    assert job1["status"] == "matched"
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
    assert job1["status"] == "matched"

    put_response = client.put("/api/jobs/1/status", json={"status": "accepted"})
    assert put_response.status_code == 200
    updated_job = put_response.json()
    assert updated_job["status"] == "accepted"

    response = client.get("/api/jobs")
    jobs = response.json()
    job1_updated = next(j for j in jobs if j["id"] == 1)
    assert job1_updated["status"] == "accepted"


def test_put_job_status_nonexistent():
    put_response = client.put("/api/jobs/999/status", json={"status": "accepted"})
    assert put_response.status_code == 404
    assert put_response.json() == {"message": "Job not found"}


def test_put_job_status_rejects_obsolete_sourced():
    put_response = client.put("/api/jobs/1/status", json={"status": "sourced"})
    assert put_response.status_code == 422


def test_put_job_status_rejects_obsolete_enriching():
    put_response = client.put("/api/jobs/1/status", json={"status": "enriching"})
    assert put_response.status_code == 422


def test_put_job_status_rejects_obsolete_enriched():
    put_response = client.put("/api/jobs/1/status", json={"status": "enriched"})
    assert put_response.status_code == 422


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
    with patch("src.web.server.run_enrichment_task_with_logs") as mock_enrich_task:
        response = client.post("/api/jobs/1/enrich")
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["job_id"] == 1

        # Verify status changed to accepted (enrichment runs in place)
        get_response = client.get("/api/jobs")
        jobs = get_response.json()
        job1 = next(j for j in jobs if j["id"] == 1)
        assert job1["status"] == "accepted"
        assert mock_enrich_task.called


def test_post_job_enrich_nonexistent():
    response = client.post("/api/jobs/999/enrich")
    assert response.status_code == 404
    assert response.json() == {"message": "Job not found"}


# --- run_enrichment_task_with_logs integration ---

@pytest.mark.asyncio
async def test_run_enrichment_task_with_logs_writes_enriched_results(setup_test_db):
    from src.web.server import run_enrichment_task_with_logs, TaskState, active_tasks
    from src.core.enrichment.coordinator import begin_enrichment
    import uuid
    begin_enrichment(1, setup_test_db)
    task_id = str(uuid.uuid4())
    state = TaskState({"job_id": 1})
    active_tasks[task_id] = state

    mock_contacts = [{"name": "Test Contact", "url": "https://linkedin.com/in/test", "contacted": False, "russian_speaker": False}]
    recruiter_note = "Hello ______,\n\nAcme is looking for a QA. My experience align well with the requirements.\n\nI would be grateful to connect and share my CV."
    mock_templates = {"recruiter": recruiter_note, "russian_speaker": ""}
    with patch("src.pipelines.source_contacts", new=AsyncMock(return_value=mock_contacts)), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=mock_templates)):
        await run_enrichment_task_with_logs(task_id, 1)

    job = database.get_job(1)
    assert job.status == "accepted"
    assert len(job.contacts) == 1
    assert job.contacts[0].name == "Test Contact"
    assert job.recruiterOutreachTemplate == recruiter_note


@pytest.mark.asyncio
async def test_run_enrichment_task_with_logs_noop_for_missing_job():
    from src.web.server import run_enrichment_task_with_logs, TaskState, active_tasks
    import uuid
    task_id = str(uuid.uuid4())
    state = TaskState({"job_id": 99999})
    active_tasks[task_id] = state
    # Should complete without raising for a non-existent job ID
    await run_enrichment_task_with_logs(task_id, 99999)


# --- PUT /api/jobs/{id}/template ---

def test_put_template_endpoint_saves_recruiter_template():
    response = client.put("/api/jobs/1/template", json={"audience": "recruiter", "template": "Edited recruiter draft"})
    assert response.status_code == 200
    job = response.json()
    assert job["recruiterOutreachTemplate"] == "Edited recruiter draft"
    # Persists on GET
    get_response = client.get("/api/jobs")
    jobs = get_response.json()
    job1 = next(j for j in jobs if j["id"] == 1)
    assert job1["recruiterOutreachTemplate"] == "Edited recruiter draft"


def test_put_template_endpoint_saves_russian_speaker_template():
    response = client.put("/api/jobs/1/template", json={"audience": "russian_speaker", "template": "Edited RS draft"})
    assert response.status_code == 200
    job = response.json()
    assert job["russianSpeakerOutreachTemplate"] == "Edited RS draft"


def test_put_template_endpoint_audiences_do_not_overwrite_each_other():
    client.put("/api/jobs/1/template", json={"audience": "recruiter", "template": "R draft"})
    client.put("/api/jobs/1/template", json={"audience": "russian_speaker", "template": "RS draft"})
    client.put("/api/jobs/1/template", json={"audience": "recruiter", "template": "R draft v2"})
    get_response = client.get("/api/jobs")
    jobs = get_response.json()
    job1 = next(j for j in jobs if j["id"] == 1)
    assert job1["recruiterOutreachTemplate"] == "R draft v2"
    assert job1["russianSpeakerOutreachTemplate"] == "RS draft"


def test_put_template_endpoint_nonexistent_job():
    response = client.put("/api/jobs/999/template", json={"audience": "recruiter", "template": "anything"})
    assert response.status_code == 404
    assert response.json() == {"message": "Job not found"}


@pytest.mark.asyncio
async def test_enrichment_task_aborts_when_pipeline_returns_none(setup_test_db):
    """Failed enrichment task leaves job in Accepted (abort is a no-op)."""
    from src.web.server import run_enrichment_task_with_logs, TaskState, active_tasks
    from src.core.enrichment.coordinator import begin_enrichment
    import uuid

    begin_enrichment(1, setup_test_db)
    task_id = str(uuid.uuid4())
    state = TaskState({"job_id": 1})
    active_tasks[task_id] = state

    with patch("src.service.just_apply.run_enrichment_pipeline", new=AsyncMock(return_value=None)):
        await run_enrichment_task_with_logs(task_id, 1)

    job = database.get_job(1, setup_test_db)
    assert job.status == "accepted"
    assert state.status == "failed"


def test_post_job_enrich_returns_server_job_snapshot():
    with patch("src.web.server.run_enrichment_task_with_logs"):
        response = client.post("/api/jobs/1/enrich")
        assert response.status_code == 200
        data = response.json()
        assert data["job"]["status"] == "accepted"
