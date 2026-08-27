"""Regression tests for Contact forward-compatible extra fields."""

import json

import pytest
from src.db import add_job, get_job, update_contact_status
from src.db.contacted_elsewhere import enrich_jobs_with_contacted_elsewhere
from src.db.job_model import parse_job_row
from src.schemas import Contact

SHARED_URL = "https://www.linkedin.com/in/ivan-petrov/"

@pytest.fixture
def db(tmp_path):
    from src.db import init_db

    db_path = str(tmp_path / "contact_schema.db")
    init_db(db_path)
    return db_path

def test_contact_preserves_apify_current_position(apify_normalized_contact):
    contact = Contact(**apify_normalized_contact)
    assert contact.currentPosition == "Senior Engineer at TechCorp"
    assert contact.location == "Montreal, QC"

def test_contact_json_round_trip_keeps_apify_extras(apify_normalized_contact):
    contact = Contact(**apify_normalized_contact)
    restored = Contact(**json.loads(contact.model_dump_json()))
    assert restored.currentPosition == apify_normalized_contact["currentPosition"]
    assert restored.location == apify_normalized_contact["location"]

def test_parse_job_row_deserializes_persisted_apify_extras(db, apify_normalized_contact):
    payload = {
        **apify_normalized_contact,
        "name": "Ivan Petrov",
        "url": SHARED_URL,
        "russian_speaker": True,
        "is_recruiter": False,
    }
    job_id = add_job(
        {
            "title": "Backend Dev",
            "company": "TechCorp",
            "status": "accepted",
            "contacts": [payload],
        },
        db_path=db,
    )

    job = get_job(job_id, db_path=db)
    contact = job.contacts[0]
    assert contact.currentPosition == "Senior Engineer at TechCorp"
    assert contact.location == "Montreal, QC"
    assert contact.russian_speaker is True

def test_update_contact_status_preserves_apify_extras(db, apify_normalized_contact):
    payload = {
        **apify_normalized_contact,
        "name": "Ivan Petrov",
        "url": SHARED_URL,
    }
    job_id = add_job(
        {
            "title": "Backend Dev",
            "company": "TechCorp",
            "status": "accepted",
            "contacts": [payload],
        },
        db_path=db,
    )

    updated = update_contact_status(job_id, 0, True, db_path=db)
    contact = updated.contacts[0]
    assert contact.contacted is True
    assert contact.currentPosition == "Senior Engineer at TechCorp"
    assert contact.model_dump().get("contacted_at")

def test_contacted_elsewhere_enrichment_preserves_apify_extras(db, apify_normalized_contact):
    source_id = add_job(
        {
            "title": "Prior Role",
            "company": "OldCo",
            "status": "accepted",
            "contacts": [
                {
                    "name": "Ivan Petrov",
                    "title": "Recruiter",
                    "url": SHARED_URL,
                    "contacted": True,
                    "contacted_at": "2026-02-01T08:00:00+00:00",
                }
            ],
        },
        db_path=db,
    )
    target_id = add_job(
        {
            "title": "New Role",
            "company": "NewCo",
            "status": "accepted",
            "contacts": [
                {
                    **apify_normalized_contact,
                    "name": "Ivan Petrov",
                    "url": SHARED_URL,
                }
            ],
        },
        db_path=db,
    )

    target = get_job(target_id, db_path=db)
    enriched = enrich_jobs_with_contacted_elsewhere([target], db_path=db)[0]
    contact = enriched.contacts[0]
    payload = contact.model_dump()

    assert payload["currentPosition"] == "Senior Engineer at TechCorp"
    assert payload["contactedElsewhere"]["jobId"] == source_id
    assert payload["contactedElsewhere"]["company"] == "OldCo"

def test_parse_job_row_from_raw_sqlite_row_keeps_extras(db, apify_normalized_contact):
    from src.db.connection import get_db_connection

    job_id = add_job({"title": "QA", "company": "Acme", "status": "accepted"}, db_path=db)
    contacts_json = json.dumps(
        [
            {
                **apify_normalized_contact,
                "name": "Ivan Petrov",
                "url": SHARED_URL,
            }
        ]
    )
    conn = get_db_connection(db)
    conn.execute("UPDATE jobs SET contacts = ? WHERE id = ?", (contacts_json, job_id))
    conn.commit()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()

    job = parse_job_row(row)
    assert job.contacts[0].currentPosition == "Senior Engineer at TechCorp"
