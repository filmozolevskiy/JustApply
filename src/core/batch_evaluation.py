"""Gemini Batch Evaluation Job submission for Scraped jobs."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import tempfile
from datetime import datetime, timezone

from google.genai import types

from ..db import batch_jobs as batch_jobs_db
from .gemini_client import MODEL_NAME, get_client
from .matcher import _build_prompt

BATCH_CHUNK_SIZE = 100


def build_batch_request_line(job_id: int, resume_content: str, job: dict) -> dict:
    """Build one JSONL line keyed by job_id with JSON output requested."""
    prompt = _build_prompt(
        resume_content,
        job.get("title", ""),
        job.get("company", ""),
        job.get("description", ""),
    )
    return {
        "key": str(job_id),
        "request": {
            "contents": [{"parts": [{"text": prompt}], "role": "user"}],
            "generation_config": {
                "response_mime_type": "application/json",
            },
        },
    }


def build_batch_jsonl(jobs: list[dict], resume_content: str) -> str:
    lines = []
    for job in jobs:
        job_id = job.get("id")
        if job_id is None:
            continue
        lines.append(json.dumps(build_batch_request_line(job_id, resume_content, job)))
    return "\n".join(lines) + ("\n" if lines else "")


def chunk_jobs(jobs: list[dict], chunk_size: int = BATCH_CHUNK_SIZE) -> list[list[dict]]:
    return [jobs[i:i + chunk_size] for i in range(0, len(jobs), chunk_size)]


def _batch_state_name(batch_job) -> str:
    state = batch_job.state
    if hasattr(state, "name"):
        return state.name
    return str(state)


def _submit_jsonl_batch(
    jsonl_content: str,
    display_name: str,
    *,
    client,
) -> tuple[str, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as handle:
        handle.write(jsonl_content)
        temp_path = handle.name

    try:
        uploaded = client.files.upload(
            file=temp_path,
            config=types.UploadFileConfig(
                display_name=display_name,
                mime_type="text/plain",
            ),
        )
        batch_job = client.batches.create(
            model=MODEL_NAME,
            src=uploaded.name,
            config={"display_name": display_name},
        )
        return batch_job.name, _batch_state_name(batch_job)
    finally:
        os.unlink(temp_path)


async def submit_batch_evaluation(
    jobs: list[dict],
    resume_content: str,
    kind: str = "search",
    *,
    client=None,
    log_func=None,
    db_path=None,
    allowed_remote_types: list[str] | None = None,
    seniorities: str = "any",
) -> list[dict]:
    """Submit chunked Batch Evaluation Jobs and persist batch_jobs rows."""

    async def log(msg: str, level: str = "info"):
        if log_func is None:
            return
        if inspect.iscoroutinefunction(log_func):
            await log_func(msg, level)
        else:
            log_func(msg, level)

    if not jobs:
        return []

    in_flight_ids = batch_jobs_db.get_in_flight_job_ids(db_path=db_path)
    pending = [job for job in jobs if job.get("id") not in in_flight_ids]
    skipped = len(jobs) - len(pending)
    if skipped:
        await log(f"Skipping {skipped} job(s) already covered by in-flight batches.", "info")
    if not pending:
        return []

    gemini_client = client or get_client()
    if gemini_client is None:
        await log("GEMINI_API_KEY not set; jobs saved to Scraped without batch submission.", "warning")
        return []

    created = []
    chunks = chunk_jobs(pending)
    for index, chunk in enumerate(chunks, start=1):
        job_ids = [job["id"] for job in chunk]
        jsonl_content = build_batch_jsonl(chunk, resume_content)
        display_name = f"justapply-{kind}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{index}"
        await log(f"Submitting batch {index}/{len(chunks)} ({len(chunk)} jobs)...")

        batch_name, state = await asyncio.to_thread(
            _submit_jsonl_batch,
            jsonl_content,
            display_name,
            client=gemini_client,
        )
        row = batch_jobs_db.create_batch_job(
            batch_name=batch_name,
            display_name=display_name,
            state=state,
            kind=kind,
            job_ids=job_ids,
            search_remote_types=allowed_remote_types,
            search_seniorities=seniorities,
            db_path=db_path,
        )
        created.append(row)

    await log(f"Submitted {len(created)} batch job(s) for {len(pending)} job(s).", "summary")
    return created
