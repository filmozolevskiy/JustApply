"""Outreach Generator: Connection Note templates for Enrichment."""

import asyncio
import json
import os
import re
from dotenv import load_dotenv

from ...db.job_model import coerce_job
from ...schemas import Job
from ..gemini_client import generate_text as gemini_generate_text

RECRUITER_CTA = "I would be grateful to connect and share my CV."
RUSSIAN_SPEAKER_CTA = "I'd be grateful if you could refer me for the role."
FIT_LINE = "My experience aligns well with the requirements."
COMPLETE_OUTREACH_OPENER = "I don't want to waste your time, so let me get right to the point."
COMPLETE_CANDIDATE_FIT_LINE = (
    "I think I'm the right candidate because my experience aligns well with the requirements."
)
COMPLETE_RECRUITER_CTA = (
    "I'd be grateful if you could consider my candidacy for this opportunity. "
    "Let me know if I can share my CV or any details with you."
)
SIGN_OFF = "Best regards,"
GEMINI_TIMEOUT_SECONDS = 30.0


def complete_russian_speaker_cta(company: str) -> str:
    return (
        f"If {company} has a referral program, I'd be grateful if you could refer me for the role. "
        f"Let me know if I can share my CV or any details that would make the process easier for you."
    )


def complete_outreach_greeting(audience: str) -> str:
    return "Hello ______," if audience == "recruiter" else "Hi ______,"


def minimal_fallback_template(audience: str, job: Job | None = None) -> str:
    """Hardcoded Connection Note when LLM generation fails. Keeps name placeholder only."""
    job = coerce_job(job) if job else None
    cta = RECRUITER_CTA if audience == "recruiter" else RUSSIAN_SPEAKER_CTA
    company = (job.company if job else "") or "______"
    title = (job.title if job else "") or "______"

    def _build(c: str, t: str) -> str:
        return (
            f"Hi ______,\n\n"
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
    if resume_name == "general_cv.md":
        return "Delivery, QA & Data"
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
    profile_name = _resume_profile_label(job.resumeUsed or "general_cv.md")
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
        return load_resume("general_cv.md")
    except Exception:
        return ""


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_complete_outreach_json(raw: str) -> dict | None:
    try:
        parsed = json.loads(_strip_json_fence(raw))
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def normalize_complete_outreach_bullets(
    llm_bullets: object,
    strengths: list[str] | None,
) -> list[str]:
    bullets: list[str] = []
    seen: set[str] = set()

    def _trim_bullet_phrase(text: str) -> str:
        match = re.search(
            r",\s*(?:directly|aligning|matching|ensuring|which|as required)\b",
            text,
            re.I,
        )
        if match:
            text = text[: match.start()]
        return text.strip().rstrip(",")

    def _add(item: object) -> None:
        if not isinstance(item, str):
            return
        cleaned = _trim_bullet_phrase(item.strip().lstrip("*-• ").strip())
        if not cleaned:
            return
        key = cleaned.casefold()
        if key in seen:
            return
        seen.add(key)
        bullets.append(cleaned)

    if isinstance(llm_bullets, list):
        for bullet in llm_bullets:
            _add(bullet)
            if len(bullets) >= 3:
                break

    for strength in strengths or []:
        if len(bullets) >= 3:
            break
        _add(strength)

    return bullets[:3]


def extract_complete_outreach_slots(parsed: dict, job: Job) -> dict:
    job = coerce_job(job)
    title = job.title or ""
    adjusted = parsed.get("adjustedPositionName") or parsed.get("adjusted_position_name") or ""
    if isinstance(adjusted, str):
        adjusted = adjusted.strip()
    if not adjusted:
        adjusted = title

    bullets_raw = parsed.get("bullets")
    if bullets_raw is None:
        bullets_raw = parsed.get("strengthBullets") or parsed.get("strength_bullets") or []

    bullets = normalize_complete_outreach_bullets(bullets_raw, job.strengths or [])
    return {"adjusted_position_name": adjusted, "bullets": bullets}


def assemble_complete_outreach_template(job: Job, audience: str, slots: dict) -> str:
    job = coerce_job(job)
    company = job.company or ""
    link = job.link or ""
    adjusted = slots.get("adjusted_position_name") or job.title or ""
    bullets = slots.get("bullets") or []

    parts = [
        complete_outreach_greeting(audience),
        "",
        COMPLETE_OUTREACH_OPENER,
        "",
        f"{company} is looking for a {adjusted}",
    ]
    if link:
        parts.append(link)
    parts.extend(["", COMPLETE_CANDIDATE_FIT_LINE])
    if bullets:
        parts.extend(f"* {bullet}" for bullet in bullets)
    cta = COMPLETE_RECRUITER_CTA if audience == "recruiter" else complete_russian_speaker_cta(company)
    parts.extend(["", cta, "", SIGN_OFF])
    return "\n".join(parts)


def _build_complete_outreach_json_prompt(
    resume: str,
    job_title: str,
    company: str,
    job_link: str,
    description: str,
) -> str:
    return f"""You are a helpful assistant matching a candidate resume to a job posting.

CANDIDATE RESUME:
{resume}

JOB DETAILS:
Title: {job_title}
Company: {company}
Posting: {job_link}
Description/Summary: {description}

Return ONLY valid JSON with this exact shape:
{{
  "adjustedPositionName": "<short natural job title for the sentence '{company} is looking for a ...'>",
  "bullets": ["<strength 1>", "<strength 2>", "<strength 3>"]
}}

Rules:
- adjustedPositionName: shorten or rephrase the raw title so it reads naturally in that sentence.
- bullets: exactly three short resume-matched strengths (under 12 words each). State the skill or experience only — no trailing justification (avoid phrases like "directly matching required skills" or "aligning with the job's focus").
- Output JSON only. No markdown fences or extra text.
"""


async def fetch_complete_outreach_slots(job: Job, log_func=None) -> dict | None:
    """Fetch Adjusted Position Name and bullets via one structured LLM call."""
    job = coerce_job(job)
    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY")
    resume_name = job.resumeUsed or "general_cv.md"
    resume_content = load_resume_for_outreach(resume_name)

    if not api_key or not resume_content:
        return None

    title = job.title or ""
    company = job.company or ""
    job_link = job.link or ""
    description = job.description or ""
    prompt = _build_complete_outreach_json_prompt(
        resume_content, title, company, job_link, description
    )

    try:
        raw = await gemini_generate_text(prompt, timeout=GEMINI_TIMEOUT_SECONDS)
    except Exception:
        return None

    parsed = parse_complete_outreach_json(raw)
    if parsed is None:
        return None

    return extract_complete_outreach_slots(parsed, job)


async def generate_complete_outreach_template(
    job: Job,
    audience: str,
    log_func=None,
    *,
    slots: dict | None = None,
) -> str:
    """Generate a Complete Outreach Message (~100-150 words) for the given audience."""
    job = coerce_job(job)
    if slots is None:
        slots = await fetch_complete_outreach_slots(job, log_func)
    if slots is None:
        return complete_outreach_fallback_template(job, audience)
    return assemble_complete_outreach_template(job, audience, slots)


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
            f"Line 1: Hi ______,\n"
            f"Line 2: (blank line)\n"
            f"Line 3: [company name shortened] is looking for a [job title shortened]. "
            f"{FIT_LINE}\n"
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

    recruiter_template = ""
    russian_speaker_template = ""

    if short_connection_note:
        async def _generate(audience: str) -> tuple[str, str]:
            return audience, await generate_connection_note_template(job, audience, log_func)

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
    else:
        needs_recruiter = has_recruiter or is_enrichment_failure
        needs_russian = has_russian or is_enrichment_failure
        slots = None
        if needs_recruiter or needs_russian:
            slots = await fetch_complete_outreach_slots(job, log_func)

        if needs_recruiter:
            recruiter_template = (
                complete_outreach_fallback_template(job, "recruiter")
                if slots is None
                else assemble_complete_outreach_template(job, "recruiter", slots)
            )
        if needs_russian:
            russian_speaker_template = (
                complete_outreach_fallback_template(job, "russian_speaker")
                if slots is None
                else assemble_complete_outreach_template(job, "russian_speaker", slots)
            )

    return {"recruiter": recruiter_template, "russian_speaker": russian_speaker_template}
