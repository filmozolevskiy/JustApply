"""LLM Outreach Audience classification for Contact Sample profiles."""

import os
import json
from dotenv import load_dotenv


def normalize_apify_employee(item: dict) -> dict:
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


# Backward-compatible alias for tests and outreach facade
_normalize_apify_employee = normalize_apify_employee


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
        normalized = normalize_apify_employee(item)
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
        from ..gemini_client import generate_text as gemini_generate_text
        text = await gemini_generate_text(prompt)
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        classified = json.loads(text)
    except Exception:
        return []

    RUSSIAN_SPEAKER_CAP = 5
    RECRUITER_CAP = 3

    russian_count = 0
    recruiter_count = 0
    result = []

    for entry in classified:
        idx = entry.get("index")
        if idx is None or not isinstance(idx, int) or idx >= len(items):
            continue

        is_recruiter_classified = bool(entry.get("is_recruiter"))
        is_russian_classified = bool(entry.get("russian_speaker"))

        # Dual-classified contacts count toward Recruiter cap only (CONTEXT.md)
        add_recruiter = (
            is_recruiter_classified and settings.target_recruiters and recruiter_count < RECRUITER_CAP
        )
        # Russian pool: only contacts with russian_speaker and NOT is_recruiter
        add_russian = (
            is_russian_classified
            and not is_recruiter_classified
            and settings.target_russian_speakers
            and russian_count < RUSSIAN_SPEAKER_CAP
        )

        if not add_russian and not add_recruiter:
            continue

        contact = normalize_apify_employee(items[idx])
        # Dual-classified contacts show both badges (is_russian_classified preserved)
        contact["russian_speaker"] = is_russian_classified and (add_russian or add_recruiter)
        contact["is_recruiter"] = add_recruiter

        if add_russian:
            russian_count += 1
        if add_recruiter:
            recruiter_count += 1

        result.append(contact)

    return result
