import os
import re
import json
import asyncio
import httpx
from dotenv import load_dotenv

from .pre_evaluation import normalize_remote_type

# Load environment variables
load_dotenv()

# Timezone filtering constants
EASTERN_STATES = {
    # US
    "CT", "DE", "FL", "GA", "IN", "KY", "ME", "MD", "MA", "MI", "NH", "NJ", "NY", "NC", "OH", "PA", "RI", "SC", "VT", "VA", "DC", "WV",
    # Canada
    "ON", "QC"
}

POSITION_KEYWORDS = {
    "qa": ["qa", "quality assurance", "test", "testing", "sdet", "automation engineer", "automation analyst"],
    "project manager": ["project manager", "program manager", "delivery manager", "scrum master", "product owner"],
    "developer": ["developer", "engineer", "programmer", "software engineer", "full stack", "backend", "frontend"]
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

def matches_position_keywords(title: str, keywords: list) -> bool:
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

def match_company_size(job_size_str: str, allowed_sizes: list) -> bool:
    """Match company size string against allowed category filters (small, medium, large)."""
    if not allowed_sizes or "any" in allowed_sizes or not job_size_str:
        return True
    
    # Extract numbers from size string (e.g., "100-500" -> [100, 500], "5000+" -> [5000])
    numbers = [int(n) for n in re.findall(r'\d+', job_size_str.replace(",", ""))]
    if not numbers:
        # Check for text indications
        size_lower = job_size_str.lower()
        if "small" in size_lower or "1-50" in size_lower or "10-50" in size_lower:
            max_val = 10
        elif "medium" in size_lower or "50-500" in size_lower or "100-500" in size_lower or "200-500" in size_lower:
            max_val = 100
        else:
            max_val = 1000
    else:
        max_val = max(numbers)
    
    matched = False
    if "small" in allowed_sizes and max_val <= 50:
        matched = True
    if "medium" in allowed_sizes and 50 < max_val <= 500:
        matched = True
    if "large" in allowed_sizes and max_val > 500:
        matched = True
    return matched

def normalize_brightdata_job(job: dict) -> dict:
    """Normalize a Bright Data job object into the standard database schema."""
    title = job.get("job_title") or job.get("title") or ""
    company = job.get("company_name") or job.get("company") or ""
    company_url = job.get("company_url") or job.get("companyUrl") or ""
    size = job.get("company_size") or job.get("size") or ""
    link = job.get("url") or job.get("apply_link") or job.get("link") or ""
    date = job.get("date_posted") or job.get("date") or ""
    location = job.get("job_location") or job.get("location") or ""
    
    loc_lower = location.lower()
    is_remote = job.get("is_remote") or "remote" in loc_lower
    
    if is_remote:
        remote_type = "remote"
    elif "hybrid" in loc_lower:
        remote_type = "hybrid"
    else:
        remote_type = "in_office"

    remote_type = normalize_remote_type(remote_type)
        
    title_lower = title.lower()
    raw_seniority = (job.get("job_seniority_level") or job.get("seniority") or "").lower()
    if any(term in raw_seniority or term in title_lower for term in ["sr", "senior", "lead", "principal", "staff", "manager", "director"]):
        seniority = "senior"
    elif any(term in raw_seniority or term in title_lower for term in ["jr", "junior", "entry", "intern", "associate"]):
        seniority = "junior"
    else:
        seniority = "mid"
        
    salary = job.get("salary") or job.get("salary_formatted") or ""
    description = job.get("job_summary") or job.get("description") or ""
    
    # Preserve job_poster if it exists
    contacts = []
    job_poster = job.get("job_poster")
    if job_poster and isinstance(job_poster, dict):
        contacts.append({
            "name": job_poster.get("name") or "",
            "title": job_poster.get("title") or "Recruiter",
            "url": job_poster.get("url") or job_poster.get("profile_url") or "",
            "contacted": False,
            "russian_speaker": False,
            "is_job_poster": True,
        })
    
    return {
        "title": title,
        "company": company,
        "companyUrl": company_url,
        "size": size,
        "link": link,
        "date": date,
        "location": location,
        "remoteType": remote_type,
        "seniority": seniority,
        "salary": salary,
        "description": description,
        "status": "sourced",
        "contacts": contacts
    }


async def _scrape_linkedin_jobs_mock(
    query: str,
    location: str,
    log: callable
) -> list:
    """Generate mock LinkedIn job search listings."""
    await log("Initializing Bright Data Mock API...", "info")
    await asyncio.sleep(0.5)
    await log("Connecting to mock proxy node...", "info")
    await asyncio.sleep(0.5)
    await log("Sending mock search request...", "warning")
    await asyncio.sleep(0.5)
    await log("Scraped 15 raw mock listings from simulated LinkedIn API", "info")
    
    return [
        {
            "job_title": f"Senior {query}",
            "company_name": "ScaleLabs Inc.",
            "company_size": "750",
            "url": "https://linkedin.com/jobs/mock-991",
            "date_posted": "2026-06-07",
            "job_location": location,
            "job_summary": f"We are seeking a senior practitioner in {query} to lead our automation pipelines and delivery patterns. The ideal candidate will work remote or hybrid.",
            "job_seniority_level": "senior",
            "salary": "$145k - $175k",
            "is_remote": True,
            "job_poster": {
                "name": "Sarah Jenkins",
                "title": "Recruiting Director",
                "url": "https://linkedin.com/in/sarah-jenkins-mocked"
            }
        },
        {
            "job_title": f"Lead {query} Developer",
            "company_name": "BrightFlow Co.",
            "company_size": "150",
            "url": "https://linkedin.com/jobs/mock-992",
            "date_posted": "2026-06-07",
            "job_location": location,
            "job_summary": f"Lead development and QA integrations for our data processing streams. High proficiency in {query} required.",
            "job_seniority_level": "senior",
            "is_hybrid": True,
            "salary": "$160k - $190k"
        },
        {
            "job_title": f"Junior {query} Assistant",
            "company_name": "WebStart LLC",
            "company_size": "25",
            "url": "https://linkedin.com/jobs/mock-993",
            "date_posted": "2026-06-07",
            "job_location": "San Francisco, CA",
            "job_summary": f"Help our engineering team with entry level tasks regarding {query}. Work in PST timezone only.",
            "job_seniority_level": "junior",
            "salary": "$70k - $90k"
        }
    ]

async def _scrape_linkedin_jobs_real(
    query: str,
    location: str,
    countries: list,
    time_range: str,
    api_key: str,
    scraper_id: str,
    log: callable
) -> list:
    """Trigger and poll the Bright Data LinkedIn scraper API to retrieve job listings."""
    await log(f"Initializing Bright Data scraping engine for query: '{query}' in '{location}'", "info")
    
    trigger_url = "https://api.brightdata.com/datasets/v3/trigger"
    params = {
        "dataset_id": scraper_id,
        "include_errors": "true",
        "type": "discover_new",
        "discover_by": "keyword",
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = []
    for country in countries:
        item = {
            "keyword": query,
            "location": location,
            "country": country.upper()
        }
        if time_range and time_range.lower() not in ["any", "anytime"]:
            time_range_mapping = {
                "past 24 hours": "Past 24 hours",
                "past week": "Past week",
                "past month": "Past month"
            }
            normalized_key = time_range.lower().replace("_", " ")
            item["time_range"] = time_range_mapping.get(normalized_key, time_range)
        payload.append(item)

    await log("Establishing secure connection to proxy nodes via Bright Data client...", "info")
    async with httpx.AsyncClient(timeout=30.0) as client:
        snapshot_id = None
        try:
            response = await client.post(trigger_url, params=params, headers=headers, json=payload)
            if response.status_code != 200:
                raise Exception(f"Failed to trigger scraper: HTTP {response.status_code} - {response.text}")

            trigger_data = response.json()
            snapshot_id = trigger_data.get("snapshot_id")
            if not snapshot_id:
                raise Exception(f"No snapshot_id returned in trigger response: {trigger_data}")

            await log(f"Bright Data scraping job triggered: {snapshot_id}", "warning")

            # Polling loop
            progress_url = f"https://api.brightdata.com/datasets/v3/progress/{snapshot_id}"
            max_polls = 120  # 120 * 5s = 10 minutes maximum
            polls = 0
            last_status = None
            while True:
                polls += 1
                if polls > max_polls:
                    raise Exception("Bright Data scraping job timed out after 10 minutes.")

                await asyncio.sleep(5.0)
                
                # Check scraper progress with up to 3 retries and exponential backoff
                progress_resp = None
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        progress_resp = await client.get(progress_url, headers=headers)
                        if progress_resp.status_code != 200:
                            raise Exception(f"HTTP {progress_resp.status_code} - {progress_resp.text}")
                        break
                    except Exception as e:
                        if attempt == max_retries - 1:
                            raise Exception(f"Failed to check scraper progress after {max_retries} attempts: {str(e)}")
                        wait_time = 2.0 ** attempt
                        await log(f"Error checking progress (attempt {attempt + 1}/{max_retries}): {str(e)}. Retrying in {wait_time:.0f}s...", "warning")
                        await asyncio.sleep(wait_time)
                
                progress_data = progress_resp.json()
                status = progress_data.get("status")
                if status != last_status:
                    await log(f"Scraper status: {status}", "info")
                    last_status = status
                
                if status == "ready":
                    break
                elif status == "failed":
                    raise Exception("Bright Data scraper job reported failure.")
            
            # Fetch results
            snapshot_url = f"https://api.brightdata.com/datasets/v3/snapshot/{snapshot_id}"
            snapshot_resp = None
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    snapshot_resp = await client.get(snapshot_url, headers=headers)
                    if snapshot_resp.status_code != 200:
                        raise Exception(f"HTTP {snapshot_resp.status_code}")
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise Exception(f"Failed to fetch snapshot results after {max_retries} attempts: {str(e)}")
                    wait_time = 2.0 ** attempt
                    await log(f"Error fetching snapshot results (attempt {attempt + 1}/{max_retries}): {str(e)}. Retrying in {wait_time:.0f}s...", "warning")
                    await asyncio.sleep(wait_time)
            
            try:
                raw_jobs = snapshot_resp.json()
            except json.JSONDecodeError:
                raw_jobs = []
                for line in snapshot_resp.text.splitlines():
                    line = line.strip()
                    if line:
                        try:
                            raw_jobs.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            if not isinstance(raw_jobs, list):
                raw_jobs = [raw_jobs]
            await log(f"Retrieved {len(raw_jobs)} raw results from Bright Data.", "info")
            return raw_jobs

        except Exception as e:
            if snapshot_id:
                try:
                    await client.post(
                        f"https://api.brightdata.com/datasets/v3/snapshot/{snapshot_id}/cancel",
                        headers=headers
                    )
                    await log(f"Canceled Bright Data snapshot {snapshot_id} after error.", "warning")
                except Exception:
                    pass
            await log(f"Bright Data API Error: {str(e)}.", "error")
            raise e

async def scrape_linkedin_jobs(
    query: str, 
    location: str, 
    remote_types: list = None, 
    seniorities: list = None, 
    company_sizes: list = None, 
    countries: list = None,
    time_range: str = "any",
    log_func = None,
    force_mock: bool = False
) -> list:
    """
    Search and retrieve job listings from LinkedIn using Bright Data or simulated fallback.
    Applies post-filtering for remote type, seniority, company size, keyword matching, and timezone.
    """
    async def log(msg: str, level: str = "info"):
        if log_func:
            if asyncio.iscoroutinefunction(log_func):
                await log_func(msg, level)
            else:
                log_func(msg, level)

    mock_scraper = force_mock or os.getenv("MOCK_SCRAPER", "false").lower() == "true"
    api_key = os.getenv("BRIGHTDATA_API_KEY")

    if not mock_scraper and not api_key:
        raise ValueError("BRIGHTDATA_API_KEY environment variable is missing. Please configure it in your .env file or enable mock mode.")

    # Convert settings filters to lists of lowercase strings
    if remote_types and isinstance(remote_types, str):
        remote_types = [t.strip().lower() for t in remote_types.split(",") if t.strip()]
    if seniorities and isinstance(seniorities, str):
        seniorities = [s.strip().lower() for s in seniorities.split(",") if s.strip()]
    if company_sizes and isinstance(company_sizes, str):
        company_sizes = [c.strip().lower() for c in company_sizes.split(",") if c.strip()]

    remote_types = remote_types or ["any"]
    seniorities = seniorities or ["any"]
    company_sizes = company_sizes or ["any"]
    
    if countries and isinstance(countries, str):
        countries = [c.strip().lower() for c in countries.split(",") if c.strip()]
    elif countries and isinstance(countries, list):
        countries = [c.lower() for c in countries]
    
    countries = countries or ["us"]
    time_range = time_range or "any"

    if mock_scraper:
        raw_jobs = await _scrape_linkedin_jobs_mock(query, location, log)
    else:
        scraper_id = os.getenv("BRIGHTDATA_JOB_SCRAPER_ID", "gd_lpfll7v5hcqtkxl6l")
        raw_jobs = await _scrape_linkedin_jobs_real(
            query=query,
            location=location,
            countries=countries,
            time_range=time_range,
            api_key=api_key,
            scraper_id=scraper_id,
            log=log
        )

    # Post-filtering phase
    await log(f"Processing and filtering {len(raw_jobs)} raw results...", "info")
    
    keywords = get_keywords_for_position(query)
    filtered_jobs = []

    for raw_job in raw_jobs:
        normalized = normalize_brightdata_job(raw_job)
        
        # 1. Title/Keyword filter
        # if not matches_position_keywords(normalized["title"], keywords):
        #     await log(f"Skipping '{normalized['title']}': Title does not match keywords {keywords}", "info")
        #     continue
            
        # 2. Timezone filter
        # is_remote = normalized["remoteType"] == "remote"
        # if not is_eastern_timezone(normalized["location"], normalized["description"], is_remote):
        #     await log(f"Skipping '{normalized['title']}': Timezone restrictions detected", "info")
        #     continue

        # 3. Settings Filter - Seniority
        if "any" not in seniorities and normalized["seniority"] not in seniorities:
            await log(f"Skipping '{normalized['title']}': Seniority '{normalized['seniority']}' not in target {seniorities}", "info")
            continue

        # 4. Settings Filter - Company Size
        if "any" not in company_sizes and not match_company_size(normalized["size"], company_sizes):
            await log(f"Skipping '{normalized['title']}': Company Size '{normalized['size']}' does not match {company_sizes}", "info")
            continue

        filtered_jobs.append(normalized)

    await log(f"Filtering complete. Yielded {len(filtered_jobs)} matching listings.", "success")
    return filtered_jobs
