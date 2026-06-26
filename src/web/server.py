import os
import sys
import uuid
import json
import asyncio
from fastapi import FastAPI, BackgroundTasks, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from ..schemas import Job, OutreachSettings

# Add project root to path so database module is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ..db import init_db, get_jobs, get_job, update_job_status, update_job_comment, update_contact_status, get_outreach_settings, save_outreach_settings, update_outreach_template, archive_job, archive_stale_rejected_jobs
from ..service import (
    RateLimitError,
    acquire_scrape_slot,
    begin_enrichment,
    complete_enrichment,
    parse_remote_types,
    search_jobs,
)
from ..pipelines import run_reclassify_pipeline, run_load_more_contacts_pipeline

# Initialize SQLite database
init_db()

app = FastAPI(title="JustApply")

HTML_PATH = os.path.join(os.path.dirname(__file__), "dashboard.html")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
RESUMES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "resumes")

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# In-memory storage for active scraping sessions
active_tasks = {}


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "message": "FastAPI backend online"}


@app.get("/api/regions")
async def get_regions():
    from ..core.regions import REGIONS_MAP
    return REGIONS_MAP


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
    return save_outreach_settings(
        settings.target_russian_speakers,
        settings.target_recruiters,
        settings.short_connection_note,
    )


@app.get("/api/jobs", response_model=list[Job])
async def get_all_jobs(archived: str = Query("active")):
    archive_stale_rejected_jobs()
    return get_jobs(archived_filter=archived)


@app.get("/api/jobs/{job_id}", response_model=Job)
async def get_one_job(job_id: int):
    job = get_job(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"message": "Job not found"})
    return job


class StatusUpdate(BaseModel):
    status: str


@app.put("/api/jobs/{job_id}/status", response_model=Job)
async def update_status(job_id: int, update: StatusUpdate):
    try:
        updated = update_job_status(job_id, update.status)
    except ValueError as e:
        return JSONResponse(status_code=422, content={"message": str(e)})
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


async def run_enrichment_task_with_logs(task_id: str, job_id: int):
    state = active_tasks.get(task_id)
    if not state:
        return

    async def log_callback(message: str, level: str = "info"):
        event = {"level": level, "message": message}
        state.logs.append(event)
        await state.queue.put(event)

    try:
        updated = await complete_enrichment(job_id, log_func=log_callback)
        if updated:
            state.result = {"type": "result", "job": updated.model_dump()}
            state.status = "completed"
        else:
            if not get_job(job_id):
                await log_callback(f"Job id={job_id} not found.", "error")
            state.status = "failed"
    except Exception as e:
        state.status = "failed"
        await log_callback(f"Enrichment task failed: {str(e)}", "error")
    finally:
        await state.queue.put(None)


async def run_reclassify_task_with_logs(task_id: str, job_id: int):
    state = active_tasks.get(task_id)
    if not state:
        return

    async def log_callback(message: str, level: str = "info"):
        event = {"level": level, "message": message}
        state.logs.append(event)
        await state.queue.put(event)

    try:
        updated = await run_reclassify_pipeline(job_id, log_func=log_callback)
        state.result = {"type": "result", "job": updated.model_dump()}
        state.status = "completed"
    except ValueError as e:
        state.status = "failed"
        await log_callback(f"Re-classify failed: {str(e)}", "error")
    except Exception as e:
        state.status = "failed"
        await log_callback(f"Re-classify task failed: {str(e)}", "error")
    finally:
        await state.queue.put(None)


@app.post("/api/jobs/{job_id}/enrich")
async def enrich_job(job_id: int, background_tasks: BackgroundTasks):
    updated = begin_enrichment(job_id)
    if not updated:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    task_id = str(uuid.uuid4())
    state = TaskState({"job_id": job_id})
    active_tasks[task_id] = state
    background_tasks.add_task(run_enrichment_task_with_logs, task_id, job_id)
    return {"task_id": task_id, "job_id": job_id, "job": updated}


COST_PER_APIFY_RUN = 0.05


@app.get("/api/jobs/{job_id}/cache-status")
async def cache_status(job_id: int):
    job = get_job(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"message": "Job not found"})
    from ..db.cache import get_contact_sample
    from ..core.enrichment.contact_sample import company_cache_slug, RECRUITER_SAMPLE_SIZE, RUSSIAN_SAMPLE_SIZE, detect_country_from_location

    detected_country = detect_country_from_location(job.location)
    slug = company_cache_slug(job.company or "", job.companyUrl or "", country=detected_country)
    settings = get_outreach_settings()
    has_company_url = bool(job.companyUrl)

    billable_streams = []
    if has_company_url:
        if settings.get("target_recruiters", True) and not get_contact_sample(slug, stream="recruiters"):
            billable_streams.append({"stream": "Recruiters", "profile_count": RECRUITER_SAMPLE_SIZE, "page": 1})
        if settings.get("target_russian_speakers", True) and not get_contact_sample(slug, stream="russian"):
            billable_streams.append({"stream": "Russian Speakers", "profile_count": RUSSIAN_SAMPLE_SIZE, "page": 1})

    estimated_runs = len(billable_streams)
    will_call_apify = estimated_runs > 0
    return {
        "billable_streams": billable_streams,
        "estimated_runs": estimated_runs,
        "estimated_cost": round(estimated_runs * COST_PER_APIFY_RUN, 2),
        "will_call_apify": will_call_apify,
        "has_cache": not will_call_apify,
    }


@app.post("/api/jobs/{job_id}/reclassify")
async def reclassify_job(job_id: int, background_tasks: BackgroundTasks):
    job = get_job(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"message": "Job not found"})
    if job.status != "accepted":
        return JSONResponse(
            status_code=422,
            content={"message": "Job must be in Accepted lane to re-classify"},
        )

    task_id = str(uuid.uuid4())
    state = TaskState({"job_id": job_id})
    active_tasks[task_id] = state
    background_tasks.add_task(run_reclassify_task_with_logs, task_id, job_id)
    return {"task_id": task_id, "job_id": job_id}


@app.get("/api/jobs/{job_id}/load-more-preflight")
async def load_more_preflight(job_id: int):
    """Return which active streams can be fetched with Load More."""
    job = get_job(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"message": "Job not found"})
    from ..db.cache import get_contact_sample
    from ..core.enrichment.contact_sample import company_cache_slug, resolve_load_more_streams

    slug = company_cache_slug(job.company or "", job.companyUrl or "")
    settings = get_outreach_settings()
    resolved = resolve_load_more_streams(
        slug, settings, job.companyUrl or "", get_contact_sample,
    )
    billable_streams = [
        {k: v for k, v in s.items() if k != "stream_key"}
        for s in resolved["billable_streams"]
    ]
    estimated_runs = len(billable_streams)
    result = {
        "billable_streams": billable_streams,
        "estimated_runs": estimated_runs,
        "estimated_cost": round(estimated_runs * COST_PER_APIFY_RUN, 2),
    }
    if resolved.get("blocked_reason"):
        result["blocked_reason"] = resolved["blocked_reason"]
    return result


@app.post("/api/jobs/{job_id}/load-more-contacts", response_model=Job)
async def load_more_contacts(job_id: int):
    job = get_job(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"message": "Job not found"})
    if job.status != "accepted":
        return JSONResponse(status_code=422, content={"message": "Job must be in Accepted lane to load more contacts"})
    try:
        updated = await run_load_more_contacts_pipeline(job_id)
    except ValueError as e:
        return JSONResponse(status_code=422, content={"message": str(e)})
    return updated


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
    active_resume: str = "general_cv.md"
    mock_eval: bool = True
    # None => follow mock_eval (a mock-eval run also mocks the scraper, so it
    # never spends Bright Data credits). Set False to force a real scrape.
    mock_scraper: bool | None = None
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
        event = {"type": "log", "level": level, "message": message}
        state.logs.append({"level": level, "message": message})
        await state.queue.put(event)

    async def job_saved_callback(job: dict):
        saved_job = get_job(job.get("id"))
        if not saved_job:
            return
        payload = saved_job.model_dump()
        state.jobs.append(payload)
        await state.queue.put({"type": "result", "job": payload})

    try:
        state.jobs = await search_jobs(
            query=params["query"],
            location=params["location"],
            active_resume=params["active_resume"],
            mock_eval=params.get("mock_eval", True),
            mock_scraper=params.get("mock_scraper"),
            allowed_remote_types=parse_remote_types(params.get("remote_type", "any")),
            seniorities=params.get("seniority", "any"),
            company_sizes=params.get("company_size", "any"),
            countries=params.get("countries", "us"),
            time_range=params.get("time_range", "any"),
            log_func=log_callback,
            job_saved_func=job_saved_callback,
            rate_limit=False,
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
    try:
        acquire_scrape_slot(request.mock_eval, request.mock_scraper)
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
    active_resume: str = Query("general_cv.md"),
    mock_eval: bool = Query(True),
    mock_scraper: bool | None = Query(None),
    remote_type: str = Query("any"),
    seniority: str = Query("any"),
    salary: str = Query(""),
    company_size: str = Query("any"),
    countries: str = Query("us"),
    time_range: str = Query("any"),
):
    try:
        acquire_scrape_slot(mock_eval, mock_scraper)
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
        "mock_scraper": mock_scraper,
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
        def _yield_log(level: str, message: str):
            return {
                "data": json.dumps({
                    "type": "log",
                    "level": level,
                    "message": message,
                })
            }

        def _yield_result(item: dict):
            return {"data": json.dumps(item)}

        try:
            for log in state.logs[skip:]:
                yield _yield_log(log["level"], log["message"])

            logs_dropped = 0
            buffered_results = []
            while logs_dropped < len(state.logs):
                try:
                    queued = state.queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if queued is None:
                    await state.queue.put(None)
                    break
                if queued.get("type") == "result":
                    buffered_results.append(queued)
                else:
                    logs_dropped += 1

            for item in buffered_results:
                yield _yield_result(item)

            while True:
                item = await state.queue.get()
                if item is None:
                    break
                if item.get("type") == "result":
                    yield _yield_result(item)
                else:
                    yield _yield_log(item["level"], item["message"])

            if state.status == "completed":
                if state.result is not None:
                    yield _yield_result(state.result)
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
