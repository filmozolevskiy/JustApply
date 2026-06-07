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


def _build_prompt(resume: str, job_title: str, company: str, description: str, allowed_remote_types: list = None) -> str:
    allowed_str = "any"
    if allowed_remote_types:
        normalized_types = [t.lower().strip() for t in allowed_remote_types if t]
        if "any" not in normalized_types:
            allowed_str = ", ".join(normalized_types)

    return f"""You are a resume matcher. Compare the candidate's resume to the job listing and evaluate compatibility.

RESUME:
{resume}

JOB LISTING:
Title: {job_title}
Company: {company}
Description: {description}

Candidate's Allowed Remote Preferences: {allowed_str}

Respond with a JSON object (no markdown, no extra text) in this exact format:
{{
  "matchScore": <integer 0-100>,
  "matchType": "<match|no-match>",
  "strengths": ["<strength 1>", "<strength 2>"],
  "gaps": ["<gap 1>", "<gap 2>"],
  "shouldProceed": <true|false>,
  "remoteType": "<remote|hybrid|in_office>",
  "summary": "<concise 2-3 sentence summary of the job listing, including key tech stack/responsibilities>"
}}

Rules:
- matchScore >= 75 means matchType is "match" and shouldProceed is true.
- List 2-4 concrete strengths and 1-3 specific gaps.
- Analyze the Job Title, Location, and Description to determine the job's remote status ("remoteType"). It must be exactly one of: "remote", "hybrid", "in_office".
  * "remote" means work from home/anywhere, no office presence required.
  * "hybrid" means part-time in office, part-time remote.
  * "in_office" means fully in office.
- If Candidate's Allowed Remote Preferences is not "any":
  * Check if the determined "remoteType" is one of the allowed remote preferences (e.g., if preferences are "remote" and the job is "hybrid" or "in_office", it is a mismatch).
  * If there is a mismatch: you MUST set "shouldProceed" to false, add the mismatch discrepancy to the "gaps" list (e.g., "Job is hybrid/in-office, but candidate prefers remote-only"), and lower the "matchScore" to be below 75 (typically between 30 and 60 depending on other factors).
"""


async def evaluate_job(job: dict, resume_content: str, log_func=None, allowed_remote_types: list = None) -> dict:
    """
    Evaluate a job against a resume using the Gemini API.
    Returns dict with matchScore, matchType, strengths, gaps, shouldProceed, remoteType, summary.
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
        job.get("description", ""),
        allowed_remote_types
    )

    max_retries = 4
    for attempt in range(max_retries):
        try:
            response = await model.generate_content_async(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                lines = text.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()
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
