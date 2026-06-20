import json
import os
import sys
import pytest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.core.enrichment.connection_note as connection_note_module
from src.core.enrichment.connection_note import (
    FIT_LINE,
    COMPLETE_OUTREACH_OPENER,
    COMPLETE_CANDIDATE_FIT_LINE,
    COMPLETE_RECRUITER_CTA,
    SIGN_OFF,
    assemble_complete_outreach_template,
    complete_outreach_fallback_template,
    complete_outreach_greeting,
    complete_russian_speaker_cta,
    extract_complete_outreach_slots,
    fetch_complete_outreach_slots,
    generate_connection_note_template,
    generate_complete_outreach_template,
    generate_outreach_templates,
    minimal_fallback_template,
    normalize_complete_outreach_bullets,
    parse_complete_outreach_json,
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


def test_minimal_fallback_uses_hi_greeting():
    for audience in ("recruiter", "russian_speaker"):
        result = minimal_fallback_template(audience)
        assert result.startswith("Hi ______,")


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
    for audience in ("recruiter", "russian_speaker"):
        assert FIT_LINE in minimal_fallback_template(audience)


# --- Complete Outreach Fallback ---

def test_complete_outreach_fallback_uses_name_placeholder_and_profile_label():
    job = {"title": "QA Lead", "company": "Acme", "resumeUsed": "qa.md"}
    result = complete_outreach_fallback_template(job, "recruiter")
    assert "______" in result
    assert "QA Lead" in result
    assert "Acme" in result
    assert "QA Automator" in result
    assert len(result) > 200


def test_complete_outreach_fallback_recruiter_cta():
    job = {"title": "Dev", "company": "Corp", "resumeUsed": "qa.md"}
    result = complete_outreach_fallback_template(job, "recruiter")
    assert RECRUITER_CTA in result


def test_complete_outreach_fallback_russian_speaker_cta():
    job = {"title": "Dev", "company": "Corp", "resumeUsed": "qa.md"}
    result = complete_outreach_fallback_template(job, "russian_speaker")
    assert RUSSIAN_SPEAKER_CTA in result


# --- Complete Outreach skeleton helpers ---

def test_complete_outreach_greeting_audience_specific():
    assert complete_outreach_greeting("recruiter") == "Hello ______,"
    assert complete_outreach_greeting("russian_speaker") == "Hi ______,"


def test_parse_complete_outreach_json_strips_markdown_fence():
    raw = '```json\n{"adjustedPositionName": "QA Lead", "bullets": ["A"]}\n```'
    parsed = parse_complete_outreach_json(raw)
    assert parsed["adjustedPositionName"] == "QA Lead"


def test_parse_complete_outreach_json_returns_none_for_invalid_json():
    assert parse_complete_outreach_json("not json") is None


def test_normalize_complete_outreach_bullets_pads_from_strengths():
    bullets = normalize_complete_outreach_bullets(
        ["Python skills"],
        ["Python skills", "CI/CD experience", "Selenium"],
    )
    assert bullets == ["Python skills", "CI/CD experience", "Selenium"]


def test_normalize_complete_outreach_bullets_truncates_to_three():
    bullets = normalize_complete_outreach_bullets(
        ["A", "B", "C", "D"],
        [],
    )
    assert bullets == ["A", "B", "C"]


def test_extract_complete_outreach_slots_falls_back_to_job_title():
    job = {"title": "Senior QA Engineer", "company": "Acme", "strengths": []}
    slots = extract_complete_outreach_slots({}, job)
    assert slots["adjusted_position_name"] == "Senior QA Engineer"
    assert slots["bullets"] == []


def test_normalize_complete_outreach_bullets_strips_trailing_justification():
    bullets = normalize_complete_outreach_bullets(
        ["Developed automated testing frameworks using Selenium and Java, directly matching required skills."],
        [],
    )
    assert bullets == ["Developed automated testing frameworks using Selenium and Java"]


def test_assemble_complete_outreach_spacing_with_link_and_bullets():
    job = {
        "title": "Senior QA Automation Analyst",
        "company": "TELUS Health",
        "link": "https://example.com/job",
    }
    slots = {
        "adjusted_position_name": "Senior QA Automation Analyst",
        "bullets": [
            "Developed automated testing frameworks using Selenium and Java",
            "Proven experience implementing automated workflows with AI agents",
            "Extensive background in API and database validation",
        ],
    }
    result = assemble_complete_outreach_template(job, "russian_speaker", slots)

    expected_block = (
        "TELUS Health is looking for a Senior QA Automation Analyst\n"
        "https://example.com/job\n"
        "\n"
        f"{COMPLETE_CANDIDATE_FIT_LINE}\n"
        "* Developed automated testing frameworks using Selenium and Java\n"
        "* Proven experience implementing automated workflows with AI agents\n"
        "* Extensive background in API and database validation\n"
        "\n"
        f"{complete_russian_speaker_cta('TELUS Health')}"
    )
    assert expected_block in result


def test_assemble_complete_outreach_recruiter_with_link_and_bullets():
    job = {
        "title": "Senior QA Engineer",
        "company": "Acme",
        "link": "http://job.url",
    }
    slots = {
        "adjusted_position_name": "QA Lead",
        "bullets": ["Python skills", "CI/CD", "Selenium"],
    }
    result = assemble_complete_outreach_template(job, "recruiter", slots)

    assert result.startswith("Hello ______,\n\n")
    assert COMPLETE_OUTREACH_OPENER in result
    assert "Acme is looking for a QA Lead" in result
    assert "http://job.url" in result
    assert COMPLETE_CANDIDATE_FIT_LINE in result
    assert "* Python skills" in result
    assert COMPLETE_RECRUITER_CTA in result
    assert result.endswith(SIGN_OFF)


def test_assemble_complete_outreach_russian_speaker_omits_link_when_missing():
    job = {"title": "QA Lead", "company": "Acme", "link": ""}
    slots = {"adjusted_position_name": "QA Lead", "bullets": ["Python"]}
    result = assemble_complete_outreach_template(job, "russian_speaker", slots)

    assert result.startswith("Hi ______,\n\n")
    assert "http://" not in result
    assert complete_russian_speaker_cta("Acme") in result


def test_assemble_complete_outreach_omits_bullet_block_when_empty():
    job = {"title": "QA Lead", "company": "Acme"}
    slots = {"adjusted_position_name": "QA Lead", "bullets": []}
    result = assemble_complete_outreach_template(job, "recruiter", slots)

    assert "* " not in result
    assert COMPLETE_CANDIDATE_FIT_LINE in result


# --- generate_complete_outreach_template ---

@pytest.mark.asyncio
async def test_generate_complete_outreach_falls_back_without_api_key():
    job = {"title": "QA Lead", "company": "Acme", "resumeUsed": "qa.md", "link": "http://job.url", "description": ""}
    with patch("src.core.enrichment.connection_note.load_dotenv"), \
         patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        result = await generate_complete_outreach_template(job, "recruiter")
    assert result == complete_outreach_fallback_template(job, "recruiter")


@pytest.mark.asyncio
async def test_generate_complete_outreach_assembles_from_llm_json(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    llm_json = json.dumps({
        "adjustedPositionName": "QA Lead",
        "bullets": ["Automation", "Python", "CI/CD"],
    })

    with patch("src.core.enrichment.connection_note.load_resume_for_outreach", return_value="resume text"), \
         patch("src.core.enrichment.connection_note.gemini_generate_text", new=AsyncMock(return_value=llm_json)) as mock_generate:
        result = await generate_complete_outreach_template(
            {
                "title": "Senior QA Engineer",
                "company": "Acme",
                "link": "http://job.url",
                "description": "test",
                "resumeUsed": "qa.md",
            },
            "recruiter",
        )

    assert mock_generate.call_count == 1
    assert "Hello ______," in result
    assert "Acme is looking for a QA Lead" in result
    assert "* Automation" in result
    assert COMPLETE_RECRUITER_CTA in result
    assert result.endswith(SIGN_OFF)


@pytest.mark.asyncio
async def test_generate_complete_outreach_best_effort_on_partial_json(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    llm_json = json.dumps({"bullets": ["Only one bullet"]})

    with patch("src.core.enrichment.connection_note.load_resume_for_outreach", return_value="resume text"), \
         patch("src.core.enrichment.connection_note.gemini_generate_text", new=AsyncMock(return_value=llm_json)):
        result = await generate_complete_outreach_template(
            {
                "title": "QA Lead",
                "company": "Acme",
                "resumeUsed": "qa.md",
                "strengths": ["Extra strength"],
            },
            "recruiter",
        )

    assert "Acme is looking for a QA Lead" in result
    assert "* Only one bullet" in result
    assert "* Extra strength" in result


@pytest.mark.asyncio
async def test_generate_complete_outreach_falls_back_on_unparseable_json(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    with patch("src.core.enrichment.connection_note.load_resume_for_outreach", return_value="resume text"), \
         patch("src.core.enrichment.connection_note.gemini_generate_text", new=AsyncMock(return_value="not json")):
        result = await generate_complete_outreach_template(
            {"title": "QA Lead", "company": "Acme", "resumeUsed": "qa.md"},
            "recruiter",
        )

    assert result == complete_outreach_fallback_template(
        {"title": "QA Lead", "company": "Acme", "resumeUsed": "qa.md"},
        "recruiter",
    )


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
    short_note = (
        "Hi ______,\n\nAcme is looking for a QA Lead. "
        f"{FIT_LINE}\n\n{RECRUITER_CTA}"
    )
    assert len(short_note) <= 200

    with patch("src.core.enrichment.connection_note.gemini_generate_text", new=AsyncMock(return_value=short_note)) as mock_generate:
        result = await generate_connection_note_template({"title": "QA Lead", "company": "Acme"}, "recruiter")

    assert result == short_note
    assert mock_generate.call_count == 1


@pytest.mark.asyncio
async def test_generate_connection_note_retries_when_first_result_too_long(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    long_note = "X" * 201
    short_note = (
        "Hi ______,\n\nAcme is looking for a QA. "
        f"{FIT_LINE}\n\n{RECRUITER_CTA}"
    )
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
        result = await generate_connection_note_template(
            {"title": "QA Lead", "company": "Acme"},
            "russian_speaker",
        )

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
    job = {"title": "QA Lead", "company": "Acme", "resumeUsed": "qa.md"}
    contacts = [{"name": "Sarah", "is_recruiter": True, "russian_speaker": False}]
    slots = {"adjusted_position_name": "QA Lead", "bullets": ["Python"]}

    with patch.object(connection_note_module, "fetch_complete_outreach_slots", new=AsyncMock(return_value=slots)) as mock_fetch, \
         patch.object(connection_note_module, "generate_connection_note_template") as mock_short:
        result = await generate_outreach_templates(job, contacts=contacts, short_connection_note=False)

    mock_short.assert_not_called()
    mock_fetch.assert_called_once()
    assert "Hello ______," in result["recruiter"]
    assert COMPLETE_OUTREACH_OPENER in result["recruiter"]
    assert result["russian_speaker"] == ""


@pytest.mark.asyncio
async def test_generate_outreach_templates_complete_uses_single_llm_call_for_both_audiences():
    job = {"title": "QA Lead", "company": "Acme", "resumeUsed": "qa.md"}
    contacts = [
        {"name": "Sarah", "is_recruiter": True, "russian_speaker": False},
        {"name": "Ivan", "is_recruiter": False, "russian_speaker": True},
    ]
    slots = {"adjusted_position_name": "QA Lead", "bullets": ["Python"]}

    with patch.object(connection_note_module, "fetch_complete_outreach_slots", new=AsyncMock(return_value=slots)) as mock_fetch:
        result = await generate_outreach_templates(job, contacts=contacts, short_connection_note=False)

    mock_fetch.assert_called_once()
    assert result["recruiter"].startswith("Hello ______,")
    assert result["russian_speaker"].startswith("Hi ______,")
    assert COMPLETE_RECRUITER_CTA in result["recruiter"]
    assert complete_russian_speaker_cta("Acme") in result["russian_speaker"]


@pytest.mark.asyncio
async def test_generate_outreach_templates_generates_both_on_empty_contacts():
    job = {"title": "QA Lead", "company": "Acme"}
    recruiter_note = (
        "Hi ______,\n\nAcme is looking for a QA. "
        f"{FIT_LINE}\n\n{RECRUITER_CTA}"
    )
    russian_note = (
        "Hi ______,\n\nAcme is looking for a QA. "
        f"{FIT_LINE}\n\n{RUSSIAN_SPEAKER_CTA}"
    )

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
