import os
import sys
import json
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src import database
import src.server as server_module
from src.server import app
from fastapi.testclient import TestClient

import src.core.outreach as outreach_module
from src.core.outreach import source_contacts, _normalize_apify_employee

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_job_tracker.db"
    test_db_str = str(test_db)
    monkeypatch.setattr(database, "DB_PATH", test_db_str)
    database.init_db(test_db_str)
    yield test_db_str


# --- source_contacts: return existing ---

@pytest.mark.asyncio
async def test_source_contacts_returns_existing_contacts_when_present():
    job = {
        "title": "QA Engineer",
        "company": "Acme",
        "contacts": [{"name": "Alice", "title": "Recruiter", "url": "https://linkedin.com/in/alice", "contacted": False, "russian_speaker": False}]
    }
    result = await source_contacts(job)
    assert result == job["contacts"]


@pytest.mark.asyncio
async def test_source_contacts_returns_empty_when_no_company_and_no_contacts():
    job = {"title": "QA Engineer", "company": "", "contacts": []}
    result = await source_contacts(job)
    assert result == []


# --- source_contacts: language-based Russian speaker detection ---

@pytest.mark.asyncio
async def test_source_contacts_returns_russian_speakers_from_language_field():
    employees = [
        {"firstName": "Ivan", "lastName": "Petrov", "headline": "Engineer", "linkedinUrl": "https://linkedin.com/in/ivan",
         "languages": [{"name": "Russian"}, {"name": "English"}]},
        {"firstName": "Jane", "lastName": "Smith", "headline": "HR Manager", "linkedinUrl": "https://linkedin.com/in/jane",
         "languages": [{"name": "English"}]},
    ]
    job = {"title": "QA Engineer", "company": "TechCorp", "contacts": []}

    with patch.object(outreach_module, "_run_apify_actor", new=AsyncMock(return_value=employees)):
        result = await source_contacts(job)

    assert len(result) == 1
    assert result[0]["name"] == "Ivan Petrov"
    assert result[0]["russian_speaker"] is True


@pytest.mark.asyncio
async def test_source_contacts_falls_back_to_hr_when_no_russian_speakers():
    employees = [
        {"firstName": "Bob", "lastName": "Lee", "headline": "Software Engineer", "linkedinUrl": "https://linkedin.com/in/bob",
         "languages": [{"name": "English"}]},
        {"firstName": "Jane", "lastName": "Smith", "headline": "HR Manager", "linkedinUrl": "https://linkedin.com/in/jane",
         "languages": [{"name": "French"}]},
        {"firstName": "Carol", "lastName": "Tang", "headline": "Talent Acquisition Specialist", "linkedinUrl": "https://linkedin.com/in/carol",
         "languages": []},
        {"firstName": "Dave", "lastName": "Kim", "headline": "Product Manager", "linkedinUrl": "https://linkedin.com/in/dave",
         "languages": []},
    ]
    job = {"title": "QA", "company": "Corp", "contacts": []}

    with patch.object(outreach_module, "_run_apify_actor", new=AsyncMock(return_value=employees)):
        result = await source_contacts(job)

    assert len(result) == 2
    assert result[0]["name"] == "Jane Smith"
    assert result[1]["name"] == "Carol Tang"


# --- _normalize_apify_employee ---

def test_normalize_detects_russian_language():
    item = {
        "firstName": "Ivan", "lastName": "Petrov",
        "headline": "Backend Dev", "linkedinUrl": "https://linkedin.com/in/ivan",
        "languages": [{"name": "Russian"}, {"name": "English"}],
    }
    result = _normalize_apify_employee(item)
    assert result["russian_speaker"] is True
    assert result["name"] == "Ivan Petrov"


def test_normalize_detects_ukrainian_language():
    item = {
        "firstName": "Oksana", "lastName": "Kovalenko",
        "headline": "QA", "linkedinUrl": "https://linkedin.com/in/oksana",
        "languages": [{"name": "Ukrainian"}],
    }
    result = _normalize_apify_employee(item)
    assert result["russian_speaker"] is True


def test_normalize_no_russian_when_no_matching_language():
    item = {
        "firstName": "Jane", "lastName": "Smith",
        "headline": "HR", "linkedinUrl": "https://linkedin.com/in/jane",
        "languages": [{"name": "English"}, {"name": "French"}],
    }
    result = _normalize_apify_employee(item)
    assert result["russian_speaker"] is False


def test_normalize_handles_missing_languages_field():
    result = _normalize_apify_employee({"firstName": "Bob", "lastName": "Lee", "linkedinUrl": ""})
    assert result["russian_speaker"] is False
    assert result["name"] == "Bob Lee"


def test_normalize_handles_empty_item():
    result = _normalize_apify_employee({})
    assert result["name"] == ""
    assert result["title"] == ""
    assert result["url"] == ""
    assert result["contacted"] is False
    assert result["russian_speaker"] is False


# --- API: PUT /api/jobs/{id}/contacts/{idx} ---

def test_contact_toggle_updates_db_and_promotes_status(setup_test_db):
    db_path = setup_test_db
    contacts = [
        {"name": "Alice", "title": "Recruiter", "url": "https://linkedin.com/in/alice", "contacted": False, "russian_speaker": False}
    ]
    job_id = database.add_job({
        "title": "QA Engineer",
        "company": "Acme",
        "status": "sourced",
        "contacts": contacts,
    }, db_path=db_path)

    response = client.put(f"/api/jobs/{job_id}/contacts/0", json={"contacted": True})
    assert response.status_code == 200
    data = response.json()
    assert data["contacts"][0]["contacted"] is True
    assert data["status"] == "contacted"


def test_contact_toggle_does_not_downgrade_status(setup_test_db):
    db_path = setup_test_db
    contacts = [
        {"name": "Alice", "title": "Recruiter", "url": "https://linkedin.com/in/alice", "contacted": True, "russian_speaker": False}
    ]
    job_id = database.add_job({
        "title": "QA Engineer",
        "company": "Acme",
        "status": "interviewing",
        "contacts": contacts,
    }, db_path=db_path)

    response = client.put(f"/api/jobs/{job_id}/contacts/0", json={"contacted": False})
    assert response.status_code == 200
    data = response.json()
    assert data["contacts"][0]["contacted"] is False
    assert data["status"] == "interviewing"


def test_contact_toggle_returns_404_for_missing_job():
    response = client.put("/api/jobs/99999/contacts/0", json={"contacted": True})
    assert response.status_code == 404


def test_contact_toggle_returns_404_for_missing_contact_idx(setup_test_db):
    db_path = setup_test_db
    job_id = database.add_job({
        "title": "QA",
        "company": "Corp",
        "status": "sourced",
        "contacts": [],
    }, db_path=db_path)

    response = client.put(f"/api/jobs/{job_id}/contacts/5", json={"contacted": True})
    assert response.status_code == 404
