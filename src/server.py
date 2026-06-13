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
from .database import init_db, get_jobs, get_job, update_job_status, update_job_comment, update_contact_status, start_enrichment
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

async def run_enrichment_task(job_id: int):
    job = get_job(job_id)
    if not job:
        return

    from .pipelines import run_enrichment_pipeline
    await run_enrichment_pipeline(job)


@app.post("/api/jobs/{job_id}/enrich")
async def enrich_job(job_id: int, background_tasks: BackgroundTasks):
    updated = start_enrichment(job_id)
    if not updated:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

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
        from .pipelines import run_search_pipeline

        remote_types_str = params.get("remote_type", "any")
        if isinstance(remote_types_str, str):
            allowed_remote_types = [t.strip().lower() for t in remote_types_str.split(",") if t.strip()]
        elif isinstance(remote_types_str, list):
            allowed_remote_types = [t.lower() for t in remote_types_str]
        else:
            allowed_remote_types = ["any"]

        state.jobs = await run_search_pipeline(
            query=params["query"],
            location=params["location"],
            active_resume=params["active_resume"],
            mock_eval=params.get("mock_eval", True),
            allowed_remote_types=allowed_remote_types,
            seniorities=params.get("seniority", "any"),
            company_sizes=params.get("company_size", "any"),
            countries=params.get("countries", "us"),
            time_range=params.get("time_range", "any"),
            log_func=log_callback,
        )

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
