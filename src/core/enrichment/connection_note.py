"""Outreach Generator: Connection Note templates for Enrichment."""

import os
from dotenv import load_dotenv

RECRUITER_CTA = "I would be grateful to connect and share my CV."
RUSSIAN_SPEAKER_CTA = "I'd be grateful if you could refer me for the role."
FIT_LINE = "My experience align well with the requirements."


def minimal_fallback_template(audience: str) -> str:
    cta = RECRUITER_CTA if audience == "recruiter" else RUSSIAN_SPEAKER_CTA
    return (
        f"Hello ______,\n\n"
        f"______ is looking for a ______. {FIT_LINE}\n\n"
        f"{cta}"
    )


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
