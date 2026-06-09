import os
import sys
import uuid
import json
import asyncio
from fastapi import FastAPI, BackgroundTasks, Query
from fastapi.responses import FileResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from .schemas import Job

# Add project root to path so database module is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from .database import init_db, get_jobs, get_job, update_job_status, add_job, update_job_comment, update_contact_status, job_exists, get_db_connection
from .rate_limiter import scrape_limiter, RateLimitError

# Initialize SQLite database
init_db()

app = FastAPI(title="Job Hunter Dashboard")

HTML_PATH = os.path.join(os.path.dirname(__file__), "dashboard.html")
RESUMES_DIR = os.path.join(os.path.dirname(__file__), "..", "resumes")

# In-memory storage for active scraping sessions
active_tasks = {}


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "message": "FastAPI backend online"}


@app.get("/api/resumes")
async def get_resumes():
    if not os.path.exists(RESUMES_DIR):
        return []
    resumes = []
    for filename in sorted(os.listdir(RESUMES_DIR)):
        if filename.endswith(".md"):
            filepath = os.path.join(RESUMES_DIR, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                resumes.append({"name": filename, "content": content})
            except Exception:
                pass
    return resumes


@app.get("/api/jobs", response_model=list[Job])
async def get_all_jobs():
    return get_jobs()


class StatusUpdate(BaseModel):
    status: str


@app.put("/api/jobs/{job_id}/status", response_model=Job)
async def update_status(job_id: int, update: StatusUpdate):
    updated = update_job_status(job_id, update.status)
    if not updated:
        return JSONResponse(status_code=404, content={"message": "Job not found"})
    return updated


class CommentUpdate(BaseModel):
    comment: str


@app.put("/api/jobs/{job_id}/comment", response_model=Job)
async def update_comment(job_id: int, update: CommentUpdate):
    updated = update_job_comment(job_id, update.comment)
    if not updated:
        return JSONResponse(status_code=404, content={"message": "Job not found"})
    return updated


class ContactUpdate(BaseModel):
    contacted: bool


@app.put("/api/jobs/{job_id}/contacts/{contact_idx}", response_model=Job)
async def update_contact(job_id: int, contact_idx: int, update: ContactUpdate):
    updated = update_contact_status(job_id, contact_idx, update.contacted)
    if updated is None:
        return JSONResponse(status_code=404, content={"message": "Job or contact not found"})
    return updated


def build_outreach_prompt(resume: str, job_title: str, company: str, description: str, contact_name: str, is_russian: bool) -> str:
    greeting_instruction = "Greet the person in Russian (e.g. 'Добрый день, [Name]!') since their profile indicates they speak Russian." if is_russian else "Greet the person in English (e.g. 'Hello [Name],')."
    
    return f"""You are a helpful assistant writing a professional outreach and referral request message on LinkedIn.

CANDIDATE RESUME:
{resume}

JOB DETAILS:
Title: {job_title}
Company: {company}
Description/Summary: {description}

RECIPIENT:
Name: {contact_name}

INSTRUCTIONS:
1. {greeting_instruction}
2. Keep the message concise (100-150 words), professional, and polite.
3. Reference the job title and company.
4. Highlight 1 or 2 matching strengths from the candidate's resume that are highly relevant to this job description.
5. End with a polite request to discuss further.
6. Do not include any placeholder text (like [Date], [Hiring Manager], etc.). Output the final draft directly. No markdown formatting, just the raw text of the message.
"""


def _load_resume_content(resume_name: str) -> str:
    from src.core.matcher import load_resume
    try:
        return load_resume(resume_name)
    except Exception:
        pass
    try:
        return load_resume("qa.md")
    except Exception:
        return ""


async def _generate_outreach_message(job: dict, contact_name: str, is_russian: bool, resume_content: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key and resume_content:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            prompt = build_outreach_prompt(
                resume_content,
                job.get("title", ""),
                job.get("company", ""),
                job.get("description", ""),
                contact_name,
                is_russian,
            )
            response = await model.generate_content_async(prompt)
            return response.text.strip()
        except Exception:
            pass

    resume_name = job.get("resumeUsed") or "qa.md"
    profile_name = (
        "QA Automator" if resume_name == "qa.md"
        else "Delivery Manager" if resume_name == "project_manager.md"
        else "BI Analyst"
    )
    greeting = f"Добрый день, {contact_name}!\n\n" if is_russian else f"Hello {contact_name},\n\n"
    return (
        f"{greeting}I recently saw your post for the {job.get('title', '')} role at "
        f"{job.get('company', '')}. Based on my matched skills in {resume_name} ({profile_name}), "
        f"I believe my background aligning developer suites and testing cycles matches your goals.\n\n"
        f"Let me know if we can schedule a quick discussion!\n\nBest,\nCandidate"
    )


async def run_enrichment_task(job_id: int):
    job = get_job(job_id)
    if not job:
        return

    from src.core.outreach import source_contacts
    contacts = await source_contacts(job)

    primary_contact = contacts[0] if contacts else None
    contact_name = primary_contact.get("name") if primary_contact else "Hiring Manager"
    is_russian = bool(primary_contact.get("russian_speaker")) if primary_contact else False

    resume_name = job.get("resumeUsed") or "qa.md"
    resume_content = _load_resume_content(resume_name)
    outreach_message = await _generate_outreach_message(job, contact_name, is_russian, resume_content)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE jobs SET contacts = ?, outreachMessage = ?, status = 'enriched' WHERE id = ?",
        (json.dumps(contacts), outreach_message, job_id),
    )
    conn.commit()
    conn.close()


@app.post("/api/jobs/{job_id}/enrich")
async def enrich_job(job_id: int, background_tasks: BackgroundTasks):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM jobs WHERE id = ?", (job_id,))
    if not cursor.fetchone():
        conn.close()
        return JSONResponse(status_code=404, content={"message": "Job not found"})
    
    cursor.execute("UPDATE jobs SET status = 'enriching' WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()

    background_tasks.add_task(run_enrichment_task, job_id)
    return {"status": "enriching", "job_id": job_id}


@app.get("/")
@app.get("/dashboard")
async def get_dashboard():
    if os.path.exists(HTML_PATH):
        return FileResponse(HTML_PATH)
    return JSONResponse(status_code=404, content={"message": "Dashboard HTML file not found"})


class TaskState:
    def __init__(self, params):
        self.params = params
        self.logs = []
        self.queue = asyncio.Queue()
        self.jobs = []
        self.status = "running"


class SearchRequest(BaseModel):
    query: str
    location: str
    platform: str = "brightdata_linkedin"
    active_resume: str = "qa.md"
    mock_eval: bool = True
    remote_type: str = "any"
    seniority: str = "any"
    salary: str = ""
    company_size: str = "any"
    countries: str = "us"
    time_range: str = "any"


async def run_scraping_task(task_id: str):
    state = active_tasks.get(task_id)
    if not state:
        return

    params = state.params

    async def log_callback(message: str, level: str = "info"):
        event = {"level": level, "message": message}
        state.logs.append(event)
        await state.queue.put(event)

    try:
        from src.core.scraper import scrape_linkedin_jobs
        from src.core.matcher import load_resume, evaluate_job

        # Parse remote_type into a list of allowed types
        remote_types_str = params.get("remote_type", "any")
        if isinstance(remote_types_str, str):
            allowed_remote_types = [t.strip().lower() for t in remote_types_str.split(",") if t.strip()]
        elif isinstance(remote_types_str, list):
            allowed_remote_types = [t.lower() for t in remote_types_str]
        else:
            allowed_remote_types = ["any"]

        jobs = await scrape_linkedin_jobs(
            query=params["query"],
            location=params["location"],
            remote_types=allowed_remote_types,
            seniorities=params["seniority"],
            company_sizes=params["company_size"],
            countries=params.get("countries", "us"),
            time_range=params.get("time_range", "any"),
            log_func=log_callback,
        )

        active_resume = params["active_resume"]
        mock_eval = params.get("mock_eval", True)
        resume_content = None
        if not mock_eval:
            try:
                resume_content = load_resume(active_resume)
                await log_callback(f"Loaded resume profile: {active_resume}", "info")
            except FileNotFoundError:
                await log_callback(f"Resume not found: {active_resume}. Skipping evaluation.", "warning")

        saved_jobs = []
        for job in jobs:
            title = job.get("title") or ""
            company = job.get("company") or ""
            link = job.get("link") or ""
            if job_exists(title, company, link):
                await log_callback(f"Skipping duplicate job: '{title}' at '{company}'", "info")
                continue

            job["resumeUsed"] = active_resume

            if mock_eval:
                job.setdefault("matchScore", 85)
                job.setdefault("matchType", "match")
                job.setdefault("shouldProceed", True)
                job.setdefault("strengths", ["Good technical background"])
                job.setdefault("gaps", ["Review job requirements carefully"])
                
                from src.core.matcher import check_recruiter_by_name
                if check_recruiter_by_name(company):
                    job["isRecruiter"] = True
                    job["shouldProceed"] = False
                    job["matchScore"] = 70
                    job["matchType"] = "no-match"
                    job["gaps"].append("Posted by a recruiting agency/staffing firm")
                else:
                    job["isRecruiter"] = False
            elif resume_content:
                await log_callback(f"Evaluating '{job['title']}' at {job['company']}...", "info")
                evaluation = await evaluate_job(job, resume_content, log_callback, allowed_remote_types)
                if evaluation:
                    job["matchScore"] = evaluation.get("matchScore", 0)
                    job["matchType"] = evaluation.get("matchType", "")
                    job["shouldProceed"] = evaluation.get("shouldProceed", False)
                    job["strengths"] = evaluation.get("strengths", [])
                    job["gaps"] = evaluation.get("gaps", [])
                    if "remoteType" in evaluation:
                        job["remoteType"] = evaluation["remoteType"]
                    if "summary" in evaluation:
                        job["description"] = evaluation["summary"]
                    job["isRecruiter"] = evaluation.get("isRecruiter", False)
                    if evaluation.get("salary"):
                        job["salary"] = evaluation["salary"]

            db_id = add_job(job)
            if db_id is not None:
                job["id"] = db_id
                saved_jobs.append(job)

        state.jobs = saved_jobs
        state.status = "completed"
        await log_callback("Jobs database sync completed successfully.", "success")

    except Exception as e:
        state.status = "failed"
        await log_callback(f"Task execution failed: {str(e)}", "error")

    finally:
        await state.queue.put(None)


@app.post("/api/search")
async def trigger_search(request: SearchRequest, background_tasks: BackgroundTasks):
    is_mock_scraper = os.getenv("MOCK_SCRAPER", "false").lower() == "true"
    is_real = (not request.mock_eval) or (not is_mock_scraper)
    if is_real:
        try:
            scrape_limiter.acquire()
        except RateLimitError as e:
            return JSONResponse(
                status_code=429,
                content={"message": f"Too many requests. Please wait {e.wait_seconds} seconds."}
            )

    task_id = str(uuid.uuid4())
    state = TaskState(request.model_dump())
    active_tasks[task_id] = state
    background_tasks.add_task(run_scraping_task, task_id)
    return {"status": "triggered", "task_id": task_id}


@app.post("/api/scrape")
async def trigger_scrape(
    background_tasks: BackgroundTasks,
    query: str = Query("Senior QA Automation"),
    location: str = Query("Remote"),
    platform: str = Query("brightdata_linkedin"),
    active_resume: str = Query("qa.md"),
    mock_eval: bool = Query(True),
    remote_type: str = Query("any"),
    seniority: str = Query("any"),
    salary: str = Query(""),
    company_size: str = Query("any"),
    countries: str = Query("us"),
    time_range: str = Query("any"),
):
    is_mock_scraper = os.getenv("MOCK_SCRAPER", "false").lower() == "true"
    is_real = (not mock_eval) or (not is_mock_scraper)
    if is_real:
        try:
            scrape_limiter.acquire()
        except RateLimitError as e:
            return JSONResponse(
                status_code=429,
                content={"message": f"Too many requests. Please wait {e.wait_seconds} seconds."}
            )

    task_id = str(uuid.uuid4())
    params = {
        "query": query,
        "location": location,
        "platform": platform,
        "active_resume": active_resume,
        "mock_eval": mock_eval,
        "remote_type": remote_type,
        "seniority": seniority,
        "salary": salary,
        "company_size": company_size,
        "countries": countries,
        "time_range": time_range,
    }
    state = TaskState(params)
    active_tasks[task_id] = state
    background_tasks.add_task(run_scraping_task, task_id)
    return {"status": "triggered", "task_id": task_id}


@app.get("/api/logs/{task_id}")
async def logs_stream(task_id: str):
    if task_id not in active_tasks:
        return JSONResponse(status_code=404, content={"message": "Task ID not found"})

    state = active_tasks[task_id]

    async def event_generator():
        try:
            for log in state.logs:
                yield {
                    "data": json.dumps({
                        "type": "log",
                        "level": log["level"],
                        "message": log["message"],
                    })
                }

            while True:
                log = await state.queue.get()
                if log is None:
                    break
                yield {
                    "data": json.dumps({
                        "type": "log",
                        "level": log["level"],
                        "message": log["message"],
                    })
                }

            if state.status == "completed":
                yield {"data": json.dumps({"type": "result", "jobs": state.jobs})}
                yield {"data": json.dumps({"type": "done"})}
            else:
                yield {
                    "data": json.dumps({
                        "type": "log",
                        "level": "error",
                        "message": "Scraping pipeline finished with errors.",
                    })
                }
                yield {"data": json.dumps({"type": "done"})}

        except asyncio.CancelledError:
            pass

    return EventSourceResponse(event_generator())
