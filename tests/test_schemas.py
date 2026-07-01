import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src import db as database


@pytest.fixture()
def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    database.init_db(db_path)
    return db_path


# --- Contact schema ---

def test_contact_schema_apify_format():
    from src.schemas import Contact
    c = Contact(name="Ivan Petrov", title="Engineer", url="https://linkedin.com/in/ivan",
                contacted=False, russian_speaker=True)
    assert c.russian_speaker is True
    assert c.title == "Engineer"
    assert c.url == "https://linkedin.com/in/ivan"


def test_contact_schema_seed_format():
    from src.schemas import Contact
    c = Contact(name="Jane Doe", role="VP Engineering",
                linkedin="https://linkedin.com/in/janedoe", contacted=False)
    assert c.name == "Jane Doe"
    assert c.role == "VP Engineering"
    assert c.russian_speaker is False


def test_contact_schema_empty():
    from src.schemas import Contact
    c = Contact()
    assert c.name == ""
    assert c.contacted is False


def test_contact_schema_has_is_recruiter_field():
    from src.schemas import Contact
    c = Contact()
    assert c.is_recruiter is False
    c2 = Contact(is_recruiter=True)
    assert c2.is_recruiter is True


# --- Job schema ---

def test_job_schema_from_get_job_output(db):
    from src.schemas import Job
    job_id = database.add_job(
        {"title": "QA Engineer", "company": "Acme", "status": "sourced"},
        db_path=db,
    )
    job = database.get_job(job_id, db_path=db)
    assert isinstance(job, Job)
    assert job.title == "QA Engineer"
    assert job.company == "Acme"
    assert job.shouldProceed is False
    assert job.isRecruiter is False
    assert isinstance(job.contacts, list)
    assert isinstance(job.strengths, list)


def test_job_schema_all_seeded_rows_parse(db):
    from src.schemas import Job
    for job in database.get_jobs(db_path=db):
        assert isinstance(job, Job)
        assert job.id is not None


def test_job_schema_seed_contacts_parse_as_contact_models(db):
    jobs = database.get_jobs(db_path=db)
    job1 = next(j for j in jobs if j.id == 1)
    assert len(job1.contacts) == 2
    assert job1.contacts[0].name == "Jane Doe"
    assert job1.contacts[0].role == "VP Engineering"


def test_job_schema_enrichment_note_defaults_to_empty():
    from src.schemas import Job
    job = Job(title="QA", company="Acme")
    assert job.enrichmentNote == ""


def test_job_schema_enrichment_note_round_trip(db):
    job_id = database.add_job(
        {"title": "QA Engineer", "company": "Acme", "status": "sourced"},
        db_path=db,
    )
    job = database.get_job(job_id, db_path=db)
    assert job.enrichmentNote == ""


def test_job_schema_has_recruiter_outreach_template_field():
    from src.schemas import Job
    job = Job(title="QA", company="Acme")
    assert job.recruiterOutreachTemplate == ""
    job2 = Job(title="QA", company="Acme", recruiterOutreachTemplate="Hello ______,\n\nAcme is looking for a QA. Fit line.\n\nCTA.")
    assert job2.recruiterOutreachTemplate == "Hello ______,\n\nAcme is looking for a QA. Fit line.\n\nCTA."


def test_job_schema_has_russian_speaker_outreach_template_field():
    from src.schemas import Job
    job = Job(title="QA", company="Acme")
    assert job.russianSpeakerOutreachTemplate == ""
    job2 = Job(title="QA", company="Acme", russianSpeakerOutreachTemplate="Hello ______,\n\nAcme is looking for a QA. Fit.\n\nRU CTA.")
    assert job2.russianSpeakerOutreachTemplate == "Hello ______,\n\nAcme is looking for a QA. Fit.\n\nRU CTA."


def test_job_schema_outreach_templates_round_trip(db):
    from src.db import enrich_job
    job_id = database.add_job(
        {"title": "QA Engineer", "company": "Acme", "status": "sourced"},
        db_path=db,
    )
    recruiter_tmpl = "Hello ______,\n\nAcme is looking for a QA. My experience align well with the requirements.\n\nI would be grateful to connect and share my CV."
    russian_tmpl = "Hello ______,\n\nAcme is looking for a QA. My experience align well with the requirements.\n\nI'd be grateful if you could refer me for the role."
    enrich_job(
        job_id, [], recruiter_tmpl,
        recruiter_template=recruiter_tmpl,
        russian_speaker_template=russian_tmpl,
        db_path=db,
    )
    job = database.get_job(job_id, db_path=db)
    assert job.recruiterOutreachTemplate == recruiter_tmpl
    assert job.russianSpeakerOutreachTemplate == russian_tmpl
