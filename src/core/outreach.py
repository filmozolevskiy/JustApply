"""Contact Sample sourcing and Outreach Generator for referral messages."""

import os
import re
import json
import time
import httpx
import asyncio
import inspect
from dotenv import load_dotenv


class ApifyTimeoutError(Exception):
    pass


RECRUITER_CTA = "I would be grateful to connect and share my CV."
RUSSIAN_SPEAKER_CTA = "I'd be grateful if you could refer me for the role."
FIT_LINE = "My experience align well with the requirements."


def minimal_fallback_template(audience: str) -> str:
    cta = RECRUITER_CTA if audience == "recruiter" else RUSSIAN_SPEAKER_CTA
    return f"Hello ______,\n______ at ______.\n{FIT_LINE}\n{cta}"


async def generate_connection_note_template(job: dict, audience: str, log_func=None) -> str:
    """Generate a Connection Note (≤200 chars) for the given audience.

    Retries once with stricter instructions if the first attempt exceeds the limit.
    Falls back to the Minimal Fallback Template when both attempts fail or no API key.
    """
    cta = RECRUITER_CTA if audience == "recruiter" else RUSSIAN_SPEAKER_CTA
    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return minimal_fallback_template(audience)

    title = job.get("title") or ""
    company = job.get("company") or ""

    def _build_prompt(strict: bool = False) -> str:
        prefix = (
            "STRICT: The previous response exceeded 200 characters. "
            "Use aggressive abbreviations to shorten company name and job title.\n\n"
            if strict else ""
        )
        return (
            f"{prefix}Generate a LinkedIn Connection Note for a job application.\n"
            f"Hard limit: 200 characters total (every character counts).\n\n"
            f"Format — use exactly this structure:\n"
            f"Line 1: Hello ______,\n"
            f"Line 2: [company name shortened] – [job title shortened]\n"
            f"Line 3: My experience align well with the requirements.\n"
            f"Line 4: {cta}\n\n"
            f"Rules:\n"
            f"- Use exactly '______' (6 underscores) as the name placeholder in Line 1.\n"
            f"- No posting link. No bullet points. ESL-friendly.\n"
            f"- Return ONLY the Connection Note text.\n\n"
            f"Job: {title} at {company}"
        )

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        response = await model.generate_content_async(_build_prompt())
        text = response.text.strip()
        if len(text) <= 200:
            return text

        response2 = await model.generate_content_async(_build_prompt(strict=True))
        text2 = response2.text.strip()
        if len(text2) <= 200:
            return text2

        return minimal_fallback_template(audience)
    except Exception:
        return minimal_fallback_template(audience)


async def generate_outreach_templates(job: dict, contacts: list, log_func=None) -> dict:
    """Generate Recruiter and Russian Speaker Outreach Templates.

    Generates templates only for audiences that have classified contacts.
    On Enrichment Failure (empty contacts), generates both templates anyway.
    Returns {"recruiter": str, "russian_speaker": str}.
    """
    has_recruiter = any(c.get("is_recruiter") for c in contacts)
    has_russian = any(c.get("russian_speaker") for c in contacts)
    is_enrichment_failure = not contacts

    recruiter_template = ""
    russian_speaker_template = ""

    if has_recruiter or is_enrichment_failure:
        recruiter_template = await generate_connection_note_template(job, "recruiter", log_func)
    if has_russian or is_enrichment_failure:
        russian_speaker_template = await generate_connection_note_template(job, "russian_speaker", log_func)

    return {"recruiter": recruiter_template, "russian_speaker": russian_speaker_template}

APIFY_API_BASE = "https://api.apify.com/v2"
ACTOR_ID = "harvestapi~linkedin-company-employees"
CONTACT_SAMPLE_SIZE = 100

_COMPANY_SUFFIXES = (
    "-technologies", "-technology", "-incorporated", "-corporation",
    "-holdings", "-international", "-solutions", "-services",
    "-inc", "-corp", "-llc", "-ltd", "-group", "-co",
)


def normalize_company_slug(company: str) -> str:
    """Return the primary LinkedIn company slug derived from a display name."""
    return company.lower().strip().replace(" ", "-").replace("_", "-")


def company_slug_candidates(company: str) -> list[str]:
    """Return ordered LinkedIn company slug variants to try for Apify lookup."""
    base = normalize_company_slug(company)
    if not base:
        return []

    candidates = [base]
    first = base.split("-", 1)[0]
    if first and first != base:
        candidates.append(first)

    for suffix in _COMPANY_SUFFIXES:
        if base.endswith(suffix):
            stripped = base[: -len(suffix)]
            if stripped and stripped not in candidates:
                candidates.append(stripped)

    return candidates


async def _fetch_apify_employees_at_url(
    company_url: str,
    *,
    label: str,
    log_func=None,
    timeout_seconds: float = 300.0,
    poll_interval: float = 5.0,
) -> list:
    """Run Apify against one LinkedIn company page URL."""

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
        last_status = None
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
            if status != last_status:
                await log(f"Apify run status: {status}", "info")
                last_status = status

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
        await log(f"Apify returned {len(items)} employees for {label}.", "info")
        return items


async def _run_apify_for_slug(
    slug: str,
    log_func=None,
    timeout_seconds: float = 300.0,
    poll_interval: float = 5.0,
) -> list:
    """Fetch up to CONTACT_SAMPLE_SIZE employees for one LinkedIn company slug via Apify."""
    company_url = f"https://www.linkedin.com/company/{slug}/"
    return await _fetch_apify_employees_at_url(
        company_url,
        label=f"slug '{slug}'",
        log_func=log_func,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
    )


async def _run_apify_for_company_page(
    company_url: str,
    log_func=None,
    timeout_seconds: float = 300.0,
    poll_interval: float = 5.0,
) -> list:
    """Fetch employees using a Bright Data company page URL."""
    normalized = normalize_linkedin_company_url(company_url)
    if not normalized:
        return []
    slug = linkedin_company_slug_from_url(normalized)
    return await _fetch_apify_employees_at_url(
        normalized,
        label=f"company URL '{slug}'",
        log_func=log_func,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
    )


async def _run_apify_actor(
    company: str,
    log_func=None,
    timeout_seconds: float = 300.0,
    poll_interval: float = 5.0,
    company_url: str | None = None,
) -> list:
    """Fetch employees via Apify, preferring Bright Data company_url then slug variants."""

    async def log(msg, level="info"):
        if log_func:
            if inspect.iscoroutinefunction(log_func):
                await log_func(msg, level)
            else:
                log_func(msg, level)

    if company_url:
        try:
            items = await _run_apify_for_company_page(
                company_url,
                log_func=log_func,
                timeout_seconds=timeout_seconds,
                poll_interval=poll_interval,
            )
        except ApifyTimeoutError:
            raise
        if items:
            return items
        await log("No employees at Bright Data company URL; trying name-based slug variants.", "info")

    candidates = company_slug_candidates(company)
    if not candidates:
        await log("No company name for Apify sourcing.", "warning")
        return []

    last_error = None
    for slug in candidates:
        try:
            items = await _run_apify_for_slug(
                slug,
                log_func=log_func,
                timeout_seconds=timeout_seconds,
                poll_interval=poll_interval,
            )
        except ApifyTimeoutError as exc:
            last_error = exc
            raise
        if items:
            if slug != candidates[0]:
                await log(f"Resolved LinkedIn company slug '{slug}' for '{company}'.", "info")
            return items
        if len(candidates) > 1:
            await log(f"No employees for slug '{slug}'; trying next variant.", "info")

    if last_error:
        raise last_error
    return []


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


def company_cache_slug(company: str, company_url: str = "") -> str:
    """Return the cache key slug for a company's Contact Sample."""
    slug = linkedin_company_slug_from_url(company_url)
    if slug:
        return slug
    return normalize_company_slug(company)


def normalize_linkedin_url(url: str) -> str:
    """Return the canonical /in/{slug} path from any LinkedIn profile URL."""
    if not url:
        return ""
    match = re.search(r'/in/([^/?#]+)', url)
    if match:
        return f"/in/{match.group(1)}"
    return ""


def linkedin_company_slug_from_url(url: str) -> str:
    """Return the /company/{slug} segment from a LinkedIn company page URL."""
    if not url:
        return ""
    match = re.search(r'/company/([^/?#]+)', url)
    return match.group(1) if match else ""


def normalize_linkedin_company_url(url: str) -> str:
    """Return a canonical LinkedIn company page URL without query params."""
    slug = linkedin_company_slug_from_url(url)
    if not slug:
        return ""
    return f"https://www.linkedin.com/company/{slug}/"


def _poster_to_apify_item(poster: dict) -> dict:
    """Convert a Job Poster contact dict to an Apify-compatible item for batch classification."""
    name_parts = (poster.get("name") or "").split(None, 1)
    return {
        "firstName": name_parts[0] if name_parts else "",
        "lastName": name_parts[1] if len(name_parts) > 1 else "",
        "headline": poster.get("title") or "",
        "linkedinUrl": poster.get("url") or "",
        "currentPosition": poster.get("title") or "",
        "location": "",
        "languages": [],
    }


async def source_contacts(job: dict, settings=None, log_func=None, bust_cache: bool = False, meta: dict | None = None) -> list:
    """
    Return outreach contacts for a job using LLM classification.

    Checks the Contact Sample Cache first. On cache miss, fetches via Apify and
    writes the result to cache when non-empty. On cache hit, skips the Apify call.
    The Job Poster from existing contacts is included in the same classification
    batch — deduped by normalized LinkedIn URL or injected as a synthetic extra
    when absent. Falls back to classifying the poster alone if no profiles are
    available. Preserves contacted:True from previous contacts matched by
    normalized URL. bust_cache=True deletes the cache entry before lookup.
    """
    from ..schemas import OutreachSettings
    from ..db.cache import get_contact_sample, set_contact_sample, delete_contact_sample
    from ..db.jobs import log_activity

    if settings is None:
        settings = OutreachSettings()

    async def log(msg, level="info"):
        if log_func:
            if inspect.iscoroutinefunction(log_func):
                await log_func(msg, level)
            else:
                log_func(msg, level)

    existing = job.get("contacts") or []
    job_poster = next((c for c in existing if c.get("is_job_poster")), None)
    contacted_by_slug = {
        normalize_linkedin_url(c.get("url", "")): c.get("contacted", False)
        for c in existing
        if normalize_linkedin_url(c.get("url", ""))
    }

    company = job.get("company") or ""
    company_url = job.get("companyUrl") or ""
    if not company:
        await log("No company name for Apify sourcing.", "warning")
        return []

    slug = company_cache_slug(company, company_url)

    if bust_cache:
        delete_contact_sample(slug)

    cache_entry = get_contact_sample(slug)
    if cache_entry:
        display = cache_entry.get("display_name") or company
        fetched_at = cache_entry.get("fetched_at") or ""
        await log(f"Contact Sample Cache hit for '{display}' (fetched {fetched_at}).", "info")
        job_id = job.get("id")
        if job_id:
            log_activity(job_id, f"Contact Sample Cache hit · {display}")
        items = cache_entry["profiles"]
    else:
        await log(f"Fetching up to {CONTACT_SAMPLE_SIZE} employees for '{company}'...", "info")
        try:
            items = await _run_apify_actor(
                company,
                log_func=log_func,
                company_url=company_url or None,
            )
        except ApifyTimeoutError as e:
            await log(f"Apify polling timed out: {e}", "error")
            items = []
        if items:
            set_contact_sample(slug, items, display_name=company)

    poster_slug = normalize_linkedin_url(job_poster.get("url", "")) if job_poster else ""
    fetched_profiles = bool(items)

    if items:
        if job_poster and poster_slug:
            apify_slugs = {
                normalize_linkedin_url(
                    item.get("linkedinUrl") or item.get("linkedInUrl") or
                    item.get("profileUrl") or item.get("url") or ""
                )
                for item in items
            }
            if poster_slug not in apify_slugs:
                await log("Job Poster not in Apify sample; injecting as synthetic profile.", "info")
                items = items + [_poster_to_apify_item(job_poster)]
        contacts = await classify_contacts(items, settings)
    elif job_poster:
        await log("Apify returned no profiles; classifying Job Poster alone.", "warning")
        contacts = await classify_contacts([_poster_to_apify_item(job_poster)], settings)
    else:
        contacts = []

    if meta is not None and not contacts:
        if not fetched_profiles and not job_poster:
            meta["empty_reason"] = "no_employees"
        else:
            meta["empty_reason"] = "no_audience_match"

    poster_slug = normalize_linkedin_url(job_poster.get("url", "")) if job_poster else ""
    for contact in contacts:
        contact_slug = normalize_linkedin_url(contact.get("url", ""))
        if poster_slug and contact_slug == poster_slug:
            contact["is_job_poster"] = True
        if contact_slug in contacted_by_slug:
            contact["contacted"] = contacted_by_slug[contact_slug]

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
