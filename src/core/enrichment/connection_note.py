"""Outreach Generator: Connection Note templates for Enrichment."""

import asyncio
import os
from dotenv import load_dotenv

from ...db.job_model import coerce_job
from ...schemas import Job
from ..gemini_client import generate_text as gemini_generate_text

RECRUITER_CTA = "I would be grateful to connect and share my CV."
RUSSIAN_SPEAKER_CTA = "I'd be grateful if you could refer me for the role."
FIT_LINE = "My experience align well with the requirements."
GEMINI_TIMEOUT_SECONDS = 30.0


def minimal_fallback_template(audience: str, job: Job | None = None) -> str:
    """Hardcoded Connection Note when LLM generation fails. Keeps name placeholder only."""
    job = coerce_job(job) if job else None
    cta = RECRUITER_CTA if audience == "recruiter" else RUSSIAN_SPEAKER_CTA
    company = (job.company if job else "") or "______"
    title = (job.title if job else "") or "______"

    def _build(c: str, t: str) -> str:
        return (
            f"Hello ______,\n\n"
            f"{c} is looking for a {t}. {FIT_LINE}\n\n"
            f"{cta}"
        )

    text = _build(company, title)
    if len(text) <= 200:
        return text

    for max_len in (30, 24, 18, 12, 8, 5):
        short_company = company[:max_len].rstrip() or company[:max_len]
        short_title = title[:max_len].rstrip() or title[:max_len]
        text = _build(short_company, short_title)
        if len(text) <= 200:
            return text

    return _build("Co", "role")


def _resume_profile_label(resume_name: str) -> str:
    if resume_name == "qa.md":
        return "QA Automator"
    if resume_name == "project_manager.md":
        return "Delivery Manager"
    return "BI Analyst"


def complete_outreach_fallback_template(job: Job, audience: str) -> str:
    """Hardcoded Complete Outreach Message when LLM generation fails."""
    job = coerce_job(job)
    cta = RECRUITER_CTA if audience == "recruiter" else RUSSIAN_SPEAKER_CTA
    title = job.title or ""
    company = job.company or ""
    profile_name = _resume_profile_label(job.resumeUsed or "qa.md")
    return (
        f"Hello ______,\n\n"
        f"I recently saw the {title} role at {company}. Based on my matched skills "
        f"({profile_name}), I believe my background aligns well with your goals.\n\n"
        f"Let me know if we can schedule a quick discussion.\n\n"
        f"{cta}"
    )


def load_resume_for_outreach(resume_name: str) -> str:
    from ..matcher import load_resume
    try:
        return load_resume(resume_name)
    except Exception:
        pass
    try:
        return load_resume("qa.md")
    except Exception:
        return ""


def _build_complete_recruiter_prompt(
    resume: str,
    job_title: str,
    company: str,
    job_link: str,
    description: str,
) -> str:
    return f"""You are a helpful assistant writing a professional LinkedIn outreach message from a job candidate to a recruiter or HR professional.

CANDIDATE RESUME:
{resume}

JOB DETAILS:
Title: {job_title}
Company: {company}
Posting: {job_link}
Description/Summary: {description}

INSTRUCTIONS:
1. Greet the person in English using exactly 'Hello ______,' as the first line (6 underscores as name placeholder).
2. Keep the message concise (100-150 words), professional, and polite.
3. Mention the job title, company name, and include the job posting link.
4. Highlight 1-2 matching strengths from the resume relevant to the job description, as bullet points.
5. End with: {RECRUITER_CTA}
6. Do not include any other placeholder text. Output the final draft directly. No markdown formatting, just the raw text of the message.
"""


def _build_complete_russian_speaker_prompt(
    resume: str,
    job_title: str,
    company: str,
    job_link: str,
    description: str,
) -> str:
    return f"""You are a helpful assistant writing a professional LinkedIn outreach message from a job candidate.

CANDIDATE RESUME:
{resume}

JOB DETAILS:
Title: {job_title}
Company: {company}
Posting: {job_link}
Description/Summary: {description}

INSTRUCTIONS:
1. Greet the person in English using exactly 'Hello ______,' as the first line (6 underscores as name placeholder).
2. Keep the message concise (100-150 words), professional, and polite.
3. Mention the job title, company name, and include the job posting link.
4. Highlight 1-2 matching strengths from the resume relevant to the job description, as bullet points.
5. End with a referral program ask — ask if they'd be willing to refer you, and offer to share your CV.
6. Do not include any other placeholder text. Output the final draft directly. No markdown formatting, just the raw text of the message.
"""


async def generate_complete_outreach_template(job: Job, audience: str, log_func=None) -> str:
    """Generate a Complete Outreach Message (~100-150 words) for the given audience."""
    job = coerce_job(job)
    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY")
    resume_name = job.resumeUsed or "qa.md"
    resume_content = load_resume_for_outreach(resume_name)

    if not api_key or not resume_content:
        return complete_outreach_fallback_template(job, audience)

    title = job.title or ""
    company = job.company or ""
    job_link = job.link or ""
    description = job.description or ""

    if audience == "recruiter":
        prompt = _build_complete_recruiter_prompt(resume_content, title, company, job_link, description)
    else:
        prompt = _build_complete_russian_speaker_prompt(resume_content, title, company, job_link, description)

    try:
        return await gemini_generate_text(prompt, timeout=GEMINI_TIMEOUT_SECONDS)
    except Exception:
        return complete_outreach_fallback_template(job, audience)


async def generate_connection_note_template(job: Job, audience: str, log_func=None) -> str:
    """Generate a Connection Note (≤200 chars) for the given audience.

    Retries once with stricter instructions if the first attempt exceeds the limit.
    Falls back to the Minimal Fallback Template when both attempts fail or no API key.
    """
    job = coerce_job(job)
    cta = RECRUITER_CTA if audience == "recruiter" else RUSSIAN_SPEAKER_CTA
    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return minimal_fallback_template(audience, job)

    title = job.title or ""
    company = job.company or ""

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
            f"Line 2: (blank line)\n"
            f"Line 3: [company name shortened] is looking for a [job title shortened]. "
            f"My experience align well with the requirements.\n"
            f"Line 4: (blank line)\n"
            f"Line 5: {cta}\n\n"
            f"Rules:\n"
            f"- Use exactly '______' (6 underscores) as the name placeholder in Line 1.\n"
            f"- No posting link. No bullet points. ESL-friendly.\n"
            f"- Return ONLY the Connection Note text.\n\n"
            f"Job: {title} at {company}"
        )

    try:
        text = await gemini_generate_text(_build_prompt(), timeout=GEMINI_TIMEOUT_SECONDS)
        if len(text) <= 200:
            return text

        text2 = await gemini_generate_text(
            _build_prompt(strict=True),
            timeout=GEMINI_TIMEOUT_SECONDS,
        )
        if len(text2) <= 200:
            return text2

        return minimal_fallback_template(audience, job)
    except Exception:
        return minimal_fallback_template(audience, job)


async def generate_outreach_templates(
    job: Job,
    contacts: list,
    log_func=None,
    *,
    short_connection_note: bool = True,
) -> dict:
    """Generate Recruiter and Russian Speaker Outreach Templates.

    Generates templates only for audiences that have classified contacts.
    On Enrichment Failure (empty contacts), generates both templates anyway.
    Returns {"recruiter": str, "russian_speaker": str}.
    """
    job = coerce_job(job)
    has_recruiter = any(c.get("is_recruiter") for c in contacts)
    has_russian = any(c.get("russian_speaker") for c in contacts)
    is_enrichment_failure = not contacts

    generate_template = (
        generate_connection_note_template
        if short_connection_note
        else generate_complete_outreach_template
    )

    recruiter_template = ""
    russian_speaker_template = ""

    async def _generate(audience: str) -> tuple[str, str]:
        return audience, await generate_template(job, audience, log_func)

    pending = []
    if has_recruiter or is_enrichment_failure:
        pending.append(_generate("recruiter"))
    if has_russian or is_enrichment_failure:
        pending.append(_generate("russian_speaker"))

    for audience, template in await asyncio.gather(*pending):
        if audience == "recruiter":
            recruiter_template = template
        else:
            russian_speaker_template = template

    return {"recruiter": recruiter_template, "russian_speaker": russian_speaker_template}
