import os
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
RUSSIAN_LANGUAGES = {"russian", "ukrainian", "belarusian"}
HR_TITLE_KEYWORDS = ["recruit", "hr ", "human resource", "talent acquisition", "people ops", "hiring manager", "talent ti", "acquisition de talents"]



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

    languages = item.get("languages") or []
    lang_names = {(lang.get("name") or "").lower() for lang in languages if isinstance(lang, dict)}
    is_russian_speaker = bool(lang_names & RUSSIAN_LANGUAGES)

    return {
        "name": full,
        "title": item.get("headline") or item.get("title") or "",
        "url": item.get("linkedinUrl") or item.get("linkedInUrl") or item.get("profileUrl") or item.get("url") or "",
        "contacted": False,
        "russian_speaker": is_russian_speaker,
    }


async def source_contacts(job: dict, log_func=None) -> list:
    """
    Return outreach contacts for a job.

    1. If the job already has contacts, return them as-is.
    2. Fetch up to CONTACT_SAMPLE_SIZE employees via Apify.
    3. Mark Russian speakers by language field (Russian/Ukrainian/Belarusian).
    4. Return Russian speakers if any found, otherwise return up to 10 HR/recruiter contacts.
    """

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

    contacts = [_normalize_apify_employee(item) for item in items]

    russian = [c for c in contacts if c["russian_speaker"]]
    if russian:
        await log(f"Found {len(russian)} Russian speaker(s).", "info")
        return russian

    await log("No Russian speakers found. Falling back to HR/recruiter contacts.", "warning")
    hr_contacts = [
        c for c in contacts
        if any(kw in (c.get("title") or "").lower() for kw in HR_TITLE_KEYWORDS)
    ]
    await log(f"Found {len(hr_contacts)} HR/recruiter contact(s).", "info")
    return hr_contacts[:10]
