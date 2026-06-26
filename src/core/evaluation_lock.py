"""Derived Evaluation Lock: active while any Batch Evaluation Job is in flight."""

from __future__ import annotations

import asyncio
import inspect

from ..db import batch_jobs as batch_jobs_db
from .gemini_client import get_client


class EvaluationLockError(Exception):
    """Raised when search/backfill is blocked by an in-flight evaluation round."""

    def __init__(self, job_count: int, batch_count: int = 0):
        self.job_count = job_count
        self.batch_count = batch_count
        super().__init__(format_evaluation_lock_message(job_count))


def format_evaluation_lock_message(job_count: int) -> str:
    return (
        f"Evaluation in progress: {job_count} job(s) are being assessed. "
        "Wait for completion or cancel from the dashboard."
    )


def get_evaluation_lock_status(db_path=None) -> dict:
    """Return derived lock state from non-terminal batch_jobs rows."""
    in_flight = batch_jobs_db.list_in_flight_batch_jobs(db_path=db_path)
    job_ids = batch_jobs_db.get_in_flight_job_ids(db_path=db_path)
    return {
        "active": bool(in_flight),
        "jobCount": len(job_ids),
        "batchCount": len(in_flight),
    }


def is_evaluation_lock_active(db_path=None) -> bool:
    return get_evaluation_lock_status(db_path=db_path)["active"]


def assert_evaluation_lock_clear(db_path=None) -> None:
    status = get_evaluation_lock_status(db_path=db_path)
    if status["active"]:
        raise EvaluationLockError(status["jobCount"], status["batchCount"])


def _cancel_batch_sync(client, batch_name: str) -> None:
    client.batches.cancel(name=batch_name)


async def cancel_in_flight_batches(
    *,
    client=None,
    db_path=None,
    log_func=None,
) -> int:
    """Cancel every in-flight batch via Gemini batches.cancel(); jobs stay in Scraped."""
    async def log(msg: str, level: str = "info"):
        if log_func is None:
            return
        if inspect.iscoroutinefunction(log_func):
            await log_func(msg, level)
        else:
            log_func(msg, level)

    in_flight = batch_jobs_db.list_in_flight_batch_jobs(db_path=db_path)
    if not in_flight:
        return 0

    gemini_client = client or get_client()
    cancelled = 0
    for batch_row in in_flight:
        batch_name = batch_row["batchName"]
        batch_id = batch_row["id"]
        if gemini_client is not None:
            try:
                await asyncio.to_thread(_cancel_batch_sync, gemini_client, batch_name)
            except Exception as exc:
                await log(f"Failed to cancel {batch_name}: {exc}", "warning")
        batch_jobs_db.update_batch_job(
            batch_id,
            {"state": "JOB_STATE_CANCELLED"},
            db_path=db_path,
        )
        cancelled += 1

    await log(f"Cancelled {cancelled} in-flight batch job(s).", "summary")
    return cancelled
