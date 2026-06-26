import os
import json
import asyncio
import inspect
import re
from dotenv import load_dotenv

from .gemini_client import generate_text as gemini_generate_text

load_dotenv()

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
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def _build_prompt(resume: str, job_title: str, company: str, description: str) -> str:
    return f"""You are a resume matcher. Compare the candidate's resume to the job listing and evaluate compatibility.

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
  "summary": "<concise 2-3 sentence summary of the job listing, including key tech stack/responsibilities>",
  "isRecruiter": <true|false>,
  "salary": "<extracted salary string or empty string>"
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
- Identify if the listing company is a recruiting/staffing/headhunting agency rather than the direct hiring employer (e.g. Randstad, Fuze HR, Teksystems, Robert Half, or if the description uses third-person phrasing like "Our client...", "A leading firm is seeking...", etc.).
  * If the job is posted by a recruiting/staffing firm: set "isRecruiter" to true. In this case, you MUST set "shouldProceed" to false, add "Posted by a recruiting agency/staffing firm" to the "gaps" list, and apply a penalty to "matchScore" by subtracting 15 points (or capping it at a maximum of 70).
  * If it is a direct employer, set "isRecruiter" to false.
- Extract any salary/compensation details from the description (e.g., "$120,000 - $140,000" or "$75/hour"). Return it formatted cleanly under the "salary" key. If not mentioned in the description, return an empty string.
"""


_BATCH_DESC_LIMIT = 2000  # chars; keeps batch prompts under ~8k tokens to avoid timeouts


def _build_batch_prompt(resume: str, jobs: list[dict]) -> str:
    jobs_text = ""
    for i, job in enumerate(jobs):
        desc = (job.get("description") or "")[:_BATCH_DESC_LIMIT]
        jobs_text += f"--- JOB {i} ---\n"
        jobs_text += f"Title: {job.get('title', '')}\n"
        jobs_text += f"Company: {job.get('company', '')}\n"
        jobs_text += f"Description: {desc}\n\n"

    return f"""You are a resume matcher. Compare the candidate's resume to the following {len(jobs)} job listings and evaluate compatibility for each.

RESUME:
{resume}

LISTINGS:
{jobs_text}

Respond with a JSON array of objects (no markdown, no extra text). Each object must correspond to a job in the order provided and follow this exact format:
{{
  "index": <integer index of the job>,
  "matchScore": <integer 0-100>,
  "matchType": "<match|no-match>",
  "strengths": ["<strength 1>", "<strength 2>"],
  "gaps": ["<gap 1>", "<gap 2>"],
  "shouldProceed": <true|false>,
  "remoteType": "<remote|hybrid|in_office>",
  "seniority": "<junior|mid|senior>",
  "summary": "<concise 2-3 sentence summary of the job listing, including key tech stack/responsibilities>",
  "isRecruiter": <true|false>,
  "salary": "<extracted salary string or empty string>"
}}

Rules for each evaluation:
- matchScore >= 75 means matchType is "match" and shouldProceed is true.
- List 2-4 concrete strengths and 1-3 specific gaps.
- Analyze the Job Title, Location, and Description to determine the job's remote status ("remoteType"). It must be exactly one of: "remote", "hybrid", "in_office".
- Analyze the Job Title and Description to determine seniority level ("seniority"). It must be exactly one of: "junior", "mid", "senior".
- Identify if the listing company is a recruiting/staffing/headhunting agency.
  * If the job is posted by a recruiting/staffing firm: set "isRecruiter" to true, "shouldProceed" to false, add "Posted by a recruiting agency/staffing firm" to "gaps", and apply a penalty to "matchScore" (-15 points, max 70).
- Extract salary details or return empty string.
"""


async def evaluate_jobs_batch(jobs: list[dict], resume_content: str, log_func=None) -> list[dict]:
    """
    Evaluate a batch of jobs against a resume using the Gemini API.
    Returns a list of evaluation results in the same order as the input jobs.
    If the batch call fails, it falls back to sequential evaluation for each job.
    """
    async def log(msg, level="info"):
        if log_func:
            if inspect.iscoroutinefunction(log_func):
                await log_func(msg, level)
            else:
                log_func(msg, level)

    if not jobs:
        return []

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        await log("GEMINI_API_KEY not set, skipping batch evaluation.", "warning")
        return [{} for _ in jobs]

    prompt = _build_batch_prompt(resume_content, jobs)
    
    max_retries = 4
    for attempt in range(max_retries):
        try:
            text = await gemini_generate_text(prompt, timeout=90.0)
            if text.startswith("```"):
                lines = text.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()

            results = json.loads(text)
            if not isinstance(results, list) or len(results) != len(jobs):
                raise ValueError(f"Batch result size mismatch: expected {len(jobs)}, got {len(results) if isinstance(results, list) else 'non-list'}")

            # Sort by index to ensure order if LLM shuffled them
            results.sort(key=lambda x: x.get("index", 0))

            # Post-process each result
            final_results = []
            for i, result in enumerate(results):
                job = jobs[i]
                company_name = job.get("company", "")
                local_is_recruiter = check_recruiter_by_name(company_name)

                if local_is_recruiter or result.get("isRecruiter"):
                    result["isRecruiter"] = True
                    result["shouldProceed"] = False
                    if result.get("matchScore", 0) >= 75:
                        result["matchScore"] = min(70, result["matchScore"] - 15)
                    elif result.get("matchScore", 0) > 0:
                        result["matchScore"] = max(0, result["matchScore"] - 15)
                    result["matchType"] = "no-match"
                    gaps = result.setdefault("gaps", [])
                    if "Posted by a recruiting agency/staffing firm" not in gaps:
                        gaps.append("Posted by a recruiting agency/staffing firm")
                final_results.append(result)

            return final_results

        except Exception as e:
            err_str = str(e)
            is_rate_limit = "429" in err_str or "quota" in err_str.lower() or "rate" in err_str.lower()
            is_last = attempt == max_retries - 1
            wait = 2.0 ** attempt  # 1, 2, 4, 8 seconds
            if is_last:
                await log(f"Batch evaluation attempt {attempt + 1} failed: {e}. Falling back to sequential.", "warning")
                sequential_results = []
                for job in jobs:
                    res = await evaluate_job(job, resume_content, log_func)
                    sequential_results.append(res)
                return sequential_results
            await log(
                f"Batch evaluation attempt {attempt + 1} failed{' (rate limit)' if is_rate_limit else ''}: {e}. "
                f"Retrying in {wait:.0f}s...",
                "warning",
            )
            await asyncio.sleep(wait)

    return [{} for _ in jobs]


async def evaluate_job(job: dict, resume_content: str, log_func=None) -> dict:
    """
    Evaluate a job against a resume using the Gemini API.
    Returns dict with matchScore, matchType, strengths, gaps, shouldProceed, remoteType, seniority, summary, isRecruiter, salary.
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

