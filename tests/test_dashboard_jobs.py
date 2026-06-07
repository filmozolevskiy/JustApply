import os
import sys
import pytest
from fastapi.testclient import TestClient

# Add root directory to path to import prototype_dashboard and database
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import database
import prototype_dashboard
from prototype_dashboard import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    # Create a temporary database path
    test_db = tmp_path / "test_job_tracker.db"
    test_db_str = str(test_db)
    
    # Patch the DB_PATH in database
    monkeypatch.setattr(database, "DB_PATH", test_db_str)
    
    # Initialize the test DB with seed data
    database.init_db(test_db_str)
    
    yield test_db_str

def test_get_jobs_endpoint():
    response = client.get("/api/jobs")
    assert response.status_code == 200
    jobs = response.json()
    # Should get 6 seeded jobs
    assert len(jobs) == 6
    # Check shape of one job
    job1 = next(j for j in jobs if j["id"] == 1)
    assert job1["title"] == "Senior QA Automation Engineer"
    assert job1["company"] == "TechCorp"
    assert job1["status"] == "sourced"
    assert job1["shouldProceed"] is True
    assert isinstance(job1["strengths"], list)
    assert isinstance(job1["contacts"], list)

def test_put_job_status_endpoint():
    # Verify initial status is sourced
    response = client.get("/api/jobs")
    jobs = response.json()
    job1 = next(j for j in jobs if j["id"] == 1)
    assert job1["status"] == "sourced"
    
    # Update status to evaluating
    put_response = client.put("/api/jobs/1/status", json={"status": "evaluating"})
    assert put_response.status_code == 200
    updated_job = put_response.json()
    assert updated_job["status"] == "evaluating"
    
    # Verify in subsequent GET request
    response = client.get("/api/jobs")
    jobs = response.json()
    job1_updated = next(j for j in jobs if j["id"] == 1)
    assert job1_updated["status"] == "evaluating"

def test_put_job_status_nonexistent():
    put_response = client.put("/api/jobs/999/status", json={"status": "evaluating"})
    assert put_response.status_code == 404
    assert put_response.json() == {"message": "Job not found"}

def test_put_job_comment_endpoint():
    # Verify initial comment is whatever was seeded
    response = client.get("/api/jobs")
    jobs = response.json()
    job1 = next(j for j in jobs if j["id"] == 1)
    assert job1["comment"] == "Excellent match. Framework matches 100%."
    
    # Update comment
    put_response = client.put("/api/jobs/1/comment", json={"comment": "Verified API testing framework."})
    assert put_response.status_code == 200
    updated_job = put_response.json()
    assert updated_job["comment"] == "Verified API testing framework."
    
    # Verify via subsequent GET
    response = client.get("/api/jobs")
    jobs = response.json()
    job1_updated = next(j for j in jobs if j["id"] == 1)
    assert job1_updated["comment"] == "Verified API testing framework."

def test_put_job_comment_nonexistent():
    put_response = client.put("/api/jobs/999/comment", json={"comment": "No job here"})
    assert put_response.status_code == 404
    assert put_response.json() == {"message": "Job not found"}
