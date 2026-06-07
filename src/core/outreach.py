import os
import json
import httpx
import asyncio
import inspect
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

APIFY_API_BASE = "https://api.apify.com/v2"
ACTOR_ID = "harvestapi~linkedin-company-employees"
RUSSIAN_KEYWORD = "Russian"
HR_JOB_TITLES = ["Recruiter", "Hiring Manager", "HR", "Talent Acquisition", "Human Resources"]
RUSSIAN_STAGE1_MIN = 5


async def _run_apify_actor(
    company: str,
    keyword: str = None,
    job_titles: list = None,
    log_func=None,
) -> list:
    """Trigger an Apify LinkedIn Company Employees run and return raw items."""

    async def log(msg, level="info"):
        if log_func:
            if inspect.iscoroutinefunction(log_func):
                await log_func(msg, level)
            else:
                log_func(msg, level)

    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        await log("APIFY_API_TOKEN not set, skipping Apify sourcing.", "warning")
        return []

    actor_input = {"companyName": company}
    if keyword:
        actor_input["keywords"] = keyword
    if job_titles:
        actor_input["jobTitles"] = job_titles

    run_url = f"{APIFY_API_BASE}/acts/{ACTOR_ID}/runs"
    params = {"token": api_token}
    headers = {"Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=60.0) as client:
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
        while True:
            await asyncio.sleep(5.0)
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
    return {
        "name": item.get("fullName") or item.get("name") or "",
        "title": item.get("headline") or item.get("title") or "",
        "url": item.get("linkedInUrl") or item.get("profileUrl") or item.get("url") or "",
        "contacted": False,
        "russian_speaker": False,
    }


async def _classify_russian_speakers(contacts: list, log_func=None) -> list:
    """Use Gemini to classify which contacts are likely Russian speakers."""

    async def log(msg, level="info"):
        if log_func:
            if inspect.iscoroutinefunction(log_func):
                await log_func(msg, level)
            else:
                log_func(msg, level)

    if not contacts:
        return contacts

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        await log("GEMINI_API_KEY not set, skipping Russian speaker classification.", "warning")
        return contacts

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    contacts_summary = json.dumps([
        {"name": c["name"], "title": c["title"], "url": c["url"]}
        for c in contacts
    ])

    prompt = f"""You are classifying LinkedIn contacts to determine if they are likely Russian speakers.
Evaluate each contact's name, job title, and profile URL. Russian names, Slavic surnames, or \
locations in Russia/CIS countries are strong indicators.

Contacts:
{contacts_summary}

Respond with ONLY a JSON array of booleans, one per contact, in the same order.
Example: [true, false, true]
true = likely Russian speaker, false = not."""

    try:
        response = await model.generate_content_async(prompt)
        results = json.loads(response.text.strip())
        if isinstance(results, list) and len(results) == len(contacts):
            for i, is_russian in enumerate(results):
                contacts[i]["russian_speaker"] = bool(is_russian)
    except Exception as e:
        await log(f"Russian speaker classification error: {e}", "warning")

    return contacts


async def source_contacts(job: dict, log_func=None) -> list:
    """
    Return contacts for a job.

    Priority:
    1. Direct poster mapping — if job["contacts"] already has entries (populated
       from the Bright Data job_poster field), return them as-is.
    2. Apify two-stage fallback:
       Stage 1 — search company employees by the keyword "Russian".
                  If >= 5 results, mark all russian_speaker=True and return.
       Stage 2 — search by HR job titles, then classify via Gemini.
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

    await log(f"No direct poster. Starting Apify sourcing for '{company}'...", "info")

    stage1_items = await _run_apify_actor(company, keyword=RUSSIAN_KEYWORD, log_func=log_func)
    contacts = [_normalize_apify_employee(item) for item in stage1_items]

    if len(contacts) >= RUSSIAN_STAGE1_MIN:
        await log(f"Stage 1 yielded {len(contacts)} Russian-keyword contacts.", "info")
        for c in contacts:
            c["russian_speaker"] = True
        return contacts

    await log(
        f"Stage 1 returned {len(contacts)} contacts (< {RUSSIAN_STAGE1_MIN}). "
        "Triggering Stage 2 fallback...",
        "warning",
    )

    stage2_items = await _run_apify_actor(company, job_titles=HR_JOB_TITLES, log_func=log_func)
    contacts = [_normalize_apify_employee(item) for item in stage2_items]
    contacts = await _classify_russian_speakers(contacts, log_func=log_func)

    await log(f"Stage 2 yielded {len(contacts)} contacts after Russian speaker classification.", "info")
    return contacts
