import os
import sys
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.core.outreach as outreach_module
from src.core.outreach import (
    minimal_fallback_template,
    generate_connection_note_template,
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
        assert "______" in result


def test_minimal_fallback_contains_fit_line():
    from src.core.outreach import FIT_LINE
    for audience in ("recruiter", "russian_speaker"):
        assert FIT_LINE in minimal_fallback_template(audience)


# --- generate_connection_note_template ---

@pytest.mark.asyncio
async def test_generate_connection_note_falls_back_without_api_key():
    job = {"title": "QA Lead", "company": "Acme"}
    with patch("src.core.outreach.load_dotenv"), \
         patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        result = await generate_connection_note_template(job, "recruiter")
    assert result == minimal_fallback_template("recruiter")


@pytest.mark.asyncio
async def test_generate_connection_note_returns_short_llm_result(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    short_note = "Hello ______,\n\nAcme is looking for a QA Lead. My experience align well with the requirements.\n\nI would be grateful to connect and share my CV."
    assert len(short_note) <= 200

    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = short_note
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)

    with patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel", return_value=mock_model):
        result = await generate_connection_note_template({"title": "QA Lead", "company": "Acme"}, "recruiter")

    assert result == short_note
    assert mock_model.generate_content_async.call_count == 1


@pytest.mark.asyncio
async def test_generate_connection_note_retries_when_first_result_too_long(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    long_note = "X" * 201
    short_note = "Hello ______,\n\nAcme is looking for a QA. My experience align well with the requirements.\n\nI would be grateful to connect and share my CV."
    assert len(short_note) <= 200

    mock_model = MagicMock()
    first_resp = MagicMock()
    first_resp.text = long_note
    second_resp = MagicMock()
    second_resp.text = short_note
    mock_model.generate_content_async = AsyncMock(side_effect=[first_resp, second_resp])

    with patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel", return_value=mock_model):
        result = await generate_connection_note_template({"title": "QA Lead", "company": "Acme"}, "recruiter")

    assert result == short_note
    assert mock_model.generate_content_async.call_count == 2


@pytest.mark.asyncio
async def test_generate_connection_note_falls_back_when_both_attempts_too_long(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    long_note = "X" * 201

    mock_model = MagicMock()
    resp = MagicMock()
    resp.text = long_note
    mock_model.generate_content_async = AsyncMock(return_value=resp)

    with patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel", return_value=mock_model):
        result = await generate_connection_note_template({"title": "QA Lead", "company": "Acme"}, "russian_speaker")

    assert result == minimal_fallback_template("russian_speaker")
    assert len(result) <= 200


@pytest.mark.asyncio
async def test_generate_connection_note_falls_back_on_llm_exception(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    mock_model = MagicMock()
    mock_model.generate_content_async = AsyncMock(side_effect=Exception("LLM error"))

    with patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel", return_value=mock_model):
        result = await generate_connection_note_template({"title": "QA Lead", "company": "Acme"}, "recruiter")

    assert result == minimal_fallback_template("recruiter")


# --- generate_outreach_templates ---

@pytest.mark.asyncio
async def test_generate_outreach_templates_generates_both_on_empty_contacts():
    job = {"title": "QA Lead", "company": "Acme"}
    recruiter_note = "Hello ______,\n\nAcme is looking for a QA. My experience align well with the requirements.\n\nI would be grateful to connect and share my CV."
    russian_note = "Hello ______,\n\nAcme is looking for a QA. My experience align well with the requirements.\n\nI'd be grateful if you could refer me for the role."

    async def mock_gen(j, audience, log_func=None):
        return recruiter_note if audience == "recruiter" else russian_note

    with patch.object(outreach_module, "generate_connection_note_template", side_effect=mock_gen):
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

    with patch.object(outreach_module, "generate_connection_note_template", side_effect=mock_gen) as mock_fn:
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

    with patch.object(outreach_module, "generate_connection_note_template", side_effect=mock_gen) as mock_fn:
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

    with patch.object(outreach_module, "generate_connection_note_template", side_effect=mock_gen):
        result = await generate_outreach_templates(job, contacts=contacts)

    assert result["recruiter"] == "recruiter template"
    assert result["russian_speaker"] == "russian_speaker template"
