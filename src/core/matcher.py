import os
import json
import asyncio
import inspect
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

RESUMES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "resumes")
MODEL_NAME = "gemini-2.5-flash"


def load_resume(name: str) -> str:
    filepath = os.path.join(RESUMES_DIR, name)
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Resume not found: {name}")
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def _build_prompt(resume: str, job_title: str, company: str, description: str) -> str:
    return f"""You are a resume matcher. Compare the candidate's resume to the job listing and evaluate compatibility.

RESUME:
{resume}

JOB LISTING:
Title: {job_title}
Company: {company}
Description: {description}

Respond with a JSON object (no markdown, no extra text) in this exact format:
{{
  "matchScore": <integer 0-100>,
  "matchType": "<match|no-match>",
  "strengths": ["<strength 1>", "<strength 2>"],
  "gaps": ["<gap 1>", "<gap 2>"],
  "shouldProceed": <true|false>
}}

Rules:
- matchScore >= 75 means matchType is "match" and shouldProceed is true
- List 2-4 concrete strengths and 1-3 specific gaps
"""


async def evaluate_job(job: dict, resume_content: str, log_func=None) -> dict:
    """
    Evaluate a job against a resume using the Gemini API.
    Returns dict with matchScore, matchType, strengths, gaps, shouldProceed.
    Implements exponential backoff on rate limit (429) errors.
    Returns {} if no API key is configured or on unrecoverable error.
    """
    async def log(msg, level="info"):
        if log_func:
            if inspect.iscoroutinefunction(log_func):
                await log_func(msg, level)
            else:
                log_func(msg, level)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        await log("GEMINI_API_KEY not set, skipping evaluation.", "warning")
        return {}

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODEL_NAME)

    prompt = _build_prompt(
        resume_content,
        job.get("title", ""),
        job.get("company", ""),
        job.get("description", "")
    )

    max_retries = 4
    for attempt in range(max_retries):
        try:
            response = await model.generate_content_async(prompt)
            text = response.text.strip()
            return json.loads(text)
        except Exception as e:
            err_str = str(e)
            is_rate_limit = "429" in err_str or "quota" in err_str.lower() or "rate" in err_str.lower()
            if is_rate_limit and attempt < max_retries - 1:
                wait = 2.0 ** attempt
                await log(f"Rate limit hit (attempt {attempt + 1}/{max_retries}). Retrying in {wait:.0f}s...", "warning")
                await asyncio.sleep(wait)
            else:
                await log(f"Gemini API error: {err_str}", "error")
                return {}

    return {}
