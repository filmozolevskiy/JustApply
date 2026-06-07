import os
import uuid
import json
import asyncio
from fastapi import FastAPI, BackgroundTasks, Query
from fastapi.responses import FileResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from database import init_db, get_jobs, update_job_status, add_job

# Initialize SQLite database
init_db()

app = FastAPI(title="Job Hunter Dashboard - Prototype")

# Path to the HTML file
HTML_PATH = os.path.join(os.path.dirname(__file__), "prototype_dashboard.html")
RESUMES_DIR = os.path.join(os.path.dirname(__file__), "resumes")

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

@app.get("/api/jobs")
async def get_all_jobs():
    return get_jobs()

class StatusUpdate(BaseModel):
    status: str

@app.put("/api/jobs/{job_id}/status")
async def update_status(job_id: int, update: StatusUpdate):
    updated = update_job_status(job_id, update.status)
    if not updated:
        return JSONResponse(status_code=404, content={"message": "Job not found"})
    return updated

@app.get("/")
@app.get("/prototype")
async def get_dashboard():
    if os.path.exists(HTML_PATH):
        return FileResponse(HTML_PATH)
    return JSONResponse(status_code=404, content={"message": "HTML prototype file not found"})

@app.post("/api/scrape")
async def trigger_scrape(
    query: str = Query("Senior QA Automation"),
    location: str = Query("Remote"),
    platform: str = Query("brightdata_linkedin"),
    active_resume: str = Query("qa.md"),
    mock_eval: bool = Query(True),
    remote_type: str = Query("any"),
    seniority: str = Query("any"),
    salary: str = Query(""),
    company_size: str = Query("any")
):
    task_id = str(uuid.uuid4())
    # Save the parameters for this task
    active_tasks[task_id] = {
        "query": query,
        "location": location,
        "platform": platform,
        "active_resume": active_resume,
        "mock_eval": mock_eval,
        "remote_type": remote_type,
        "seniority": seniority,
        "salary": salary,
        "company_size": company_size
    }
    return {"status": "triggered", "task_id": task_id}

@app.get("/api/logs/{task_id}")
async def logs_stream(task_id: str):
    if task_id not in active_tasks:
        return JSONResponse(status_code=404, content={"message": "Task ID not found"})
    
    params = active_tasks[task_id]
    
    async def event_generator():
        try:
            # 1. Start Scraper
            yield {
                "data": json.dumps({
                    "type": "log",
                    "level": "info",
                    "message": f"Initializing Bright Data scraping engine for query: '{params['query']}' in '{params['location']}'"
                })
            }
            await asyncio.sleep(1.0)
            
            # 1.5 Show active filters
            filters = []
            if params.get("remote_type") and params["remote_type"] != "any":
                filters.append(f"Remote = {params['remote_type']}")
            if params.get("seniority") and params["seniority"] != "any":
                filters.append(f"Seniority = {params['seniority']}")
            if params.get("salary"):
                filters.append(f"Salary Min = {params['salary']}")
            if params.get("company_size") and params["company_size"] != "any":
                filters.append(f"Company Size = {params['company_size']}")
            
            if filters:
                yield {
                    "data": json.dumps({
                        "type": "log",
                        "level": "warning",
                        "message": f"Applying target filters: {', '.join(filters)}"
                    })
                }
                await asyncio.sleep(0.8)
            
            # 2. Proxy Connect
            yield {
                "data": json.dumps({
                    "type": "log",
                    "level": "info",
                    "message": f"Establishing secure connection to proxy nodes via {params['platform']} client..."
                })
            }
            await asyncio.sleep(1.2)
            
            # 3. HTTP Request
            yield {
                "data": json.dumps({
                    "type": "log",
                    "level": "warning",
                    "message": f"Sending HTTP search payload. Scraping LinkedIn DOM structure..."
                })
            }
            await asyncio.sleep(1.8)
            
            # 4. Parse Results
            yield {
                "data": json.dumps({
                    "type": "log",
                    "level": "info",
                    "message": "Scraped 15 raw job listings. Filtering invalid postings and sponsored ads..."
                })
            }
            await asyncio.sleep(1.0)

            # 5. Load Resume
            yield {
                "data": json.dumps({
                    "type": "log",
                    "level": "info",
                    "message": f"Loading target profile: '{params['active_resume']}' from local storage..."
                })
            }
            await asyncio.sleep(0.8)

            # 6. LLM Match
            yield {
                "data": json.dumps({
                    "type": "log",
                    "level": "warning",
                    "message": f"Starting LLM Match evaluation on 3 candidate postings..."
                })
            }
            await asyncio.sleep(1.5)

            # Mock some dynamically created job items to inject on the client side
            score_1 = 95 if "qa" in params["query"].lower() else 83
            score_2 = 87 if "qa" in params["query"].lower() else 74

            new_jobs = [
                {
                    "id": int(uuid.uuid4().int >> 96),
                    "title": f"Senior {params['query']}",
                    "company": "ScaleLabs Inc.",
                    "size": "500-1000",
                    "link": "https://linkedin.com/jobs/991",
                    "date": "2026-06-07",
                    "location": params["location"],
                    "remoteType": "remote" if "remote" in params["location"].lower() else "hybrid",
                    "seniority": "senior",
                    "salary": "$145k - $175k",
                    "description": f"We are seeking a senior practitioner in {params['query']} to lead our automation pipelines and delivery patterns. Experience with modern web architectures and scripting is essential.",
                    "matchScore": score_1,
                    "matchType": "match" if score_1 >= 85 else "no-match",
                    "shouldProceed": True if score_1 >= 85 else False,
                    "status": "sourced",
                    "resumeUsed": params["active_resume"],
                    "strengths": [f"Direct correlation with {params['query']} requirements", "Strong scripting and automation background"],
                    "gaps": ["No Kubernetes container orchestrations listed"],
                    "contactName": "Sarah Jenkins",
                    "contactRole": "Recruiting Director",
                    "outreachMessage": ""
                },
                {
                    "id": int(uuid.uuid4().int >> 96),
                    "title": f"Lead {params['query']} Developer",
                    "company": "BrightFlow Co.",
                    "size": "100-250",
                    "link": "https://linkedin.com/jobs/992",
                    "date": "2026-06-07",
                    "location": params["location"],
                    "remoteType": "remote" if "remote" in params["location"].lower() else "in office",
                    "seniority": "senior",
                    "salary": "$160k - $190k",
                    "description": f"Lead development and QA integrations for our data processing streams. High proficiency in {params['query']} required.",
                    "matchScore": score_2,
                    "matchType": "match" if score_2 >= 85 else "no-match",
                    "shouldProceed": True if score_2 >= 85 else False,
                    "status": "sourced",
                    "resumeUsed": params["active_resume"],
                    "strengths": ["Excellent team lead history", "Python core framework experience"],
                    "gaps": ["Lacks 8+ years enterprise system maintenance requirements"],
                    "contactName": "David Chen",
                    "contactRole": "Head of Engineering",
                    "outreachMessage": ""
                }
            ]

            yield {
                "data": json.dumps({
                    "type": "log",
                    "level": "success",
                    "message": f"Match Complete. Job 1: {new_jobs[0]['title']} @ {new_jobs[0]['company']} -> {score_1}% Match."
                })
            }
            yield {
                "data": json.dumps({
                    "type": "log",
                    "level": "success",
                    "message": f"Match Complete. Job 2: {new_jobs[1]['title']} @ {new_jobs[1]['company']} -> {score_2}% Match."
                })
            }
            await asyncio.sleep(0.8)

            # Save newly scraped jobs to SQLite DB and update IDs
            for nj in new_jobs:
                db_id = add_job(nj)
                nj["id"] = db_id

            # 7. Yield the integrated results
            yield {
                "data": json.dumps({
                    "type": "result",
                    "jobs": new_jobs
                })
            }
            
            # 8. Done
            yield {
                "data": json.dumps({
                    "type": "done"
                })
            }
            
        except asyncio.CancelledError:
            # Client disconnected early
            pass
            
    return EventSourceResponse(event_generator())

if __name__ == "__main__":
    import uvicorn
    # Bound strictly to localhost/127.0.0.1, no auth required
    uvicorn.run("prototype_dashboard:app", host="127.0.0.1", port=8000, reload=True)
