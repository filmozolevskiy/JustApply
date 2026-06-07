import os
import sys
import json
import pytest

# Add root directory to path to import database
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database import init_db, get_jobs, update_job_status, add_job

def test_database_lifecycle(tmp_path):
    test_db = tmp_path / "test_job_tracker.db"
    db_str = str(test_db)
    
    # 1. Initialize and Seed
    init_db(db_str)
    assert test_db.exists()
    
    # Check default seeded jobs (should be 6)
    jobs = get_jobs(db_str)
    assert len(jobs) == 6
    
    # Verify first job data structure
    first_job = next(j for j in jobs if j["id"] == 1)
    assert first_job["title"] == "Senior QA Automation Engineer"
    assert first_job["company"] == "TechCorp"
    assert isinstance(first_job["strengths"], list)
    assert "Highly proficient in Python & Pytest" in first_job["strengths"]
    assert isinstance(first_job["contacts"], list)
    assert first_job["contacts"][0]["name"] == "Jane Doe"
    assert first_job["shouldProceed"] is True
    
    # 2. Update status
    updated = update_job_status(1, "applied", db_str)
    assert updated is not None
    assert updated["status"] == "applied"
    
    # Verify update in fetched list
    jobs_after_update = get_jobs(db_str)
    job_1 = next(j for j in jobs_after_update if j["id"] == 1)
    assert job_1["status"] == "applied"
    
    # 3. Add new job
    new_job_data = {
        "title": "Staff Engineer",
        "company": "Google",
        "status": "sourced",
        "strengths": ["Testing", "Scaling"],
        "shouldProceed": True
    }
    new_id = add_job(new_job_data, db_str)
    assert new_id is not None
    assert new_id > 6
    
    jobs_after_add = get_jobs(db_str)
    assert len(jobs_after_add) == 7
    added_job = next(j for j in jobs_after_add if j["id"] == new_id)
    assert added_job["title"] == "Staff Engineer"
    assert added_job["company"] == "Google"
    assert added_job["status"] == "sourced"
    assert added_job["strengths"] == ["Testing", "Scaling"]
    assert added_job["shouldProceed"] is True

def test_update_nonexistent_job(tmp_path):
    test_db = tmp_path / "test_job_tracker.db"
    db_str = str(test_db)
    init_db(db_str)
    
    res = update_job_status(999, "applied", db_str)
    assert res is None
