import os
import sys
import json
import pytest

# Add root directory to path to import database
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.db import init_db, get_jobs, update_job_status, add_job, VALID_STATUSES, start_enrichment, enrich_job

def test_database_lifecycle(tmp_path):
    test_db = tmp_path / "test_just_apply.db"
    db_str = str(test_db)
    
    # 1. Initialize and Seed
    init_db(db_str)
    assert test_db.exists()
    
    # Check default seeded jobs (should be 7)
    jobs = get_jobs(db_str)
    assert len(jobs) == 7
    
    # Verify first job data structure
    first_job = next(j for j in jobs if j.id == 1)
    assert first_job.title == "Senior QA Automation Engineer"
    assert first_job.company == "TechCorp"
    assert isinstance(first_job.strengths, list)
    assert "Highly proficient in Python & Pytest" in first_job.strengths
    assert isinstance(first_job.contacts, list)
    assert first_job.contacts[0].name == "Jane Doe"
    assert first_job.shouldProceed is True
    
    # 2. Update status
    updated = update_job_status(1, "applied", db_str)
    assert updated is not None
    assert updated.status == "applied"
    
    # Verify update in fetched list
    jobs_after_update = get_jobs(db_str)
    job_1 = next(j for j in jobs_after_update if j.id == 1)
    assert job_1.status == "applied"
    
    # 3. Add new job
    new_job_data = {
        "title": "Staff Engineer",
        "company": "Google",
        "status": "found",
        "strengths": ["Testing", "Scaling"],
        "shouldProceed": True
    }
    new_id = add_job(new_job_data, db_str)
    assert new_id is not None
    assert new_id > 7

    jobs_after_add = get_jobs(db_str)
    assert len(jobs_after_add) == 8
    added_job = next(j for j in jobs_after_add if j.id == new_id)
    assert added_job.title == "Staff Engineer"
    assert added_job.company == "Google"
    assert added_job.status == "found"
    assert added_job.strengths == ["Testing", "Scaling"]
    assert added_job.shouldProceed is True


def test_add_job_persists_company_url(tmp_path):
    db_str = str(tmp_path / "test_just_apply.db")
    init_db(db_str)

    job_id = add_job({
        "title": "Product Application Engineer",
        "company": "Trane Technologies",
        "companyUrl": "https://www.linkedin.com/company/tranetechnologies?trk=public_jobs_topcard-org-name",
    }, db_str)

    job = next(j for j in get_jobs(db_str) if j.id == job_id)
    assert job.companyUrl == (
        "https://www.linkedin.com/company/tranetechnologies?trk=public_jobs_topcard-org-name"
    )


def test_update_nonexistent_job(tmp_path):
    test_db = tmp_path / "test_just_apply.db"
    db_str = str(test_db)
    init_db(db_str)
    
    res = update_job_status(999, "applied", db_str)
    assert res is None

def test_update_job_comment(tmp_path):
    test_db = tmp_path / "test_just_apply.db"
    db_str = str(test_db)
    init_db(db_str)
    
    from src.db import update_job_comment

    # Verify initial comment of job 1
    jobs = get_jobs(db_str)
    job1 = next(j for j in jobs if j.id == 1)
    assert job1.comment == "Excellent match. Framework matches 100%."
    
    # Update comment
    new_comment = "New test comment here"
    updated = update_job_comment(1, new_comment, db_str)
    assert updated is not None
    assert updated.comment == new_comment
    
    # Verify persistence
    jobs_after = get_jobs(db_str)
    job1_after = next(j for j in jobs_after if j.id == 1)
    assert job1_after.comment == new_comment

def test_update_job_comment_nonexistent(tmp_path):
    test_db = tmp_path / "test_just_apply.db"
    db_str = str(test_db)
    init_db(db_str)
    
    from src.db import update_job_comment
    res = update_job_comment(999, "No comment", db_str)
    assert res is None


def test_update_job_status_invalid_status(tmp_path):
    test_db = tmp_path / "test_just_apply.db"
    db_str = str(test_db)
    init_db(db_str)

    with pytest.raises(ValueError, match="Invalid status"):
        update_job_status(1, "banana", db_str)

    # Job status must be unchanged
    jobs = get_jobs(db_str)
    job1 = next(j for j in jobs if j.id == 1)
    assert job1.status == "found"


def test_get_jobs_json_roundtrip(tmp_path):
    test_db = tmp_path / "test_just_apply.db"
    db_str = str(test_db)
    init_db(db_str)

    new_id = add_job({
        "title": "ML Engineer",
        "company": "Acme",
        "strengths": ["Python", "PyTorch"],
        "gaps": ["No MLOps experience"],
        "contacts": [{"name": "Bob", "url": "https://linkedin.com/in/bob", "contacted": False}],
    }, db_str)

    jobs = get_jobs(db_str)
    added = next(j for j in jobs if j.id == new_id)
    assert added.strengths == ["Python", "PyTorch"]
    assert added.gaps == ["No MLOps experience"]
    assert isinstance(added.contacts, list)
    assert added.contacts[0].name == "Bob"


def test_job_exists(tmp_path):
    test_db = tmp_path / "test_just_apply.db"
    db_str = str(test_db)
    init_db(db_str)
    
    from src.db import job_exists
    
    # 1. Initially, TechCorp QA Engineer exists (from seed data)
    assert job_exists(
        title="Senior QA Automation Engineer",
        company="TechCorp",
        link="https://linkedin.com/jobs/123",
        db_path=db_str
    ) is True
    
    # 2. Check existence by link only
    assert job_exists(
        title="Different Title",
        company="Different Company",
        link="https://linkedin.com/jobs/123",
        db_path=db_str
    ) is True
    
    # 3. Check existence by title/company only
    assert job_exists(
        title="Senior QA Automation Engineer",
        company="TechCorp",
        link="https://some-other-link.com",
        db_path=db_str
    ) is True
    
    # 4. Non-existent job
    assert job_exists(
        title="Staff Engineer",
        company="Google",
        link="https://some-new-link.com",
        db_path=db_str
    ) is False


def test_start_enrichment(tmp_path):
    db_str = str(tmp_path / "test_just_apply.db")
    init_db(db_str)

    updated = start_enrichment(1, db_str)
    assert updated is not None
    assert updated.status == "accepted"

    job = next(j for j in get_jobs(db_str) if j.id == 1)
    assert job.status == "accepted"


def test_start_enrichment_nonexistent(tmp_path):
    db_str = str(tmp_path / "test_just_apply.db")
    init_db(db_str)
    assert start_enrichment(999, db_str) is None


def test_enrich_job_persists_contacts_and_message(tmp_path):
    db_str = str(tmp_path / "test_just_apply.db")
    init_db(db_str)

    contacts = [
        {"name": "Alice", "title": "Recruiter", "url": "https://linkedin.com/in/alice", "contacted": False, "russian_speaker": False}
    ]
    updated = enrich_job(1, contacts, "Hello Alice", db_path=db_str)

    assert updated is not None
    assert updated.status == "accepted"
    assert updated.contacts[0].name == contacts[0]["name"]
    assert updated.contacts[0].url == contacts[0]["url"]
    assert updated.outreachMessage == "Hello Alice"

    job = next(j for j in get_jobs(db_str) if j.id == 1)
    assert job.status == "accepted"
    assert job.outreachMessage == "Hello Alice"


def test_enrich_job_nonexistent(tmp_path):
    db_str = str(tmp_path / "test_just_apply.db")
    init_db(db_str)
    assert enrich_job(999, [], "", db_path=db_str) is None


def test_enrich_job_persists_enrichment_note(tmp_path):
    db_str = str(tmp_path / "test_just_apply.db")
    init_db(db_str)
    updated = enrich_job(1, [], "msg", enrichment_note="Apify failed: HTTP 403", db_path=db_str)
    assert updated is not None
    assert updated.enrichmentNote == "Apify failed: HTTP 403"


def test_enrich_job_clears_enrichment_note(tmp_path):
    db_str = str(tmp_path / "test_just_apply.db")
    init_db(db_str)
    enrich_job(1, [], "msg", enrichment_note="Previous failure", db_path=db_str)
    contacts = [{"name": "Alice", "url": "https://linkedin.com/in/alice", "contacted": False}]
    updated = enrich_job(1, contacts, "Hello", enrichment_note="", db_path=db_str)
    assert updated is not None
    assert updated.enrichmentNote == ""


def test_enrich_job_persists_both_outreach_templates(tmp_path):
    db_str = str(tmp_path / "test_just_apply.db")
    init_db(db_str)
    recruiter_tmpl = "Hello ______,\n\nAcme is looking for a QA. My experience align well with the requirements.\n\nI would be grateful to connect and share my CV."
    russian_tmpl = "Hello ______,\n\nAcme is looking for a QA. My experience align well with the requirements.\n\nI'd be grateful if you could refer me for the role."
    updated = enrich_job(
        1, [], recruiter_tmpl,
        recruiter_template=recruiter_tmpl,
        russian_speaker_template=russian_tmpl,
        db_path=db_str,
    )
    assert updated is not None
    assert updated.recruiterOutreachTemplate == recruiter_tmpl
    assert updated.russianSpeakerOutreachTemplate == russian_tmpl


def test_existing_recruiter_template_not_overwritten_by_legacy_message(tmp_path):
    db_str = str(tmp_path / "test_just_apply.db")
    init_db(db_str)
    recruiter_tmpl = "Hello ______,\n\nAcme is looking for a QA Lead. My experience align well with the requirements.\n\nI would be grateful to connect and share my CV."
    enrich_job(
        1, [], "legacy msg",
        recruiter_template=recruiter_tmpl,
        db_path=db_str,
    )
    job = next(j for j in get_jobs(db_str) if j.id == 1)
    assert job.recruiterOutreachTemplate == recruiter_tmpl


def test_update_outreach_template_persists_recruiter_template(tmp_path):
    from src.db.jobs import update_outreach_template
    db_str = str(tmp_path / "test_just_apply.db")
    init_db(db_str)
    new_text = "Hello ______,\nEdited recruiter draft."
    updated = update_outreach_template(1, "recruiter", new_text, db_path=db_str)
    assert updated is not None
    assert updated.recruiterOutreachTemplate == new_text
    # Persists across reads
    job = next(j for j in get_jobs(db_str) if j.id == 1)
    assert job.recruiterOutreachTemplate == new_text


def test_update_outreach_template_persists_russian_speaker_template(tmp_path):
    from src.db.jobs import update_outreach_template
    db_str = str(tmp_path / "test_just_apply.db")
    init_db(db_str)
    new_text = "Hello ______,\nEdited Russian speaker draft."
    updated = update_outreach_template(1, "russian_speaker", new_text, db_path=db_str)
    assert updated is not None
    assert updated.russianSpeakerOutreachTemplate == new_text
    job = next(j for j in get_jobs(db_str) if j.id == 1)
    assert job.russianSpeakerOutreachTemplate == new_text


def test_update_outreach_template_audiences_independent(tmp_path):
    from src.db.jobs import update_outreach_template
    db_str = str(tmp_path / "test_just_apply.db")
    init_db(db_str)
    enrich_job(
        1, [], "",
        recruiter_template="Recruiter draft",
        russian_speaker_template="Russian draft",
        db_path=db_str,
    )
    update_outreach_template(1, "recruiter", "Edited recruiter", db_path=db_str)
    job = next(j for j in get_jobs(db_str) if j.id == 1)
    assert job.recruiterOutreachTemplate == "Edited recruiter"
    assert job.russianSpeakerOutreachTemplate == "Russian draft"


def test_update_outreach_template_nonexistent_job(tmp_path):
    from src.db.jobs import update_outreach_template
    db_str = str(tmp_path / "test_just_apply.db")
    init_db(db_str)
    result = update_outreach_template(999, "recruiter", "anything", db_path=db_str)
    assert result is None
