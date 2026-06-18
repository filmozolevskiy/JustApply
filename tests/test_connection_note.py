import os
import sys
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.core.enrichment.connection_note as connection_note_module
from src.core.enrichment.connection_note import (
    minimal_fallback_template,
    complete_outreach_fallback_template,
    generate_connection_note_template,
    generate_complete_outreach_template,
    generate_outreach_templates,
    RECRUITER_CTA,
    RUSSIAN_SPEAKER_CTA,
)


# --- minimal_fallback_template ---

def test_minimal_fallback_recruiter_has_correct_cta():
    result = minimal_fallback_template("recruiter")
    assert RECRUITER_CTA in result


def test_minimal_fallback_russian_speaker_has_correct_cta():
    result = minimal_fallback_template("russian_speaker")
    assert RUSSIAN_SPEAKER_CTA in result


def test_minimal_fallback_recruiter_within_200_chars():
    assert len(minimal_fallback_template("recruiter")) <= 200


def test_minimal_fallback_russian_speaker_within_200_chars():
    assert len(minimal_fallback_template("russian_speaker")) <= 200


def test_minimal_fallback_contains_name_placeholder():
    for audience in ("recruiter", "russian_speaker"):
        result = minimal_fallback_template(audience)
        assert "______" in result.split("\n", 1)[0]


def test_minimal_fallback_uses_job_company_and_title():
    job = {"title": "QA Lead", "company": "Acme"}
    result = minimal_fallback_template("recruiter", job)
    assert "Acme is looking for a QA Lead" in result
    assert "______ is looking for a ______" not in result
    assert len(result) <= 200


def test_minimal_fallback_contains_fit_line():
    from src.core.enrichment.connection_note import FIT_LINE
    for audience in ("recruiter", "russian_speaker"):
        assert FIT_LINE in minimal_fallback_template(audience)


# --- Complete Outreach Fallback ---

def test_complete_outreach_fallback_uses_name_placeholder_and_profile_label():
    from src.core.enrichment.connection_note import complete_outreach_fallback_template
    job = {"title": "QA Lead", "company": "Acme", "resumeUsed": "qa.md"}
    result = complete_outreach_fallback_template(job, "recruiter")
    assert "______" in result
    assert "QA Lead" in result
    assert "Acme" in result
    assert "QA Automator" in result
    assert len(result) > 200


def test_complete_outreach_fallback_recruiter_cta():
    from src.core.enrichment.connection_note import complete_outreach_fallback_template
    from src.core.enrichment.connection_note import RECRUITER_CTA
    job = {"title": "Dev", "company": "Corp", "resumeUsed": "qa.md"}
    result = complete_outreach_fallback_template(job, "recruiter")
    assert RECRUITER_CTA in result


def test_complete_outreach_fallback_russian_speaker_cta():
    from src.core.enrichment.connection_note import complete_outreach_fallback_template
    from src.core.enrichment.connection_note import RUSSIAN_SPEAKER_CTA
    job = {"title": "Dev", "company": "Corp", "resumeUsed": "qa.md"}
    result = complete_outreach_fallback_template(job, "russian_speaker")
    assert RUSSIAN_SPEAKER_CTA in result


# --- generate_complete_outreach_template ---

@pytest.mark.asyncio
async def test_generate_complete_outreach_falls_back_without_api_key():
    job = {"title": "QA Lead", "company": "Acme", "resumeUsed": "qa.md", "link": "http://job.url", "description": ""}
    with patch("src.core.enrichment.connection_note.load_dotenv"), \
         patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        result = await generate_complete_outreach_template(job, "recruiter")
    assert result == complete_outreach_fallback_template(job, "recruiter")


@pytest.mark.asyncio
async def test_generate_complete_outreach_returns_llm_result(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    long_note = (
        "Hello ______,\n\n"
        "Acme is hiring a QA Lead. See http://job.url\n"
        "- Strong automation background\n"
        "- CI/CD experience\n\n"
        "I would be grateful to connect and share my CV."
    )

    with patch("src.core.enrichment.connection_note.load_resume_for_outreach", return_value="resume text"), \
         patch("src.core.enrichment.connection_note.gemini_generate_text", new=AsyncMock(return_value=long_note)) as mock_generate:
        result = await generate_complete_outreach_template(
            {"title": "QA Lead", "company": "Acme", "link": "http://job.url", "description": "test", "resumeUsed": "qa.md"},
            "recruiter",
        )

    assert result == long_note
    assert mock_generate.call_count == 1


# --- generate_connection_note_template ---

@pytest.mark.asyncio
async def test_generate_connection_note_falls_back_without_api_key():
    job = {"title": "QA Lead", "company": "Acme"}
    with patch("src.core.enrichment.connection_note.load_dotenv"), \
         patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        result = await generate_connection_note_template(job, "recruiter")
    assert result == minimal_fallback_template("recruiter", job)


@pytest.mark.asyncio
async def test_generate_connection_note_returns_short_llm_result(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    short_note = "Hello ______,\n\nAcme is looking for a QA Lead. My experience align well with the requirements.\n\nI would be grateful to connect and share my CV."
    assert len(short_note) <= 200

    with patch("src.core.enrichment.connection_note.gemini_generate_text", new=AsyncMock(return_value=short_note)) as mock_generate:
        result = await generate_connection_note_template({"title": "QA Lead", "company": "Acme"}, "recruiter")

    assert result == short_note
    assert mock_generate.call_count == 1


@pytest.mark.asyncio
async def test_generate_connection_note_retries_when_first_result_too_long(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    long_note = "X" * 201
    short_note = "Hello ______,\n\nAcme is looking for a QA. My experience align well with the requirements.\n\nI would be grateful to connect and share my CV."
    assert len(short_note) <= 200

    mock_generate = AsyncMock(side_effect=[long_note, short_note])

    with patch("src.core.enrichment.connection_note.gemini_generate_text", mock_generate):
        result = await generate_connection_note_template({"title": "QA Lead", "company": "Acme"}, "recruiter")

    assert result == short_note
    assert mock_generate.call_count == 2


@pytest.mark.asyncio
async def test_generate_connection_note_falls_back_when_both_attempts_too_long(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    long_note = "X" * 201

    mock_generate = AsyncMock(return_value=long_note)

    with patch("src.core.enrichment.connection_note.gemini_generate_text", mock_generate):
        result = await generate_connection_note_template({"title": "QA Lead", "company": "Acme"}, "russian_speaker")

    assert result == minimal_fallback_template("russian_speaker", {"title": "QA Lead", "company": "Acme"})
    assert len(result) <= 200


@pytest.mark.asyncio
async def test_generate_connection_note_falls_back_on_llm_exception(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    with patch("src.core.enrichment.connection_note.gemini_generate_text", new=AsyncMock(side_effect=Exception("LLM error"))):
        result = await generate_connection_note_template({"title": "QA Lead", "company": "Acme"}, "recruiter")

    assert result == minimal_fallback_template("recruiter", {"title": "QA Lead", "company": "Acme"})


@pytest.mark.asyncio
async def test_generate_connection_note_falls_back_on_llm_timeout(monkeypatch):
    import asyncio

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    async def slow_generate(*args, **kwargs):
        await asyncio.sleep(60)

    with patch("src.core.enrichment.connection_note.gemini_generate_text", side_effect=slow_generate), \
         patch.object(connection_note_module, "GEMINI_TIMEOUT_SECONDS", 0.05):
        result = await generate_connection_note_template({"title": "QA Lead", "company": "Acme"}, "recruiter")

    assert result == minimal_fallback_template("recruiter", {"title": "QA Lead", "company": "Acme"})


# --- generate_outreach_templates ---

@pytest.mark.asyncio
async def test_generate_outreach_templates_uses_complete_format_when_short_disabled():
    job = {"title": "QA Lead", "company": "Acme"}
    contacts = [{"name": "Sarah", "is_recruiter": True, "russian_speaker": False}]
    complete_note = "Hello ______,\n\nLong complete outreach draft with bullets and link."

    async def mock_complete(j, audience, log_func=None):
        return complete_note

    with patch.object(connection_note_module, "generate_complete_outreach_template", side_effect=mock_complete) as mock_fn, \
         patch.object(connection_note_module, "generate_connection_note_template") as mock_short:
        result = await generate_outreach_templates(job, contacts=contacts, short_connection_note=False)

    mock_short.assert_not_called()
    mock_fn.assert_called_once()
    assert result["recruiter"] == complete_note
    assert result["russian_speaker"] == ""


@pytest.mark.asyncio
async def test_generate_outreach_templates_generates_both_on_empty_contacts():
    job = {"title": "QA Lead", "company": "Acme"}
    recruiter_note = "Hello ______,\n\nAcme is looking for a QA. My experience align well with the requirements.\n\nI would be grateful to connect and share my CV."
    russian_note = "Hello ______,\n\nAcme is looking for a QA. My experience align well with the requirements.\n\nI'd be grateful if you could refer me for the role."

    async def mock_gen(j, audience, log_func=None):
        return recruiter_note if audience == "recruiter" else russian_note

    with patch.object(connection_note_module, "generate_connection_note_template", side_effect=mock_gen):
        result = await generate_outreach_templates(job, contacts=[])

    assert result["recruiter"] == recruiter_note
    assert result["russian_speaker"] == russian_note


@pytest.mark.asyncio
async def test_generate_outreach_templates_generates_only_recruiter_when_only_recruiter_contacts():
    job = {"title": "QA Lead", "company": "Acme"}
    contacts = [{"name": "Sarah", "is_recruiter": True, "russian_speaker": False}]
    recruiter_note = "recruiter template"

    async def mock_gen(j, audience, log_func=None):
        return recruiter_note if audience == "recruiter" else "russian template"

    with patch.object(connection_note_module, "generate_connection_note_template", side_effect=mock_gen) as mock_fn:
        result = await generate_outreach_templates(job, contacts=contacts)

    assert result["recruiter"] == recruiter_note
    assert result["russian_speaker"] == ""
    audiences_called = [c.args[1] for c in mock_fn.call_args_list]
    assert "recruiter" in audiences_called
    assert "russian_speaker" not in audiences_called


@pytest.mark.asyncio
async def test_generate_outreach_templates_generates_only_russian_when_only_russian_contacts():
    job = {"title": "QA Lead", "company": "Acme"}
    contacts = [{"name": "Ivan", "is_recruiter": False, "russian_speaker": True}]
    russian_note = "russian template"

    async def mock_gen(j, audience, log_func=None):
        return russian_note if audience == "russian_speaker" else "recruiter template"

    with patch.object(connection_note_module, "generate_connection_note_template", side_effect=mock_gen) as mock_fn:
        result = await generate_outreach_templates(job, contacts=contacts)

    assert result["russian_speaker"] == russian_note
    assert result["recruiter"] == ""
    audiences_called = [c.args[1] for c in mock_fn.call_args_list]
    assert "russian_speaker" in audiences_called
    assert "recruiter" not in audiences_called


@pytest.mark.asyncio
async def test_generate_outreach_templates_generates_both_for_mixed_contacts():
    job = {"title": "QA Lead", "company": "Acme"}
    contacts = [
        {"name": "Sarah", "is_recruiter": True, "russian_speaker": False},
        {"name": "Ivan", "is_recruiter": False, "russian_speaker": True},
    ]

    async def mock_gen(j, audience, log_func=None):
        return f"{audience} template"

    with patch.object(connection_note_module, "generate_connection_note_template", side_effect=mock_gen):
        result = await generate_outreach_templates(job, contacts=contacts)

    assert result["recruiter"] == "recruiter template"
    assert result["russian_speaker"] == "russian_speaker template"
