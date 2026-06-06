import asyncio
import json
import os
import sys
import argparse
import re
import datetime
import random
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

async def evaluate_job_compatibility(resume_text: str, job: dict, api_key: str = None) -> dict:
    """Evaluate job description compatibility against resume using Gemini API."""
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable is not set.")
    
    genai.configure(api_key=key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = f"""
You are an expert recruiter and career advisor.
Analyze the following candidate's resume and a job listing to evaluate compatibility.

Candidate Resume (tailored for target role):
{resume_text}

Job Listing:
Title: {job.get('Job title')}
Company: {job.get('Company + Company size')}
Location: {job.get('Location + Remote type (in office, hybrid, remote)')}
Seniority: {job.get('Seniority type (junior, mid, senior)')}
Salary: {job.get('Salary type')}
Description: {job.get('Short description')}

Analyze the alignment and gaps between the candidate's profile and the job requirements/seniority.
Return a JSON object with the following fields:
1. "match": A concise summary (1-2 sentences, max 200 chars) of key matching skills, experience, or alignments.
2. "no_match": A concise summary (1-2 sentences, max 200 chars) of any gaps, missing requirements, or misalignments.
3. "should_proceed": A boolean (true or false) indicating whether the candidate matches the core requirements and seniority of the job (i.e. whether they should proceed with applying).

Return ONLY the JSON object. Do not include any other text, markdown formatting (other than optionally wrapping in ```json and ```), or explanations.
"""
    
    response = None
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = await model.generate_content_async(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            break
        except Exception as e:
            if "429" in str(e) or "Quota exceeded" in str(e) or "ResourceExhausted" in str(e):
                wait_time = 30 * (attempt + 1)
                print(f"Rate limit hit. Waiting {wait_time}s before retry...", file=sys.stderr)
                await asyncio.sleep(wait_time)
                continue
            raise e
    if response is None:
        raise RuntimeError("Failed to evaluate job compatibility due to Gemini API rate limits.")
    
    try:
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text)
            text = re.sub(r"```$", "", text).strip()
            
        data = json.loads(text)
        
        job_copy = job.copy()
        job_copy["match"] = data.get("match") or ""
        job_copy["no-match"] = data.get("no_match") or ""
        should_proceed = data.get("should_proceed")
        job_copy["Should proceed?"] = "Yes" if should_proceed else "No"
        return job_copy
    except Exception as e:
        job_copy = job.copy()
        job_copy["match"] = "Error parsing LLM response"
        job_copy["no-match"] = str(e)
        job_copy["Should proceed?"] = "No"
        return job_copy


# Preset keywords mapping for typical target positions
POSITION_KEYWORDS = {
    "qa": ["qa", "quality assurance", "test", "sdet", "automation", "testing"],
    "project/delivery manager": ["project manager", "delivery manager", "pm", "scrum", "project management", "delivery management"],
    "automation specialist": ["automation", "sdet", "qa", "test", "scripting", "testing"],
    "data analyst/bi analyst": ["data analyst", "bi analyst", "business intelligence", "sql", "tableau", "power bi"]
}

# US states and Canadian provinces in Eastern Time zone (EST/EDT)
EASTERN_STATES = {
    # US
    "CT", "DE", "FL", "GA", "IN", "KY", "ME", "MD", "MA", "MI", "NH", "NJ", "NY", "NC", "OH", "PA", "RI", "SC", "VT", "VA", "DC", "WV",
    # Canada
    "ON", "QC"
}

def get_keywords_for_position(position: str) -> list:
    """Determine the keywords matching the given target position."""
    pos_lower = position.lower()
    for key, keywords in POSITION_KEYWORDS.items():
        if key in pos_lower or pos_lower in key:
            return keywords
    # Fallback: extract alphabetic words from target position
    words = re.findall(r'\b[a-zA-Z]+\b', pos_lower)
    return [w for w in words if len(w) > 1]

def matches_position_keywords(title: str, description: str, keywords: list) -> bool:
    """Verify if the job title matches at least one keyword using word boundaries."""
    title_lower = title.lower()
    for kw in keywords:
        pattern = r'\b' + re.escape(kw) + r'\b'
        if re.search(pattern, title_lower):
            return True
    return False

def is_eastern_timezone(location: str, description: str, is_remote: bool) -> bool:
    """Check if the job location or details align with Eastern Time Zone (EST/EDT)."""
    if not is_remote and location:
        # Extract US/Canada state or province abbreviations, e.g. New York, NY
        state_match = re.search(r'\b([A-Z]{2})\b', location)
        if state_match:
            state = state_match.group(1)
            if state in EASTERN_STATES:
                return True
        
        # Check for full names of Eastern states or key cities
        loc_lower = location.lower()
        eastern_names = ["new york", "georgia", "ontario", "quebec", "florida", "massachusetts", "pennsylvania", "toronto", "atlanta", "boston", "miami"]
        for name in eastern_names:
            if name in loc_lower:
                return True
        return False
        
    # Remote jobs are compatible by default unless they explicitly restrict to non-Eastern zones
    desc_lower = description.lower()
    has_eastern = any(term in desc_lower for term in ["est", "edt", "eastern"])
    
    has_pacific = any(term in desc_lower for term in ["pst", "pdt", "pacific"])
    has_mountain = any(term in desc_lower for term in ["mst", "mdt", "mountain"])
    has_central = any(term in desc_lower for term in ["cst", "cdt", "central"])
    
    if (has_pacific or has_mountain or has_central) and not has_eastern:
        # Check for timezone restrictions in description
        restriction_patterns = [
            r'must be in (?:pst|mst|cst|pacific|mountain|central)',
            r'(?:pst|mst|cst|pacific|mountain|central) (?:only|required|timezone)',
            r'located in (?:pst|mst|cst|pacific|mountain|central)',
            r'work in (?:pst|mst|cst|pacific|mountain|central)'
        ]
        for pattern in restriction_patterns:
            if re.search(pattern, desc_lower):
                return False
                
    return True

def filter_jobs(jobs: list, position: str) -> list:
    """Filter raw jobs based on position keywords and timezone compatibility."""
    keywords = get_keywords_for_position(position)
    filtered = []
    for job in jobs:
        title = job.get("title") or job.get("Job title") or ""
        description = job.get("description") or job.get("Short description") or ""
        location = job.get("location") or job.get("Location") or ""
        is_remote = job.get("isRemote") or job.get("is_remote") or "remote" in location.lower()
        
        if not matches_position_keywords(title, description, keywords):
            continue
            
        if not is_eastern_timezone(location, description, is_remote):
            continue
            
        filtered.append(job)
    return filtered

def normalize_job(job: dict) -> dict:
    """Map raw JobSpy fields to the Job Tracker Sheet 'Jobs' schema."""
    title = job.get("title") or job.get("Job title") or ""
    
    company = job.get("company") or ""
    size = job.get("companyNumEmployees") or job.get("company_num_employees") or ""
    company_field = f"{company} ({size})" if size else company
    
    link = job.get("jobUrl") or job.get("job_url") or ""
    date = job.get("datePosted") or job.get("date_posted") or ""
    
    loc = job.get("location") or ""
    is_rem = job.get("isRemote") or job.get("is_remote") or "remote" in loc.lower()
    
    if is_rem:
        loc_field = f"Remote ({loc})" if loc and loc.lower() != "remote" else "Remote"
    else:
        if "hybrid" in loc.lower():
            loc_field = f"Hybrid ({loc})"
        else:
            loc_field = f"In Office ({loc})" if loc else "In Office"
            
    title_lower = title.lower()
    if any(term in title_lower for term in ["sr", "senior", "lead", "principal", "staff", "manager", "director"]):
        seniority = "senior"
    elif any(term in title_lower for term in ["jr", "junior", "entry", "intern", "associate"]):
        seniority = "junior"
    else:
        seniority = "mid"
        
    min_amt = job.get("minAmount") or job.get("min_amount")
    max_amt = job.get("maxAmount") or job.get("max_amount")
    interval = job.get("interval") or "yearly"
    
    salary_field = ""
    if min_amt is not None and max_amt is not None:
        def fmt(val):
            if val >= 1000:
                if val % 1000 == 0:
                    return f"${int(val / 1000)}k"
                return f"${val / 1000:.1f}k"
            return f"${val}"
        salary_field = f"{fmt(min_amt)} - {fmt(max_amt)} / {interval}"
    elif min_amt is not None:
        def fmt(val):
            if val >= 1000:
                if val % 1000 == 0:
                    return f"${int(val / 1000)}k"
                return f"${val / 1000:.1f}k"
            return f"${val}"
        salary_field = f"{fmt(min_amt)} / {interval}"
    elif max_amt is not None:
        def fmt(val):
            if val >= 1000:
                if val % 1000 == 0:
                    return f"${int(val / 1000)}k"
                return f"${val / 1000:.1f}k"
            return f"${val}"
        salary_field = f"{fmt(max_amt)} / {interval}"
        
    desc = job.get("description") or job.get("Short description") or ""
    if len(desc) > 500:
        desc_field = desc[:500] + "..."
    else:
        desc_field = desc
        
    return {
        "Job title": title,
        "Company + Company size": company_field,
        "Posting link": link,
        "Posting date": date,
        "Location + Remote type (in office, hybrid, remote)": loc_field,
        "Seniority type (junior, mid, senior)": seniority,
        "Salary type": salary_field,
        "Short description": desc_field,
        "match": "",
        "no-match": "",
        "Should proceed?": ""
    }

def get_mcp_params(server_name: str, default_cmd: str, default_args: list) -> StdioServerParameters:
    """Helper to load MCP server configuration from settings.json or fallback to defaults."""
    command = default_cmd
    args = default_args
    script_dir = os.path.dirname(os.path.abspath(__file__))
    settings_path = os.path.join(script_dir, ".claude", "settings.json")
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r") as f:
                settings = json.load(f)
                config = settings.get("mcpServers", {}).get(server_name, {})
                if config.get("command"):
                    command = config.get("command")
                    args = config.get("args", [])
        except Exception:
            pass
    return StdioServerParameters(
        command=command,
        args=args,
        env=os.environ.copy()
    )

async def run_search_pipeline(position: str, sites: list = None) -> list:
    """Launch JobSpy MCP server and query jobs concurrently for specified sites."""
    if sites is None:
        sites = ["linkedin", "zip_recruiter", "indeed"]
        
    server_params = get_mcp_params("jobspy", "node", ["jobspy-mcp-server/src/index.js"])
    
    results = []
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            tasks = []
            for site in sites:
                params = {
                    "siteNames": site,
                    "searchTerm": position,
                    "location": "remote",
                    "resultsWanted": 20,
                    "hoursOld": 72
                }
                tasks.append(session.call_tool("search_jobs", params))
                
            tool_results = await asyncio.gather(*tasks)
            
            for result in tool_results:
                if hasattr(result, "content") and result.content:
                    text = result.content[0].text
                    try:
                        data = json.loads(text)
                        if "jobs" in data:
                            results.extend(data["jobs"])
                    except json.JSONDecodeError:
                        pass
    return results

async def run_orchestrator_pipeline(position: str, skip_unmatched: bool = False, sites: list = None) -> list:
    """Run search, retrieve resume, evaluate jobs, and write to Jobs tab in Sheets."""
    print(f"Starting job hunter pipeline for position: {position}")
    
    # 1. Search jobs via JobSpy
    jobs = await run_search_pipeline(position, sites=sites)
    print(f"Found {len(jobs)} total jobs via JobSpy.")
    
    # 2. Filter jobs by keywords and timezone
    filtered = filter_jobs(jobs, position)
    print(f"Filtered to {len(filtered)} compatible jobs.")
    if not filtered:
        print("No compatible jobs found.")
        return []
        
    # 3. Connect to google-sheets MCP server to get the resume
    sheets_params = StdioServerParameters(
        command=sys.executable,
        args=["scripts/google_sheets_mcp.py"],
        env=os.environ.copy()
    )
    
    evaluated_jobs = []
    
    async with stdio_client(sheets_params) as (sheets_read, sheets_write):
        async with ClientSession(sheets_read, sheets_write) as sheets_session:
            await sheets_session.initialize()
            print("Connected to Google Sheets MCP server.")
            
            # Resolve resume filename and fetch resume
            resume_filename = position.lower().replace("/", "_").replace(" ", "_")
            if not resume_filename.endswith(".md"):
                resume_filename += ".md"
                
            try:
                print(f"Retrieving resume: {resume_filename}")
                resume_response = await sheets_session.call_tool(
                    "get_resume", 
                    {"filename": resume_filename}
                )
                resume_text = resume_response.content[0].text
                print("Resume retrieved successfully.")
            except Exception as e:
                print(f"Warning: Error retrieving resume '{resume_filename}': {e}", file=sys.stderr)
                print("Falling back to retrieve 'qa.md' or default resume...")
                try:
                    resume_response = await sheets_session.call_tool(
                        "get_resume", 
                        {"filename": "qa.md"}
                    )
                    resume_text = resume_response.content[0].text
                    print("Fallback resume 'qa.md' retrieved successfully.")
                except Exception as fallback_e:
                    print(f"Failed to retrieve fallback resume: {fallback_e}", file=sys.stderr)
                    raise ValueError(f"Could not retrieve resume for evaluation: {e}")
            
            # 4. Evaluate each job and write to sheet
            for i, job in enumerate(filtered):
                normalized = normalize_job(job)
                print(f"[{i+1}/{len(filtered)}] Evaluating: {normalized['Job title']} at {normalized['Company + Company size']}")
                
                try:
                    evaluated = await evaluate_job_compatibility(resume_text, normalized)
                except Exception as e:
                    print(f"Error evaluating job '{normalized['Job title']}': {e}", file=sys.stderr)
                    evaluated = normalized.copy()
                    evaluated["match"] = "Evaluation failed"
                    evaluated["no-match"] = str(e)
                    evaluated["Should proceed?"] = "No"
                
                should_proceed = evaluated.get("Should proceed?") == "Yes"
                if not should_proceed and skip_unmatched:
                    print(f"Skipping unmatched job: {normalized['Job title']} at {normalized['Company + Company size']}")
                    continue
                
                try:
                    add_result = await sheets_session.call_tool(
                        "add_job",
                        {
                            "job_title": evaluated["Job title"],
                            "company": evaluated["Company + Company size"],
                            "posting_link": evaluated["Posting link"],
                            "posting_date": evaluated["Posting date"],
                            "location": evaluated["Location + Remote type (in office, hybrid, remote)"],
                            "seniority": evaluated["Seniority type (junior, mid, senior)"],
                            "salary": evaluated["Salary type"],
                            "short_description": evaluated["Short description"],
                            "match_details": evaluated["match"],
                            "no_match_details": evaluated["no-match"],
                            "should_proceed": evaluated["Should proceed?"]
                        }
                    )
                    print(f"Added to sheet: {add_result.content[0].text if hasattr(add_result, 'content') else add_result}")
                    evaluated_jobs.append(evaluated)
                except Exception as e:
                    print(f"Error adding job to sheet: {e}", file=sys.stderr)
                    
    return evaluated_jobs

def extract_company_slug(company_name: str, search_results: dict) -> str:
    """Extract company slug from search_companies output, or fallback to slugified name."""
    refs = search_results.get("references", {}).get("search_results", [])
    for ref in refs:
        if ref.get("kind") == "company" and "url" in ref:
            url = ref["url"]
            match = re.search(r'/company/([^/]+)', url)
            if match:
                return match.group(1)
    
    # Fallback slugification
    cleaned = company_name.lower().strip()
    cleaned = re.sub(r'\s*\([^)]*\)', '', cleaned)
    cleaned = re.sub(r'[^a-z0-9\s-]', '', cleaned)
    slug = re.sub(r'[\s-]+', '-', cleaned)
    return slug

async def extract_contacts_via_llm(employees_json_text: str, api_key: str = None) -> list:
    """Parse LinkedIn employees JSON response using Gemini to extract names, titles, and profile links."""
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable is not set.")
    
    genai.configure(api_key=key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = f"""
You are an expert data extraction assistant.
Given the following JSON response from a LinkedIn employee search, extract all people who are Recruiters, Hiring Managers, or Talent Acquisition professionals.

LinkedIn Employee Search Response:
{employees_json_text}

For each matching person, extract:
1. "name": The full name of the person.
2. "title": Their job title.
3. "url": Their LinkedIn profile URL (usually starting with '/in/', prepend 'https://www.linkedin.com' to make it a full URL, e.g. 'https://www.linkedin.com/in/kmarscel').

Return a JSON array of objects with the fields: "name", "title", "url".
Return ONLY the JSON array. Do not include any other text, markdown formatting (other than optionally wrapping in ```json and ```), or explanations.
"""
    
    response = None
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = await model.generate_content_async(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            break
        except Exception as e:
            if "429" in str(e) or "Quota exceeded" in str(e) or "ResourceExhausted" in str(e):
                wait_time = 30 * (attempt + 1)
                print(f"Rate limit hit. Waiting {wait_time}s before retry...", file=sys.stderr)
                await asyncio.sleep(wait_time)
                continue
            raise e
    if response is None:
        raise RuntimeError("Failed to extract contacts from LinkedIn due to Gemini API rate limits.")
    
    try:
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text)
            text = re.sub(r"```$", "", text).strip()
            
        data = json.loads(text)
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        print(f"Error parsing LLM response for contacts: {e}", file=sys.stderr)
        return []

async def generate_outreach_messages(resume_text: str, job: dict, contacts: list, api_key: str = None) -> str:
    """Generate cover letter and referral message using Gemini."""
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable is not set.")
    
    genai.configure(api_key=key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    contacts_str = ""
    if contacts:
        contacts_str = "\n".join([f"- Name: {c['name']}, Title: {c['title']}, Profile: {c['url']}" for c in contacts])
    else:
        contacts_str = "No specific contacts found."
        
    prompt = f"""
You are an expert job application assistant.
Generate a customized cover letter and a referral request message for a candidate applying to this job.

Candidate Resume:
{resume_text}

Job Listing:
Title: {job.get('Job title')}
Company: {job.get('Company + Company size')}
Location: {job.get('Location + Remote type (in office, hybrid, remote)')}
Description: {job.get('Short description')}

Company Contacts Found:
{contacts_str}

Please generate:
1. A customized, professional Cover Letter tailored to the candidate's experience and the job description.
2. A short, polite Referral Request / Outreach Message to be sent to one of the recruiters or hiring managers. 
   - If contacts were found, address it to the first contact (e.g., "Hi {contacts[0]['name'] if contacts else '[Recruiter Name]'}, ...").
   - If no contacts were found, use "Hi [Hiring Manager / Recruiter Name]," as the placeholder.
   - Keep it short (1-2 paragraphs, under 300 words), focused on value and a quick chat/referral request.

Format the output clearly with separators so they can be copy-pasted:

[Cover Letter]
<generated cover letter here>

[Referral Message]
<generated referral message here>
"""
    
    response = None
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = await model.generate_content_async(prompt)
            break
        except Exception as e:
            if "429" in str(e) or "Quota exceeded" in str(e) or "ResourceExhausted" in str(e):
                wait_time = 30 * (attempt + 1)
                print(f"Rate limit hit. Waiting {wait_time}s before retry...", file=sys.stderr)
                await asyncio.sleep(wait_time)
                continue
            raise e
    if response is None:
        raise RuntimeError("Failed to generate outreach messages due to Gemini API rate limits.")
    return response.text.strip()

CACHE_FILE = "cache/linkedin_cache.json"

class LinkedInCache:
    def __init__(self, filepath=CACHE_FILE):
        self.filepath = filepath
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Failed to load LinkedIn cache: {e}", file=sys.stderr)
        return {"slugs": {}, "contacts": {}, "lookups_today": []}

    def save(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to save LinkedIn cache: {e}", file=sys.stderr)

    def get_slug(self, company_name):
        return self.data.get("slugs", {}).get(company_name)

    def set_slug(self, company_name, slug):
        if "slugs" not in self.data:
            self.data["slugs"] = {}
        self.data["slugs"][company_name] = slug
        self.save()

    def get_contacts(self, slug):
        return self.data.get("contacts", {}).get(slug)

    def set_contacts(self, slug, contacts):
        if "contacts" not in self.data:
            self.data["contacts"] = {}
        self.data["contacts"][slug] = contacts
        self.save()

    def get_lookups_count_last_24h(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        cutoff = now - datetime.timedelta(hours=24)
        
        # Parse and filter timestamps
        lookups = []
        for ts_str in self.data.get("lookups_today", []):
            try:
                ts = datetime.datetime.fromisoformat(ts_str)
                if ts >= cutoff:
                    lookups.append(ts_str)
            except ValueError:
                pass
        
        self.data["lookups_today"] = lookups
        self.save()
        return len(lookups)

    def record_lookup(self):
        if "lookups_today" not in self.data:
            self.data["lookups_today"] = []
        now = datetime.datetime.now(datetime.timezone.utc)
        self.data["lookups_today"].append(now.isoformat())
        self.save()

async def run_promotion_pipeline(position: str) -> list:
    """Retrieve jobs from Jobs tab, check 'Should proceed?', search LinkedIn contacts, generate outreach, and promote to Applications."""
    print(f"Starting promotion pipeline for position: {position}")
    
    # 1. Connect to Sheets MCP server
    sheets_params = get_mcp_params("google-sheets", sys.executable, ["scripts/google_sheets_mcp.py"])
    
    promoted_jobs = []
    
    # Initialize cache
    cache = LinkedInCache()
    
    async with stdio_client(sheets_params) as (sheets_read, sheets_write):
        async with ClientSession(sheets_read, sheets_write) as sheets_session:
            await sheets_session.initialize()
            print("Connected to Google Sheets MCP server.")
            
            # Resolve resume filename and fetch resume
            resume_filename = position.lower().replace("/", "_").replace(" ", "_")
            if not resume_filename.endswith(".md"):
                resume_filename += ".md"
                
            try:
                print(f"Retrieving resume: {resume_filename}")
                resume_response = await sheets_session.call_tool(
                    "get_resume", 
                    {"filename": resume_filename}
                )
                resume_text = resume_response.content[0].text
                print("Resume retrieved successfully.")
            except Exception as e:
                print(f"Warning: Error retrieving resume '{resume_filename}': {e}", file=sys.stderr)
                print("Falling back to retrieve 'qa.md' or default resume...")
                try:
                    resume_response = await sheets_session.call_tool(
                        "get_resume", 
                        {"filename": "qa.md"}
                    )
                    resume_text = resume_response.content[0].text
                    print("Fallback resume 'qa.md' retrieved successfully.")
                except Exception as fallback_e:
                    print(f"Failed to retrieve fallback resume: {fallback_e}", file=sys.stderr)
                    raise ValueError(f"Could not retrieve resume for evaluation: {e}")
            
            # List jobs and applications
            try:
                jobs = await sheets_session.call_tool("list_jobs")
                jobs_text = jobs.content[0].text if hasattr(jobs, "content") and jobs.content else "[]"
                jobs_data = json.loads(jobs_text)
            except Exception as e:
                print(f"Error listing jobs: {e}", file=sys.stderr)
                jobs_data = []
                
            try:
                apps = await sheets_session.call_tool("list_applications")
                apps_text = apps.content[0].text if hasattr(apps, "content") and apps.content else "[]"
                apps_data = json.loads(apps_text)
            except Exception as e:
                print(f"Error listing applications: {e}", file=sys.stderr)
                apps_data = []
                
            # Helper sets for fast lookup
            existing_links = {app.get("Posting link") for app in apps_data if app.get("Posting link")}
            existing_keys = {(app.get("Job title", "").strip().lower(), app.get("Company + Company size", "").strip().lower()) for app in apps_data}
            
            # Find jobs to promote
            to_promote = []
            for job in jobs_data:
                should_proceed = job.get("Should proceed?", "").strip().lower() == "yes"
                if not should_proceed:
                    continue
                    
                link = job.get("Posting link", "").strip()
                title_company = (job.get("Job title", "").strip().lower(), job.get("Company + Company size", "").strip().lower())
                
                already_promoted = False
                if link and link in existing_links:
                    already_promoted = True
                elif not link and title_company in existing_keys:
                    already_promoted = True
                    
                if not already_promoted:
                    to_promote.append(job)
                    
            print(f"Found {len(to_promote)} jobs ready to promote.")
            if not to_promote:
                return []
                
            # Connect to LinkedIn MCP server
            linkedin_params = get_mcp_params("linkedin", "bash", ["-c", "export $(grep -v '^#' .env | xargs) && exec ./.venv/bin/linkedin-scraper-mcp"])
            
            async with stdio_client(linkedin_params) as (li_read, li_write):
                async with ClientSession(li_read, li_write) as li_session:
                    await li_session.initialize()
                    print("Connected to LinkedIn MCP server.")
                    
                    for i, job in enumerate(to_promote):
                        title = job.get("Job title")
                        raw_company = job.get("Company + Company size", "")
                        clean_company = re.sub(r'\s*\([^)]*\)', '', raw_company).strip()
                        print(f"[{i+1}/{len(to_promote)}] Sourcing outreach contacts for '{title}' at '{clean_company}'...")
                        
                        contacts = []
                        cached = False
                        
                        slug = cache.get_slug(clean_company)
                        if slug:
                            contacts_from_cache = cache.get_contacts(slug)
                            if contacts_from_cache is not None:
                                contacts = contacts_from_cache
                                cached = True
                                print(f"Retrieved contacts from cache for company '{clean_company}' (slug: {slug})")
                        
                        if not cached:
                            lookups_today = cache.get_lookups_count_last_24h()
                            if lookups_today >= 15:
                                print(f"Daily LinkedIn lookup limit (15) reached. Skipping live lookup for '{clean_company}' to protect your account. (The job will remain in the Jobs sheet to be promoted later.)")
                                continue  # Skip promoting this job in this run
                                
                            try:
                                # 1. Search for company to resolve slug
                                comp_res = await li_session.call_tool("search_companies", {"keywords": clean_company})
                                comp_text = comp_res.content[0].text if hasattr(comp_res, "content") else "{}"
                                comp_data = json.loads(comp_text)
                                slug = extract_company_slug(clean_company, comp_data)
                                print(f"Resolved company slug: {slug}")
                                cache.set_slug(clean_company, slug)
                                
                                # Delay between company resolution and recruiter search
                                delay = random.uniform(5.0, 10.0)
                                print(f"Pacing: Waiting {delay:.2f}s before recruiter search...")
                                await asyncio.sleep(delay)
                                
                                # 2. Search for recruiters
                                rec_res = await li_session.call_tool("get_company_employees", {"company_name": slug, "keywords": "Recruiter"})
                                rec_text = rec_res.content[0].text if hasattr(rec_res, "content") else "{}"
                                rec_contacts = await extract_contacts_via_llm(rec_text)
                                contacts.extend(rec_contacts)
                                
                                # Delay between recruiter search and hiring manager search
                                delay = random.uniform(5.0, 10.0)
                                print(f"Pacing: Waiting {delay:.2f}s before hiring manager search...")
                                await asyncio.sleep(delay)
                                
                                # 3. Search for hiring managers
                                hm_res = await li_session.call_tool("get_company_employees", {"company_name": slug, "keywords": "Hiring Manager"})
                                hm_text = hm_res.content[0].text if hasattr(hm_res, "content") else "{}"
                                hm_contacts = await extract_contacts_via_llm(hm_text)
                                contacts.extend(hm_contacts)
                                
                                # De-duplicate contacts
                                seen = set()
                                unique_contacts = []
                                for c in contacts:
                                    key_val = c.get("url") or c.get("name")
                                    if key_val and key_val not in seen:
                                        seen.add(key_val)
                                        unique_contacts.append(c)
                                contacts = unique_contacts
                                
                                # Save contacts and record lookup
                                cache.set_contacts(slug, contacts)
                                cache.record_lookup()
                                
                                # Delay before the next company lookup (if there is another one)
                                if i < len(to_promote) - 1:
                                    delay = random.uniform(15.0, 30.0)
                                    print(f"Pacing: Waiting {delay:.2f}s before the next company lookup...")
                                    await asyncio.sleep(delay)
                                    
                            except Exception as e:
                                print(f"Warning: Failed to lookup LinkedIn employees: {e}", file=sys.stderr)
                                
                        # Format contacts list
                        if contacts:
                            people_contacted = ", ".join([f"{c['name']} ({c['title']}) - {c['url']}" for c in contacts])
                        else:
                            people_contacted = ""
                            
                        # Generate cover letter and referral message
                        try:
                            print("Generating cover letter and referral messages...")
                            contact_message = await generate_outreach_messages(resume_text, job, contacts)
                        except Exception as e:
                            print(f"Error generating outreach messages: {e}", file=sys.stderr)
                            contact_message = f"Error generating outreach: {e}"
                            
                        # Track application in Google Sheets
                        application_date = datetime.date.today().isoformat()
                        try:
                            add_res = await sheets_session.call_tool(
                                "track_application",
                                {
                                    "job_title": job.get("Job title"),
                                    "company": job.get("Company + Company size"),
                                    "posting_link": job.get("Posting link"),
                                    "posting_date": job.get("Posting date"),
                                    "application_date": application_date,
                                    "location": job.get("Location + Remote type (in office, hybrid, remote)"),
                                    "salary": job.get("Salary type"),
                                    "short_description": job.get("Short description"),
                                    "match_details": job.get("match"),
                                    "no_match_details": job.get("no-match"),
                                    "people_contacted": people_contacted,
                                    "contact_message": contact_message,
                                    "comment": "Promoted from Jobs"
                                }
                            )
                            print(f"Promoted to Applications: {add_res.content[0].text if hasattr(add_res, 'content') else add_res}")
                            promoted_jobs.append(job)
                        except Exception as e:
                            print(f"Error promoting job to sheet: {e}", file=sys.stderr)
                            
    return promoted_jobs

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Job search aggregator and pipeline CLI")
    parser.add_argument("position", help="Target position to search for (e.g. QA, Project/delivery manager)")
    parser.add_argument("--skip-unmatched", action="store_true", help="Skip jobs that do not match candidate profile")
    parser.add_argument("--list-only", action="store_true", help="Only scrape and filter jobs, do not match or save to sheets")
    parser.add_argument("--promote", action="store_true", help="Promote qualified jobs with 'Should proceed?'=Yes to Applications tab")
    parser.add_argument("--sites", help="Comma-separated list of job sites to search (linkedin, indeed, zip_recruiter)")
    args = parser.parse_args()
    
    search_sites = None
    if args.sites:
        search_sites = [s.strip() for s in args.sites.split(",") if s.strip()]
        
    if args.promote:
        # Run promotion pipeline
        asyncio.run(run_promotion_pipeline(args.position))
    elif args.list_only:
        # Run search and print only
        results = asyncio.run(run_search_pipeline(args.position, sites=search_sites))
        filtered = filter_jobs(results, args.position)
        normalized = [normalize_job(j) for j in filtered]
        print(json.dumps(normalized, indent=2))
    else:
        # Run full orchestrator pipeline
        asyncio.run(run_orchestrator_pipeline(
            position=args.position,
            skip_unmatched=args.skip_unmatched,
            sites=search_sites
        ))

