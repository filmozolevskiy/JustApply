import os
import sys
import json
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import src.core.matcher as matcher_module
from src.core.matcher import evaluate_job, load_resume


@pytest.fixture
def mock_gemini_response():
    result = {
        "matchScore": 89,
        "matchType": "match",
        "strengths": ["Python expertise", "CI/CD experience"],
        "gaps": ["No WebUSB experience"],
        "shouldProceed": True,
        "remoteType": "remote",
        "summary": "This is a mock summary of the job listing."
    }
    response = MagicMock()
    response.text = json.dumps(result)
    return response


@pytest.fixture
def sample_job():
    return {
        "title": "Senior QA Automation Engineer",
        "company": "TechCorp",
        "description": "We need a QA engineer with Python and Pytest experience."
    }


# --- load_resume ---

def test_load_resume_returns_content(tmp_path, monkeypatch):
    resume_dir = tmp_path / "resumes"
    resume_dir.mkdir()
    (resume_dir / "qa.md").write_text("# QA Resume\nPython expert")
    monkeypatch.setattr(matcher_module, "RESUMES_DIR", str(resume_dir))

    content = load_resume("qa.md")
    assert content == "# QA Resume\nPython expert"


def test_load_resume_raises_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(matcher_module, "RESUMES_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        load_resume("nonexistent.md")


# --- evaluate_job ---

@pytest.mark.asyncio
async def test_evaluate_job_returns_structured_result(mock_gemini_response, sample_job):
    with patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel") as mock_model_cls:
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_gemini_response)
        mock_model_cls.return_value = mock_model

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            result = await evaluate_job(sample_job, "# QA Resume\nPython expert")

    assert result["matchScore"] == 89
    assert result["matchType"] == "match"
    assert result["shouldProceed"] is True
    assert "Python expertise" in result["strengths"]
    assert "No WebUSB experience" in result["gaps"]
    assert result["remoteType"] == "remote"
    assert result["summary"] == "This is a mock summary of the job listing."


@pytest.mark.asyncio
async def test_evaluate_job_retries_on_rate_limit(mock_gemini_response, sample_job):
    with patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel") as mock_model_cls, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(side_effect=[
            Exception("429 Too Many Requests"),
            mock_gemini_response
        ])
        mock_model_cls.return_value = mock_model

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            result = await evaluate_job(sample_job, "resume content")

    assert result["matchScore"] == 89
    assert mock_model.generate_content_async.call_count == 2


@pytest.mark.asyncio
async def test_evaluate_job_returns_empty_when_no_api_key(sample_job):
    env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        result = await evaluate_job(sample_job, "resume content")

    assert result == {}


@pytest.mark.asyncio
async def test_evaluate_job_returns_empty_on_non_rate_limit_error(sample_job):
    with patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel") as mock_model_cls:
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(side_effect=Exception("Unexpected API error"))
        mock_model_cls.return_value = mock_model

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            result = await evaluate_job(sample_job, "resume content")

    assert result == {}


@pytest.mark.asyncio
async def test_evaluate_job_returns_empty_on_max_retries_exceeded(sample_job):
    with patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel") as mock_model_cls, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(
            side_effect=Exception("429 Rate limit exceeded")
        )
        mock_model_cls.return_value = mock_model

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            result = await evaluate_job(sample_job, "resume content")

    assert result == {}


# --- Pipeline integration: mock_eval applied via scraping endpoint ---

@pytest.mark.asyncio
async def test_evaluate_job_logs_warning_when_skipping(sample_job):
    log_messages = []

    async def capture_log(msg, level="info"):
        log_messages.append((level, msg))

    env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        result = await evaluate_job(sample_job, "resume", log_func=capture_log)

    assert result == {}
    assert any("GEMINI_API_KEY" in msg for _, msg in log_messages)


def test_build_prompt_formatting():
    from src.core.matcher import _build_prompt

    prompt = _build_prompt(
        resume="My Resume",
        job_title="QA",
        company="Google",
        description="A job description",
    )
    assert "remoteType" in prompt
    assert "summary" in prompt
    assert "Allowed Remote Preferences" not in prompt


def test_recruiter_company_detection_local():
    from src.core.matcher import check_recruiter_by_name
    assert check_recruiter_by_name("Fuze HR Solutions") is True
    assert check_recruiter_by_name("Randstad Canada") is True
    assert check_recruiter_by_name("Google Inc.") is False
    assert check_recruiter_by_name("Air Canada") is False


@pytest.mark.asyncio
async def test_evaluate_job_applies_recruiter_override():
    from src.core.matcher import evaluate_job
    from unittest.mock import patch, MagicMock, AsyncMock

    recruiter_job = {
        "title": "QA Analyst",
        "company": "Fuze HR Solutions",
        "description": "Our client is looking for a QA analyst...",
        "salary": ""
    }

    with patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel") as mock_model_cls:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"matchScore": 90, "matchType": "match", "strengths": ["Python"], "gaps": [], "shouldProceed": true, "remoteType": "remote", "summary": "QA Analyst job", "isRecruiter": false, "salary": "$110k"}'
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_model_cls.return_value = mock_model

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            result = await evaluate_job(recruiter_job, "resume content")
            
            assert result["isRecruiter"] is True
            assert result["shouldProceed"] is False
            assert result["matchScore"] == 70
            assert result["matchType"] == "no-match"
            assert "Posted by a recruiting agency/staffing firm" in result["gaps"]
            assert result["salary"] == "$110k"

