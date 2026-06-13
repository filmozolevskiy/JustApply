import os
import sys
import json
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src import database
import src.web.server as server_module
from src.web.server import app
from fastapi.testclient import TestClient

import src.core.outreach as outreach_module
from src.core.outreach import source_contacts, _normalize_apify_employee, _run_apify_actor, ApifyTimeoutError

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


# --- Apify polling timeout ---

@pytest.mark.asyncio
async def test_run_apify_actor_raises_apify_timeout_error():
    """Polling loop raises ApifyTimeoutError when timeout_seconds is exceeded."""
    mock_post = MagicMock()
    mock_post.status_code = 201
    mock_post.json.return_value = {"data": {"id": "run-abc123"}}

    mock_status = MagicMock()
    mock_status.status_code = 200
    mock_status.json.return_value = {"data": {"status": "RUNNING"}}

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post.return_value = mock_post
    mock_client.get.return_value = mock_status

    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch.dict(os.environ, {"APIFY_API_TOKEN": "fake-token"}), \
         patch("asyncio.sleep", new=AsyncMock()), \
         patch("time.monotonic", side_effect=[0.0, 1.0, 301.0]):
        with pytest.raises(ApifyTimeoutError):
            await _run_apify_actor("TestCorp", timeout_seconds=300.0)


@pytest.mark.asyncio
async def test_source_contacts_returns_empty_on_apify_timeout():
    """source_contacts returns [] when _run_apify_actor raises ApifyTimeoutError."""
    job = {"title": "QA Engineer", "company": "TestCorp", "contacts": []}
    with patch.object(outreach_module, "_run_apify_actor", new=AsyncMock(side_effect=ApifyTimeoutError("timed out"))):
        result = await source_contacts(job)
    assert result == []


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


# --- Outreach Generator ---

def test_load_resume_for_outreach_returns_empty_when_all_fail():
    from src.core.outreach import load_resume_for_outreach
    with patch("src.core.matcher.load_resume", side_effect=FileNotFoundError("not found")):
        assert load_resume_for_outreach("missing.md") == ""


def test_load_resume_for_outreach_falls_back_to_qa_on_primary_fail():
    from src.core.outreach import load_resume_for_outreach

    def mock_load(name):
        if name == "qa.md":
            return "qa fallback content"
        raise FileNotFoundError(f"{name} not found")

    with patch("src.core.matcher.load_resume", side_effect=mock_load):
        assert load_resume_for_outreach("custom_resume.md") == "qa fallback content"


@pytest.mark.asyncio
async def test_generate_outreach_message_template_no_api_key():
    from src.core.outreach import generate_outreach_message
    job = {"title": "QA Lead", "company": "Acme", "resumeUsed": "qa.md", "description": ""}
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        msg = await generate_outreach_message(job, "Alice", False, "resume text")
    assert "QA Lead" in msg
    assert "Acme" in msg
    assert "Hello Alice" in msg


@pytest.mark.asyncio
async def test_generate_outreach_message_russian_greeting():
    from src.core.outreach import generate_outreach_message
    job = {"title": "Dev", "company": "Corp", "resumeUsed": "qa.md", "description": ""}
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        msg = await generate_outreach_message(job, "Ivan", True, "")
    assert "Добрый день" in msg
    assert "Ivan" in msg


@pytest.mark.asyncio
async def test_generate_outreach_message_uses_gemini_when_available(monkeypatch):
    from src.core.outreach import generate_outreach_message
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "  AI-generated outreach  "
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)
    with patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel", return_value=mock_model):
        msg = await generate_outreach_message(
            {"title": "QA", "company": "Co", "resumeUsed": "qa.md", "description": ""},
            "Bob", False, "resume text",
        )
    assert msg == "AI-generated outreach"


@pytest.mark.asyncio
async def test_generate_outreach_for_job_uses_primary_contact():
    from src.core.outreach import generate_outreach_for_job
    job = {"title": "QA Lead", "company": "Acme", "resumeUsed": "qa.md", "description": ""}
    contacts = [
        {"name": "Ivan", "russian_speaker": True},
        {"name": "Jane", "russian_speaker": False},
    ]
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        msg = await generate_outreach_for_job(job, contacts)
    assert "Добрый день" in msg
    assert "Ivan" in msg


@pytest.mark.asyncio
async def test_generate_outreach_for_job_defaults_to_hiring_manager_when_no_contacts():
    from src.core.outreach import generate_outreach_for_job
    job = {"title": "QA Lead", "company": "Acme", "resumeUsed": "qa.md", "description": ""}
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        msg = await generate_outreach_for_job(job, [])
    assert "Hello Hiring Manager" in msg
