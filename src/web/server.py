import os
import sys
import uuid
import json
import asyncio
from fastapi import FastAPI, BackgroundTasks, Query
from fastapi.responses import FileResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from ..schemas import Job, OutreachSettings

# Add project root to path so database module is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ..db import init_db, get_jobs, get_job, update_job_status, update_job_comment, update_contact_status, start_enrichment, get_outreach_settings, save_outreach_settings, update_outreach_template, archive_job
from ..rate_limiter import scrape_limiter, RateLimitError

# Initialize SQLite database
init_db()

app = FastAPI(title="Job Hunter Dashboard")

HTML_PATH = os.path.join(os.path.dirname(__file__), "dashboard.html")
RESUMES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "resumes")

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


@app.get("/api/settings/outreach", response_model=OutreachSettings)
async def get_settings_outreach():
    return get_outreach_settings()


@app.put("/api/settings/outreach", response_model=OutreachSettings)
async def put_settings_outreach(settings: OutreachSettings):
    return save_outreach_settings(settings.target_russian_speakers, settings.target_recruiters)


@app.get("/api/jobs", response_model=list[Job])
async def get_all_jobs(archived: str = Query("active")):
    return get_jobs(archived_filter=archived)


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

class TemplateUpdate(BaseModel):
    audience: str
    template: str


@app.post("/api/jobs/{job_id}/archive", response_model=Job)
async def archive_job_endpoint(job_id: int):
    result = archive_job(job_id)
    if result is None:
        job = get_job(job_id)
        if job is None:
            return JSONResponse(status_code=404, content={"message": "Job not found"})
        return JSONResponse(status_code=422, content={"message": "Only Rejected jobs can be archived"})
    return result


@app.put("/api/jobs/{job_id}/template", response_model=Job)
async def update_template(job_id: int, update: TemplateUpdate):
    updated = update_outreach_template(job_id, update.audience, update.template)
    if not updated:
        return JSONResponse(status_code=404, content={"message": "Job not found"})
    return updated


async def _run_enrichment_task(task_id: str, job_id: int, bust_cache: bool = False):
    state = active_tasks.get(task_id)
    if not state:
        return

    async def log_callback(message: str, level: str = "info"):
        event = {"level": level, "message": message}
        state.logs.append(event)
        await state.queue.put(event)

    try:
        job = get_job(job_id)
        if not job:
            await log_callback(f"Job id={job_id} not found.", "error")
            state.status = "failed"
            return

        from ..pipelines import run_enrichment_pipeline
        updated = await run_enrichment_pipeline(job, log_func=log_callback, bust_cache=bust_cache)

        if updated:
            state.result = {"type": "result", "job": updated}
            state.status = "completed"
        else:
            state.status = "failed"
    except Exception as e:
        state.status = "failed"
        await log_callback(f"Enrichment task failed: {str(e)}", "error")
    finally:
        await state.queue.put(None)


async def run_enrichment_task_with_logs(task_id: str, job_id: int):
    await _run_enrichment_task(task_id, job_id, bust_cache=False)


async def run_refresh_contacts_task_with_logs(task_id: str, job_id: int):
    await _run_enrichment_task(task_id, job_id, bust_cache=True)


@app.post("/api/jobs/{job_id}/enrich")
async def enrich_job(job_id: int, background_tasks: BackgroundTasks):
    updated = start_enrichment(job_id)
    if not updated:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    task_id = str(uuid.uuid4())
    state = TaskState({"job_id": job_id})
    active_tasks[task_id] = state
    background_tasks.add_task(run_enrichment_task_with_logs, task_id, job_id)
    return {"task_id": task_id, "job_id": job_id}


@app.post("/api/jobs/{job_id}/refresh-contacts")
async def refresh_contacts(job_id: int, background_tasks: BackgroundTasks):
    updated = start_enrichment(job_id)
    if not updated:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    task_id = str(uuid.uuid4())
    state = TaskState({"job_id": job_id})
    active_tasks[task_id] = state
    background_tasks.add_task(run_refresh_contacts_task_with_logs, task_id, job_id)
    return {"task_id": task_id, "job_id": job_id}


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
        self.result = None  # Generic result payload for non-search tasks
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
        from ..pipelines import run_search_pipeline

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
async def logs_stream(task_id: str, skip: int = 0):
    if task_id not in active_tasks:
        return JSONResponse(status_code=404, content={"message": "Task ID not found"})

    state = active_tasks[task_id]
    if skip < 0:
        skip = 0

    async def event_generator():
        try:
            for log in state.logs[skip:]:
                yield {
                    "data": json.dumps({
                        "type": "log",
                        "level": log["level"],
                        "message": log["message"],
                    })
                }

            # log_callback mirrors each line into logs and the queue; drop
            # the full queued history (skip only affects replay, not queue depth).
            for _ in range(len(state.logs)):
                try:
                    queued = state.queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if queued is None:
                    await state.queue.put(None)
                    break

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
                if state.result is not None:
                    yield {"data": json.dumps(state.result)}
                else:
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
