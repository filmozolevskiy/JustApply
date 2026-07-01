import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import src.core.matcher as matcher_module
from src.core.matcher import evaluate_job, evaluate_jobs_batch, load_resume


@pytest.fixture
def mock_gemini_response():
    result = {
        "matchScore": 89,
        "matchType": "match",
        "strengths": ["Python expertise", "CI/CD experience"],
        "gaps": ["No WebUSB experience"],
        "shouldProceed": True,
        "remoteType": "remote",
        "seniority": "senior",
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
    with patch("src.core.matcher.gemini_generate_text", new=AsyncMock(return_value=mock_gemini_response.text)):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            result = await evaluate_job(sample_job, "# QA Resume\nPython expert")

    assert result["matchScore"] == 89
    assert result["matchType"] == "match"
    assert result["shouldProceed"] is True
    assert "Python expertise" in result["strengths"]
    assert "No WebUSB experience" in result["gaps"]
    assert result["remoteType"] == "remote"
    assert result["seniority"] == "senior"
    assert result["summary"] == "This is a mock summary of the job listing."


@pytest.mark.asyncio
async def test_evaluate_job_retries_on_rate_limit(mock_gemini_response, sample_job):
    mock_generate = AsyncMock(side_effect=[
        Exception("429 Too Many Requests"),
        mock_gemini_response.text,
    ])
    with patch("src.core.matcher.gemini_generate_text", mock_generate), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            result = await evaluate_job(sample_job, "resume content")

    assert result["matchScore"] == 89
    assert mock_generate.call_count == 2


@pytest.mark.asyncio
async def test_evaluate_job_returns_empty_when_no_api_key(sample_job):
    env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        result = await evaluate_job(sample_job, "resume content")

    assert result == {}


@pytest.mark.asyncio
async def test_evaluate_job_returns_empty_on_non_rate_limit_error(sample_job):
    with patch("src.core.matcher.gemini_generate_text", new=AsyncMock(side_effect=Exception("Unexpected API error"))):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            result = await evaluate_job(sample_job, "resume content")

    assert result == {}


@pytest.mark.asyncio
async def test_evaluate_job_returns_empty_on_max_retries_exceeded(sample_job):
    with patch("src.core.matcher.gemini_generate_text", new=AsyncMock(side_effect=Exception("429 Rate limit exceeded"))), \
         patch("asyncio.sleep", new_callable=AsyncMock):
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
    assert "seniority" in prompt
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
    from unittest.mock import AsyncMock, patch

    from src.core.matcher import evaluate_job

    recruiter_job = {
        "title": "QA Analyst",
        "company": "Fuze HR Solutions",
        "description": "Our client is looking for a QA analyst...",
        "salary": ""
    }

    with patch("src.core.matcher.gemini_generate_text", new=AsyncMock(return_value='{"matchScore": 90, "matchType": "match", "strengths": ["Python"], "gaps": [], "shouldProceed": true, "remoteType": "remote", "summary": "QA Analyst job", "isRecruiter": false, "salary": "$110k"}')):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            result = await evaluate_job(recruiter_job, "resume content")
            
            assert result["isRecruiter"] is True
            assert result["shouldProceed"] is False
            assert result["matchScore"] == 70
            assert result["matchType"] == "no-match"
            assert "Posted by a recruiting agency/staffing firm" in result["gaps"]
            assert result["salary"] == "$110k"


# --- evaluate_jobs_batch ---

@pytest.mark.asyncio
async def test_evaluate_jobs_batch_evaluates_each_job_sequentially(mock_gemini_response, sample_job):
    second_job = {
        "title": "QA Analyst",
        "company": "OtherCo",
        "description": "Another role.",
    }
    mock_generate = AsyncMock(return_value=mock_gemini_response.text)
    with patch("src.core.matcher.gemini_generate_text", mock_generate), \
         patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
        results = await evaluate_jobs_batch([sample_job, second_job], "resume content")

    assert len(results) == 2
    assert results[0]["matchScore"] == 89
    assert results[1]["matchScore"] == 89
    assert mock_generate.call_count == 2

