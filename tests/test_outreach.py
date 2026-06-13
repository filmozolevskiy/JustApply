import os
import sys
import json
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src import db as database
import src.db.connection as _db_connection
import src.web.server as server_module
from src.web.server import app
from fastapi.testclient import TestClient

import src.core.outreach as outreach_module
from src.core.outreach import source_contacts, _normalize_apify_employee, _run_apify_actor, ApifyTimeoutError, classify_contacts
from src.schemas import OutreachSettings

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_job_tracker.db"
    test_db_str = str(test_db)
    monkeypatch.setattr(_db_connection, "DB_PATH", test_db_str)
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


def test_normalize_extracts_current_position_and_location():
    item = {
        "firstName": "Ivan", "lastName": "Petrov",
        "headline": "Backend Dev", "linkedinUrl": "https://linkedin.com/in/ivan",
        "languages": [],
        "currentPosition": "Senior Engineer at TechCorp",
        "location": "Montreal, QC",
    }
    result = _normalize_apify_employee(item)
    assert result["currentPosition"] == "Senior Engineer at TechCorp"
    assert result["location"] == "Montreal, QC"


def test_normalize_handles_missing_current_position_and_location():
    item = {
        "firstName": "Jane", "lastName": "Smith",
        "headline": "HR", "linkedinUrl": "https://linkedin.com/in/jane",
        "languages": [],
    }
    result = _normalize_apify_employee(item)
    assert result["currentPosition"] == ""
    assert result["location"] == ""


# --- DB round-trip ---

def test_contact_new_fields_persist_through_db_roundtrip(setup_test_db):
    db_path = setup_test_db
    contacts = [
        {
            "name": "Alice", "title": "HR Manager",
            "url": "https://linkedin.com/in/alice",
            "contacted": False, "russian_speaker": False,
            "is_recruiter": True,
            "currentPosition": "HR Manager at Acme",
            "location": "Toronto, ON",
        }
    ]
    job_id = database.add_job({
        "title": "QA Engineer",
        "company": "Acme",
        "status": "sourced",
        "contacts": contacts,
    }, db_path=db_path)

    job = database.get_job(job_id, db_path=db_path)
    contact = job["contacts"][0]
    assert contact["is_recruiter"] is True
    assert contact["currentPosition"] == "HR Manager at Acme"
    assert contact["location"] == "Toronto, ON"


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
    assert "Добрый день" not in msg
    assert "Ivan" in msg
    assert "Hello Ivan" in msg


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
        {"name": "Ivan", "russian_speaker": True, "is_recruiter": False},
        {"name": "Jane", "russian_speaker": False, "is_recruiter": False},
    ]
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        msg = await generate_outreach_for_job(job, contacts)
    assert "Добрый день" not in msg
    assert "Ivan" in msg


@pytest.mark.asyncio
async def test_generate_outreach_for_job_defaults_to_hiring_manager_when_no_contacts():
    from src.core.outreach import generate_outreach_for_job
    job = {"title": "QA Lead", "company": "Acme", "resumeUsed": "qa.md", "description": ""}
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        msg = await generate_outreach_for_job(job, [])
    assert "Hello Hiring Manager" in msg


# --- classify_contacts ---

@pytest.mark.asyncio
async def test_classify_contacts_assigns_russian_speaker_flag(monkeypatch):
    from src.core.outreach import classify_contacts
    from src.schemas import OutreachSettings

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    items = [{"firstName": "Ivan", "lastName": "Petrov", "headline": "Dev", "linkedinUrl": ""}]
    settings = OutreachSettings(target_russian_speakers=True, target_recruiters=True)

    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '[{"index": 0, "russian_speaker": true, "is_recruiter": false}]'
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)

    with patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel", return_value=mock_model):
        result = await classify_contacts(items, settings)

    assert len(result) == 1
    assert result[0]["russian_speaker"] is True
    assert result[0]["is_recruiter"] is False


@pytest.mark.asyncio
async def test_classify_contacts_assigns_recruiter_flag(monkeypatch):
    from src.core.outreach import classify_contacts
    from src.schemas import OutreachSettings

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    items = [{"firstName": "Jane", "lastName": "HR", "headline": "HR Manager", "linkedinUrl": ""}]
    settings = OutreachSettings(target_russian_speakers=True, target_recruiters=True)

    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '[{"index": 0, "russian_speaker": false, "is_recruiter": true}]'
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)

    with patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel", return_value=mock_model):
        result = await classify_contacts(items, settings)

    assert len(result) == 1
    assert result[0]["is_recruiter"] is True
    assert result[0]["russian_speaker"] is False


@pytest.mark.asyncio
async def test_classify_contacts_handles_dual_classified_contact(monkeypatch):
    from src.core.outreach import classify_contacts
    from src.schemas import OutreachSettings

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    items = [{"firstName": "Olga", "lastName": "Rec", "headline": "Talent Acquisition", "linkedinUrl": ""}]
    settings = OutreachSettings(target_russian_speakers=True, target_recruiters=True)

    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '[{"index": 0, "russian_speaker": true, "is_recruiter": true}]'
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)

    with patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel", return_value=mock_model):
        result = await classify_contacts(items, settings)

    assert len(result) == 1
    assert result[0]["russian_speaker"] is True
    assert result[0]["is_recruiter"] is True


@pytest.mark.asyncio
async def test_classify_contacts_caps_at_five_per_group(monkeypatch):
    from src.core.outreach import classify_contacts
    from src.schemas import OutreachSettings

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    items = [{"firstName": f"Ivan{i}", "lastName": "P", "headline": "Dev", "linkedinUrl": ""} for i in range(7)]
    settings = OutreachSettings(target_russian_speakers=True, target_recruiters=False)

    llm_response = json.dumps([{"index": i, "russian_speaker": True, "is_recruiter": False} for i in range(7)])

    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = llm_response
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)

    with patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel", return_value=mock_model):
        result = await classify_contacts(items, settings)

    assert sum(1 for c in result if c["russian_speaker"]) == 5


@pytest.mark.asyncio
async def test_classify_contacts_returns_empty_when_llm_returns_no_matches(monkeypatch):
    from src.core.outreach import classify_contacts
    from src.schemas import OutreachSettings

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    items = [{"firstName": "Bob", "lastName": "Smith", "headline": "Engineer", "linkedinUrl": ""}]
    settings = OutreachSettings(target_russian_speakers=True, target_recruiters=True)

    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "[]"
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)

    with patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel", return_value=mock_model):
        result = await classify_contacts(items, settings)

    assert result == []


# --- audience-specific outreach templates ---

def test_build_russian_speaker_prompt_contains_referral_and_english_greeting():
    from src.core.outreach import build_russian_speaker_prompt
    prompt = build_russian_speaker_prompt(
        resume="my resume",
        job_title="QA Lead",
        company="Acme",
        job_link="http://job.url",
        description="test job",
        contact_name="Ivan",
    )
    assert "referral" in prompt.lower()
    assert "cv" in prompt.lower() or "resume" in prompt.lower()
    assert "English" in prompt
    assert "Добрый день" not in prompt
    assert "Ivan" in prompt
    assert "http://job.url" in prompt


def test_build_recruiter_prompt_no_referral_direct_connect():
    from src.core.outreach import build_recruiter_prompt
    prompt = build_recruiter_prompt(
        resume="my resume",
        job_title="QA Lead",
        company="Acme",
        job_link="http://job.url",
        description="test job",
        contact_name="Sarah",
    )
    assert "referral" not in prompt.lower()
    assert "connect" in prompt.lower() or "cv" in prompt.lower() or "resume" in prompt.lower()
    assert "English" in prompt
    assert "Добрый день" not in prompt
    assert "Sarah" in prompt
    assert "http://job.url" in prompt


@pytest.mark.asyncio
async def test_generate_outreach_message_fallback_no_cyrillic_for_russian_speaker():
    from src.core.outreach import generate_outreach_message
    job = {"title": "Dev", "company": "Corp", "resumeUsed": "qa.md", "description": ""}
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        msg = await generate_outreach_message(job, "Ivan", True, "")
    assert "Добрый день" not in msg


@pytest.mark.asyncio
async def test_generate_outreach_message_gemini_uses_recruiter_prompt_when_is_recruiter(monkeypatch):
    from src.core.outreach import generate_outreach_message
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "recruiter response"
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)

    with patch.object(outreach_module, "build_recruiter_prompt", wraps=outreach_module.build_recruiter_prompt) as mock_recruiter, \
         patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel", return_value=mock_model):
        msg = await generate_outreach_message(
            {"title": "QA", "company": "Co", "resumeUsed": "qa.md", "description": "", "link": "http://j.url"},
            "Bob", False, "resume text", is_recruiter=True,
        )
    mock_recruiter.assert_called_once()
    assert msg == "recruiter response"


@pytest.mark.asyncio
async def test_generate_outreach_message_gemini_uses_russian_speaker_prompt_when_is_russian(monkeypatch):
    from src.core.outreach import generate_outreach_message
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "russian response"
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)

    with patch.object(outreach_module, "build_russian_speaker_prompt", wraps=outreach_module.build_russian_speaker_prompt) as mock_russian, \
         patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel", return_value=mock_model):
        msg = await generate_outreach_message(
            {"title": "QA", "company": "Co", "resumeUsed": "qa.md", "description": "", "link": "http://j.url"},
            "Ivan", True, "resume text", is_recruiter=False,
        )
    mock_russian.assert_called_once()
    assert msg == "russian response"


@pytest.mark.asyncio
async def test_generate_outreach_message_recruiter_priority_over_russian_speaker(monkeypatch):
    from src.core.outreach import generate_outreach_message
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "priority response"
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)

    with patch.object(outreach_module, "build_recruiter_prompt", wraps=outreach_module.build_recruiter_prompt) as mock_recruiter, \
         patch.object(outreach_module, "build_russian_speaker_prompt", wraps=outreach_module.build_russian_speaker_prompt) as mock_russian, \
         patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel", return_value=mock_model):
        await generate_outreach_message(
            {"title": "QA", "company": "Co", "resumeUsed": "qa.md", "description": "", "link": "http://j.url"},
            "Ivan", True, "resume text", is_recruiter=True,
        )
    mock_recruiter.assert_called_once()
    mock_russian.assert_not_called()


@pytest.mark.asyncio
async def test_generate_outreach_for_job_passes_is_recruiter_flag():
    from src.core.outreach import generate_outreach_for_job
    job = {"title": "HR Role", "company": "Corp", "resumeUsed": "qa.md", "description": "", "link": "http://j.url"}
    contacts = [{"name": "Sarah", "russian_speaker": False, "is_recruiter": True}]

    with patch.object(outreach_module, "generate_outreach_message", new=AsyncMock(return_value="msg")) as mock_gen:
        await generate_outreach_for_job(job, contacts)

    _, call_kwargs = mock_gen.call_args_list[0][0], mock_gen.call_args_list[0][1]
    assert mock_gen.call_args[1].get("is_recruiter") is True or mock_gen.call_args[0][4] is True
