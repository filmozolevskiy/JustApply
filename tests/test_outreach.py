import os
import sys
import json
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import database
import prototype_dashboard
from prototype_dashboard import app
from fastapi.testclient import TestClient

import src.core.outreach as outreach_module
from src.core.outreach import source_contacts, _classify_russian_speakers, _normalize_apify_employee

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_job_tracker.db"
    test_db_str = str(test_db)
    monkeypatch.setattr(database, "DB_PATH", test_db_str)
    database.init_db(test_db_str)
    yield test_db_str


# --- source_contacts: direct poster mapping ---

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


# --- source_contacts: Apify fallback - Stage 1 sufficient ---

@pytest.mark.asyncio
async def test_source_contacts_stage1_returns_russian_speakers_when_5_or_more():
    stage1_employees = [
        {"fullName": f"Ivan Petrov {i}", "headline": "Software Engineer", "linkedInUrl": f"https://linkedin.com/in/ivan{i}"}
        for i in range(6)
    ]
    job = {"title": "QA Engineer", "company": "TechCorp", "contacts": []}

    with patch.object(outreach_module, "_run_apify_actor", new=AsyncMock(return_value=stage1_employees)):
        result = await source_contacts(job)

    assert len(result) == 6
    assert all(c["russian_speaker"] is True for c in result)
    assert all(c["contacted"] is False for c in result)


# --- source_contacts: Apify fallback - Stage 2 triggered ---

@pytest.mark.asyncio
async def test_source_contacts_triggers_stage2_when_stage1_returns_fewer_than_5():
    stage1_employees = [
        {"fullName": "Ivan Petrov", "headline": "Engineer", "linkedInUrl": "https://linkedin.com/in/ivan"}
    ]
    stage2_employees = [
        {"fullName": "Jane Smith", "headline": "HR Manager", "linkedInUrl": "https://linkedin.com/in/janesmith"},
        {"fullName": "Olga Sidorova", "headline": "Talent Acquisition", "linkedInUrl": "https://linkedin.com/in/olga"},
    ]

    call_count = {"n": 0}

    async def mock_apify(company, keyword=None, job_titles=None, log_func=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return stage1_employees
        return stage2_employees

    with patch.object(outreach_module, "_run_apify_actor", new=mock_apify), \
         patch.object(outreach_module, "_classify_russian_speakers", new=AsyncMock(
             side_effect=lambda contacts, **_: [{**c, "russian_speaker": c["name"].startswith("Olga")} for c in contacts]
         )):
        result = await source_contacts(job={"title": "QA", "company": "Corp", "contacts": []})

    assert call_count["n"] == 2
    assert len(result) == 2
    olga = next(c for c in result if c["name"] == "Olga Sidorova")
    assert olga["russian_speaker"] is True
    jane = next(c for c in result if c["name"] == "Jane Smith")
    assert jane["russian_speaker"] is False


# --- _classify_russian_speakers ---

@pytest.mark.asyncio
async def test_classify_russian_speakers_sets_flag_from_gemini():
    contacts = [
        {"name": "Ivan Petrov", "title": "Engineer", "url": "https://linkedin.com/in/ivan", "contacted": False, "russian_speaker": False},
        {"name": "Jane Smith", "title": "HR", "url": "https://linkedin.com/in/jane", "contacted": False, "russian_speaker": False},
    ]

    mock_response = MagicMock()
    mock_response.text = "[true, false]"

    with patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel") as mock_model_cls:
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_model_cls.return_value = mock_model

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            result = await _classify_russian_speakers(contacts)

    assert result[0]["russian_speaker"] is True
    assert result[1]["russian_speaker"] is False


@pytest.mark.asyncio
async def test_classify_russian_speakers_skips_when_no_api_key():
    contacts = [
        {"name": "Ivan", "title": "Dev", "url": "", "contacted": False, "russian_speaker": False}
    ]
    env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        result = await _classify_russian_speakers(contacts)
    assert result[0]["russian_speaker"] is False


# --- _normalize_apify_employee ---

def test_normalize_apify_employee_maps_fields():
    item = {"fullName": "Sergei Ivanov", "headline": "Backend Dev", "linkedInUrl": "https://linkedin.com/in/sergei"}
    result = _normalize_apify_employee(item)
    assert result == {
        "name": "Sergei Ivanov",
        "title": "Backend Dev",
        "url": "https://linkedin.com/in/sergei",
        "contacted": False,
        "russian_speaker": False,
    }


def test_normalize_apify_employee_handles_missing_fields():
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
    assert data["status"] == "applied"


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
