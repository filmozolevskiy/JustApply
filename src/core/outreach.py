"""Contact Sample sourcing and Outreach Generator for referral messages."""

import os
import json
import time
import httpx
import asyncio
import inspect
from dotenv import load_dotenv


class ApifyTimeoutError(Exception):
    pass

APIFY_API_BASE = "https://api.apify.com/v2"
ACTOR_ID = "harvestapi~linkedin-company-employees"
CONTACT_SAMPLE_SIZE = 100



async def _run_apify_actor(company: str, log_func=None, timeout_seconds: float = 300.0, poll_interval: float = 5.0) -> list:
    """Fetch up to CONTACT_SAMPLE_SIZE employees for a company via Apify."""

    async def log(msg, level="info"):
        if log_func:
            if inspect.iscoroutinefunction(log_func):
                await log_func(msg, level)
            else:
                log_func(msg, level)

    load_dotenv(override=True)
    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        await log("APIFY_API_TOKEN not set, skipping Apify sourcing.", "warning")
        return []

    slug = company.lower().strip().replace(" ", "-").replace("_", "-")
    company_url = f"https://www.linkedin.com/company/{slug}/"
    actor_input = {"companies": [company_url], "maxItems": CONTACT_SAMPLE_SIZE}

    run_url = f"{APIFY_API_BASE}/acts/{ACTOR_ID}/runs"
    params = {"token": api_token}
    headers = {"Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(run_url, params=params, headers=headers, json=actor_input)
        if resp.status_code not in (200, 201):
            await log(f"Apify trigger failed: HTTP {resp.status_code}", "error")
            return []

        run_id = resp.json().get("data", {}).get("id")
        if not run_id:
            await log("Apify did not return a run ID.", "error")
            return []

        await log(f"Apify run started: {run_id}", "info")

        status_url = f"{APIFY_API_BASE}/actor-runs/{run_id}"
        start_time = time.monotonic()
        while True:
            if time.monotonic() - start_time >= timeout_seconds:
                raise ApifyTimeoutError(
                    f"Apify run {run_id} did not complete within {timeout_seconds}s"
                )
            await asyncio.sleep(poll_interval)
            status_resp = await client.get(status_url, params=params)
            if status_resp.status_code != 200:
                await log(f"Apify status check error: HTTP {status_resp.status_code}", "warning")
                continue

            run_data = status_resp.json().get("data", {})
            status = run_data.get("status")
            await log(f"Apify run status: {status}", "info")

            if status == "SUCCEEDED":
                dataset_id = run_data.get("defaultDatasetId")
                break
            if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                await log(f"Apify run ended with status: {status}", "error")
                return []

        dataset_url = f"{APIFY_API_BASE}/datasets/{dataset_id}/items"
        data_resp = await client.get(dataset_url, params={**params, "format": "json"})
        if data_resp.status_code != 200:
            await log(f"Apify dataset fetch error: HTTP {data_resp.status_code}", "error")
            return []

        items = data_resp.json()
        await log(f"Apify returned {len(items)} employees.", "info")
        return items


def _normalize_apify_employee(item: dict) -> dict:
    first = item.get("firstName") or ""
    last = item.get("lastName") or ""
    full = f"{first} {last}".strip() or item.get("fullName") or item.get("name") or ""

    return {
        "name": full,
        "title": item.get("headline") or item.get("title") or "",
        "url": item.get("linkedinUrl") or item.get("linkedInUrl") or item.get("profileUrl") or item.get("url") or "",
        "contacted": False,
        "russian_speaker": False,
        "is_recruiter": False,
        "currentPosition": item.get("currentPosition") or "",
        "location": item.get("location") or "",
    }


async def source_contacts(job: dict, settings=None, log_func=None) -> list:
    """
    Return outreach contacts for a job using LLM classification.

    1. If the job already has contacts, return them as-is.
    2. Fetch up to CONTACT_SAMPLE_SIZE employees via Apify.
    3. Classify via classify_contacts using the provided OutreachSettings.
    """
    from ..schemas import OutreachSettings
    if settings is None:
        settings = OutreachSettings()

    async def log(msg, level="info"):
        if log_func:
            if inspect.iscoroutinefunction(log_func):
                await log_func(msg, level)
            else:
                log_func(msg, level)

    existing = job.get("contacts") or []
    if existing:
        await log(f"Using direct poster contact: {existing[0].get('name', 'Unknown')}", "info")
        return existing

    company = job.get("company") or ""
    if not company:
        await log("No company name for Apify sourcing.", "warning")
        return []

    await log(f"Fetching up to {CONTACT_SAMPLE_SIZE} employees for '{company}'...", "info")
    try:
        items = await _run_apify_actor(company, log_func=log_func)
    except ApifyTimeoutError as e:
        await log(f"Apify polling timed out: {e}", "error")
        return []
    if not items:
        return []

    contacts = await classify_contacts(items, settings)
    await log(f"Found {len(contacts)} classified contact(s).", "info")
    return contacts


async def classify_contacts(items: list, settings) -> list:
    """
    Send a single batch Gemini prompt to classify raw Apify profiles.

    Returns Contact-like dicts with russian_speaker and is_recruiter flags set.
    At most 5 contacts per audience type. Contacts matching neither type are excluded.
    """
    if not items:
        return []

    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return []

    profiles = []
    for i, item in enumerate(items):
        normalized = _normalize_apify_employee(item)
        lang_list = ", ".join(
            lang.get("name", "") for lang in (item.get("languages") or [])
            if isinstance(lang, dict)
        )
        profiles.append(
            f"[{i}] Name: {normalized['name']}, Title: {normalized['title']}, "
            f"Languages: {lang_list}, Position: {normalized['currentPosition']}, "
            f"Location: {normalized['location']}"
        )

    prompt = (
        "Classify each LinkedIn profile into one or both of:\n"
        "- Russian Speaker: speaks Russian, Ukrainian, or Belarusian\n"
        "- Recruiter/HR: works in recruiting, HR, talent acquisition, or people ops\n\n"
        "Profiles:\n" + "\n".join(profiles) + "\n\n"
        'Return a JSON array of only matching profiles. '
        'Format: [{"index": 0, "russian_speaker": true, "is_recruiter": false}, ...]\n'
        "Return [] if no profiles match. Return only valid JSON, no markdown."
    )

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = await model.generate_content_async(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        classified = json.loads(text)
    except Exception:
        return []

    russian_count = 0
    recruiter_count = 0
    result = []

    for entry in classified:
        idx = entry.get("index")
        if idx is None or not isinstance(idx, int) or idx >= len(items):
            continue

        wants_russian = bool(entry.get("russian_speaker")) and settings.target_russian_speakers
        wants_recruiter = bool(entry.get("is_recruiter")) and settings.target_recruiters

        add_russian = wants_russian and russian_count < 5
        add_recruiter = wants_recruiter and recruiter_count < 5

        if not add_russian and not add_recruiter:
            continue

        contact = _normalize_apify_employee(items[idx])
        contact["russian_speaker"] = add_russian
        contact["is_recruiter"] = add_recruiter

        if add_russian:
            russian_count += 1
        if add_recruiter:
            recruiter_count += 1

        result.append(contact)

    return result


def load_resume_for_outreach(resume_name: str) -> str:
    from .matcher import load_resume
    try:
        return load_resume(resume_name)
    except Exception:
        pass
    try:
        return load_resume("qa.md")
    except Exception:
        return ""


def build_russian_speaker_prompt(
    resume: str,
    job_title: str,
    company: str,
    job_link: str,
    description: str,
    contact_name: str,
) -> str:
    return f"""You are a helpful assistant writing a professional LinkedIn outreach message from a job candidate.

CANDIDATE RESUME:
{resume}

JOB DETAILS:
Title: {job_title}
Company: {company}
Posting: {job_link}
Description/Summary: {description}

RECIPIENT:
Name: {contact_name}

INSTRUCTIONS:
1. Greet the person in English (e.g. 'Hello {contact_name},').
2. Keep the message concise (100-150 words), professional, and polite.
3. Mention the job title, company name, and include the job posting link.
4. Highlight 1-2 matching strengths from the resume relevant to the job description, as bullet points.
5. End with a referral program ask — ask if they'd be willing to refer you, and offer to share your CV.
6. Do not include any placeholder text. Output the final draft directly. No markdown formatting, just the raw text of the message.
"""


def build_recruiter_prompt(
    resume: str,
    job_title: str,
    company: str,
    job_link: str,
    description: str,
    contact_name: str,
) -> str:
    return f"""You are a helpful assistant writing a professional LinkedIn outreach message from a job candidate to a recruiter or HR professional.

CANDIDATE RESUME:
{resume}

JOB DETAILS:
Title: {job_title}
Company: {company}
Posting: {job_link}
Description/Summary: {description}

RECIPIENT:
Name: {contact_name}

INSTRUCTIONS:
1. Greet the person in English (e.g. 'Hello {contact_name},').
2. Keep the message concise (100-150 words), professional, and polite.
3. Mention the job title, company name, and include the job posting link.
4. Highlight 1-2 matching strengths from the resume relevant to the job description, as bullet points.
5. End with a direct invitation to connect and an offer to share your CV. Do not ask for introductions to third parties.
6. Do not include any placeholder text. Output the final draft directly. No markdown formatting, just the raw text of the message.
"""


async def generate_outreach_message(
    job: dict,
    contact_name: str,
    is_russian: bool,
    resume_content: str,
    is_recruiter: bool = False,
) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key and resume_content:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            job_link = job.get("link", "")
            if is_recruiter:
                prompt = build_recruiter_prompt(
                    resume_content,
                    job.get("title", ""),
                    job.get("company", ""),
                    job_link,
                    job.get("description", ""),
                    contact_name,
                )
            else:
                prompt = build_russian_speaker_prompt(
                    resume_content,
                    job.get("title", ""),
                    job.get("company", ""),
                    job_link,
                    job.get("description", ""),
                    contact_name,
                )
            response = await model.generate_content_async(prompt)
            return response.text.strip()
        except Exception:
            pass

    resume_name = job.get("resumeUsed") or "qa.md"
    profile_name = (
        "QA Automator" if resume_name == "qa.md"
        else "Delivery Manager" if resume_name == "project_manager.md"
        else "BI Analyst"
    )
    return (
        f"Hello {contact_name},\n\n"
        f"I recently saw your post for the {job.get('title', '')} role at "
        f"{job.get('company', '')}. Based on my matched skills in {resume_name} ({profile_name}), "
        f"I believe my background aligning developer suites and testing cycles matches your goals.\n\n"
        f"Let me know if we can schedule a quick discussion!\n\nBest,\nCandidate"
    )


async def generate_outreach_for_job(job: dict, contacts: list) -> str:
    """Outreach Generator: load resume profile and draft message for the primary contact."""
    primary = contacts[0] if contacts else None
    contact_name = primary.get("name") if primary else "Hiring Manager"
    is_russian = bool(primary.get("russian_speaker")) if primary else False
    is_recruiter = bool(primary.get("is_recruiter")) if primary else False
    resume_name = job.get("resumeUsed") or "qa.md"
    resume_content = load_resume_for_outreach(resume_name)
    return await generate_outreach_message(job, contact_name, is_russian, resume_content, is_recruiter=is_recruiter)
