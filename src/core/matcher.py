import asyncio
import inspect
import json
import os
import re

from .gemini_client import generate_text as gemini_generate_text

RESUMES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "resumes")

RECRUITING_AGENCY_PATTERNS = [
    r'\bhr\s+solutions\b', r'\bstaffing\b', r'\brecruiting\b', r'\bplacement\b',
    r'\btalent\s+solutions\b', r'\bheadhunter\b', r'\bhuman\s+resources\b',
    r'\brecruiters\b', r'\bpartners\b', r'\bassociates\b', r'\bagency\b',
    r'\bjobspy\b', r'\bworkland\b', r'\br2\s+global\b', r'\bdelan\b',
    r'\bfuze\s+hr\b', r'\brandstad\b', r'\brobert\s+half\b', r'\bteksystems\b',
    r'\baerotek\b', r'\bkforce\b', r'\bignite\b', r'\bquantum\b', r'\bprocom\b'
]


def check_recruiter_by_name(company_name: str) -> bool:
    if not company_name:
        return False
    name_lower = company_name.lower()
    combined = re.compile('|'.join(RECRUITING_AGENCY_PATTERNS), re.IGNORECASE)
    return bool(combined.search(name_lower))


def load_resume(name: str) -> str:
    filepath = os.path.join(RESUMES_DIR, name)
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Resume not found: {name}")
    with open(filepath, encoding="utf-8") as f:
        return f.read()


def _build_prompt(
    resume: str,
    job_title: str,
    company: str,
    description: str,
    search_query: str = "",
) -> str:
    query = (search_query or "").strip()
    return f"""You are a resume matcher. Compare the candidate's resume to the job listing and evaluate compatibility.

Search query: {query}

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
  "shouldProceed": <true|false>,
  "remoteType": "<remote|hybrid|in_office>",
  "seniority": "<junior|mid|senior>",
  "employmentType": "<Full-time|Contract|Part-time|Temporary|Volunteer>",
  "summary": "<concise 2-3 sentence summary of the job listing, including key tech stack/responsibilities>",
  "isRecruiter": <true|false>,
  "salary": "<human-readable Posted Salary string or empty string>",
  "postedSalary": <null or object — structured Posted Salary facts; see rules>,
  "roleRelevant": <true|false|null>
}}

Rules:
- matchScore >= 75 means matchType is "match" and shouldProceed is true.
- List 2-4 concrete strengths and 1-3 specific gaps.
- Analyze the Job Title, Location, and Description to determine the job's remote status ("remoteType"). It must be exactly one of: "remote", "hybrid", "in_office".
  * "remote" means work from home/anywhere, no office presence required.
  * "hybrid" means part-time in office, part-time remote.
  * "in_office" means fully in office.
- Analyze the Job Title and Description to determine seniority level ("seniority"). It must be exactly one of: "junior", "mid", "senior".
  * "junior" means entry-level, intern, associate, or explicitly junior roles.
  * "mid" means standard individual contributor roles without explicit senior/junior markers.
  * "senior" means senior, lead, principal, staff, manager, director, or equivalent seniority signals.
- Analyze the Job Title and Description to determine Employment Type ("employmentType"). It must be exactly one of: "Full-time", "Contract", "Part-time", "Temporary", "Volunteer".
  * "Full-time" means permanent or ongoing full-time employment.
  * "Contract" means contractor, freelance, or fixed-term contract roles.
  * "Part-time" means part-time hours (not full-time).
  * "Temporary" means temp / temporary placement.
  * "Volunteer" means unpaid or volunteer roles.
- Identify if the listing company is a recruiting/staffing/headhunting agency rather than the direct hiring employer (e.g. Randstad, Fuze HR, Teksystems, Robert Half, or if the description uses third-person phrasing like "Our client...", "A leading firm is seeking...", etc.).
  * If the job is posted by a recruiting/staffing firm: set "isRecruiter" to true. In this case, you MUST set "shouldProceed" to false, add "Posted by a recruiting agency/staffing firm" to the "gaps" list, and apply a penalty to "matchScore" by subtracting 15 points (or capping it at a maximum of 70).
  * If it is a direct employer, set "isRecruiter" to false.
- Extract Posted Salary / compensation from the description (and any salary field in the listing text).
  * Always set "salary" to a clean human-readable string of the listed pay (e.g. "$120,000 - $140,000", "$70-80/hr"). If pay is not mentioned, set "salary" to "" and "postedSalary" to null.
  * When pay is present, also set "postedSalary" to structured facts (code annualizes these; do not convert periods yourself):
    - Single-location / single band:
      {{"period": "<hourly|daily|monthly|yearly>", "amountMin": <number>, "amountMax": <number or omit if point>, "currency": "<ISO code e.g. USD|CAD>", "hoursPerWeek": <number or omit>}}
    - Multi-location pay: use "bands" with one object per location:
      {{"bands": [{{"location": "<place as stated>", "period": "...", "amountMin": <n>, "amountMax": <n>, "currency": "...", "hoursPerWeek": <n or omit>}}, ...]}}
  * "period" must reflect the listing unit (hourly / daily / monthly / yearly), not an annualized guess.
  * Include "hoursPerWeek" only when the listing states hours per week for hourly pay.
  * "amountMin"/"amountMax" are numeric amounts in that period's unit (not annualized). For a single figure, set amountMin only (or equal min/max).
  * "currency" is the listing currency code when known (default USD if "$" with no other cue).
- Role Relevance ("roleRelevant") classifies role family against the search query only — not resume fit.
  * true if the listing is the queried role or an adjacent title in the same family.
    For query QA that includes QA Engineer, SDET, Software Engineer in Test, and test-automation roles.
  * false only when the listing is clearly a different role (example: a product/feature software engineer or developer vs QA).
  * null if the title and description are too thin or mixed to tell.
  * Do not use resume fit. Do not score skills for this field.
  * Read the listing in the language it is written in, including French or bilingual titles. Translate as needed before setting roleRelevant. Do not rely on a keyword list.
"""


async def evaluate_jobs_batch(
    jobs: list[dict],
    resume_content: str,
    log_func=None,
    search_query: str = "",
) -> list[dict]:
    """Evaluate jobs sequentially (legacy helper; search/backfill use Batch API)."""
    if not jobs:
        return []
    results = []
    for job in jobs:
        results.append(
            await evaluate_job(job, resume_content, log_func, search_query=search_query)
        )
    return results


async def evaluate_job(
    job: dict,
    resume_content: str,
    log_func=None,
    search_query: str = "",
) -> dict:
    """
    Evaluate a job against a resume using the Gemini API.
    Returns dict with matchScore, matchType, strengths, gaps, shouldProceed, remoteType, seniority, employmentType, summary, isRecruiter, salary, postedSalary, roleRelevant.
    search_query is the Role Relevance target (batch snapshot or live settings query).
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
    company_name = job.get("company", "")
    local_is_recruiter = check_recruiter_by_name(company_name)

    if not api_key:
        await log("GEMINI_API_KEY not set, skipping evaluation.", "warning")
        return {}

    prompt = _build_prompt(
        resume_content,
        job.get("title", ""),
        company_name,
        job.get("description", ""),
        search_query=search_query,
    )

    max_retries = 4
    for attempt in range(max_retries):
        try:
            text = await gemini_generate_text(prompt)
            if text.startswith("```"):
                lines = text.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()
            
            result = json.loads(text)
            
            # Post-process with local recruiter check to be 100% reliable
            if local_is_recruiter or result.get("isRecruiter"):
                result["isRecruiter"] = True
                result["shouldProceed"] = False
                # Apply penalty if score is too high
                if result.get("matchScore", 0) >= 75:
                    result["matchScore"] = min(70, result["matchScore"] - 15)
                elif result.get("matchScore", 0) > 0:
                    result["matchScore"] = max(0, result["matchScore"] - 15)
                result["matchType"] = "no-match"
                
                gaps = result.setdefault("gaps", [])
                if "Posted by a recruiting agency/staffing firm" not in gaps:
                    gaps.append("Posted by a recruiting agency/staffing firm")
                    
            return result
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

