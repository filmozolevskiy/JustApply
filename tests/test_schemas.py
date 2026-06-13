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


# --- Job schema ---

def test_job_schema_from_get_job_output(db):
    from src.schemas import Job
    job_id = database.add_job(
        {"title": "QA Engineer", "company": "Acme", "status": "sourced"},
        db_path=db,
    )
    row = database.get_job(job_id, db_path=db)
    job = Job(**row)
    assert job.title == "QA Engineer"
    assert job.company == "Acme"
    assert job.shouldProceed is False
    assert job.isRecruiter is False
    assert isinstance(job.contacts, list)
    assert isinstance(job.strengths, list)


def test_job_schema_all_seeded_rows_parse(db):
    from src.schemas import Job
    for row in database.get_jobs(db_path=db):
        job = Job(**row)
        assert job.id is not None


def test_job_schema_seed_contacts_parse_as_contact_models(db):
    from src.schemas import Job
    jobs = database.get_jobs(db_path=db)
    job1 = next(j for j in jobs if j["id"] == 1)
    parsed = Job(**job1)
    assert len(parsed.contacts) == 2
    assert parsed.contacts[0].name == "Jane Doe"
    assert parsed.contacts[0].role == "VP Engineering"
