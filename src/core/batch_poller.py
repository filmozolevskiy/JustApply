"""Batch Evaluation Job poller: poll Gemini batches and write back job scores."""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from .. import db as database
from ..db import batch_jobs as batch_jobs_db
from .attribute_gating import (
    format_attribute_mismatch,
    is_unclassified,
    merge_job_attributes,
    passes_attribute_gate,
)
from .gemini_client import get_client
from .matcher import check_recruiter_by_name


TERMINAL_FAILURE_STATES = frozenset({
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
})

POISON_MAX_ATTEMPTS = 3


def poll_cadence_seconds(age_seconds: float) -> int:
    """Return poll interval in seconds for a batch of the given age."""
    age_minutes = age_seconds / 60.0
    if age_minutes <= 10:
        return 60
    if age_minutes <= 40:
        return 120
    if age_minutes <= 180:
        return 300
    return 900


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _batch_state_name(batch_job) -> str:
    state = getattr(batch_job, "state", batch_job)
    if hasattr(state, "name"):
        return state.name
    return str(state)


def is_due_for_poll(batch_row: dict, *, now: datetime | None = None) -> bool:
    """True when enough time has passed since the last poll for this batch."""
    now = now or datetime.now(timezone.utc)
    submitted = _parse_iso(batch_row.get("submittedAt"))
    if submitted is None:
        return True
    if submitted.tzinfo is None:
        submitted = submitted.replace(tzinfo=timezone.utc)

    last_polled = _parse_iso(batch_row.get("lastPolledAt"))
    if last_polled and last_polled.tzinfo is None:
        last_polled = last_polled.replace(tzinfo=timezone.utc)

    reference = last_polled or submitted
    age_seconds = max(0.0, (now - submitted).total_seconds())
    interval = poll_cadence_seconds(age_seconds)
    elapsed = (now - reference).total_seconds()
    return elapsed >= interval


def _parse_search_remote_types(raw) -> list[str] | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def _search_preferences(batch_row: dict) -> tuple[list[str] | None, str]:
    remote_types = _parse_search_remote_types(batch_row.get("searchRemoteTypes"))
    seniorities = batch_row.get("searchSeniorities") or "any"
    return remote_types, seniorities


def _extract_response_text(line: dict) -> str | None:
    if line.get("error"):
        return None
    response = line.get("response") or {}
    if isinstance(response, dict):
        candidates = response.get("candidates") or []
        if candidates:
            content = candidates[0].get("content") or {}
            parts = content.get("parts") or []
            if parts and parts[0].get("text"):
                return parts[0]["text"]
        if response.get("text"):
            return response["text"]
    text = getattr(response, "text", None)
    if text:
        return text
    return None


def parse_evaluation_text(text: str, company_name: str = "") -> dict:
    """Parse Resume Matcher JSON from a batch result line."""
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    if not cleaned:
        return {}

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        return {}

    local_is_recruiter = check_recruiter_by_name(company_name)
    if local_is_recruiter or result.get("isRecruiter"):
        result["isRecruiter"] = True
        result["shouldProceed"] = False
        if result.get("matchScore", 0) >= 75:
            result["matchScore"] = min(70, result.get("matchScore", 0) - 15)
        elif result.get("matchScore", 0) > 0:
            result["matchScore"] = max(0, result.get("matchScore", 0) - 15)
        result["matchType"] = "no-match"
        gaps = result.setdefault("gaps", [])
        if "Posted by a recruiting agency/staffing firm" not in gaps:
            gaps.append("Posted by a recruiting agency/staffing firm")
    return result


def _parse_result_jsonl(content: str | bytes) -> list[dict]:
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    lines = []
    for raw_line in content.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            lines.append(json.loads(raw_line))
        except json.JSONDecodeError:
            continue
    return lines


@dataclass
class CollectResult:
    state: str
    matched: int = 0
    rejected: int = 0
    failed: int = 0
    unclassified: int = 0
    terminal: bool = False


def apply_unclassified_fallback(
    job_id: int,
    *,
    allowed_remote_types: list[str] | None,
    seniorities: str,
    db_path=None,
) -> str:
    """Fall back to scraper attributes after poison retries are exhausted."""
    job = database.get_job(job_id, db_path=db_path)
    if not job:
        return "skipped"

    job_dict = job.model_dump() if hasattr(job, "model_dump") else dict(job)
    if job_dict.get("status") != "scraped":
        return "skipped"

    remote_type = job_dict.get("remoteType") or ""
    seniority = job_dict.get("seniority") or ""
    fields = {
        "matchScore": 0,
        "matchType": "no-match",
        "shouldProceed": False,
        "resumeUsed": job_dict.get("resumeUsed") or "",
        "strengths": [],
        "gaps": [],
        "description": job_dict.get("description") or "",
        "isRecruiter": bool(job_dict.get("isRecruiter")),
        "salary": job_dict.get("salary") or "",
        "remoteType": remote_type,
        "seniority": seniority,
        "unclassified": True,
    }
    database.update_job_evaluation(job_id, fields, db_path=db_path)

    if passes_attribute_gate(
        remote_type,
        seniority,
        allowed_remote_types,
        seniorities,
    ):
        database.update_job_status(job_id, "matched", db_path=db_path)
        return "matched"

    database.update_job_status(job_id, "rejected", db_path=db_path)
    return "rejected"


def handle_poison_job_failure(
    job_id: int,
    *,
    allowed_remote_types: list[str] | None,
    seniorities: str,
    db_path=None,
) -> str:
    """Increment batchAttempts; Unclassified fallback after POISON_MAX_ATTEMPTS."""
    attempts = database.increment_batch_attempts(job_id, db_path=db_path)
    if attempts < POISON_MAX_ATTEMPTS:
        return "retry"

    return apply_unclassified_fallback(
        job_id,
        allowed_remote_types=allowed_remote_types,
        seniorities=seniorities,
        db_path=db_path,
    )


def write_back_job_evaluation(
    job_id: int,
    evaluation: dict,
    *,
    allowed_remote_types: list[str] | None,
    seniorities: str,
    db_path=None,
) -> str:
    """Persist evaluation and move lane. Returns 'matched', 'rejected', or 'skipped'."""
    job = database.get_job(job_id, db_path=db_path)
    if not job:
        return "skipped"

    job_dict = job.model_dump() if hasattr(job, "model_dump") else dict(job)
    original_status = job_dict.get("status", "scraped")
    if original_status != "scraped":
        return "skipped"

    merged = merge_job_attributes(job_dict, evaluation)
    active_resume = job_dict.get("resumeUsed") or "general_cv.md"
    fields = {
        "matchScore": evaluation.get("matchScore", 0),
        "matchType": evaluation.get("matchType", ""),
        "shouldProceed": evaluation.get("shouldProceed", False),
        "resumeUsed": active_resume,
        "strengths": evaluation.get("strengths", []),
        "gaps": evaluation.get("gaps", []),
        "description": evaluation.get("summary") or job_dict.get("description") or "",
        "isRecruiter": evaluation.get("isRecruiter", False),
        "salary": evaluation.get("salary") or job_dict.get("salary") or "",
        "remoteType": merged["remoteType"],
        "seniority": merged["seniority"],
        "unclassified": is_unclassified(evaluation),
    }
    database.update_job_evaluation(job_id, fields, db_path=db_path)

    if passes_attribute_gate(
        merged["remoteType"],
        merged["seniority"],
        allowed_remote_types,
        seniorities,
    ):
        database.update_job_status(job_id, "matched", db_path=db_path)
        return "matched"

    database.update_job_status(job_id, "rejected", db_path=db_path)
    return "rejected"


async def collect_batch_results(
    batch_row: dict,
    *,
    client=None,
    db_path=None,
    log_func=None,
    allowed_remote_types: list[str] | None = None,
    seniorities: str | None = None,
) -> CollectResult:
    """Poll one batch job, write back results when succeeded."""

    async def log(msg: str, level: str = "info"):
        if log_func is None:
            return
        if inspect.iscoroutinefunction(log_func):
            await log_func(msg, level)
        else:
            log_func(msg, level)

    gemini_client = client or get_client()
    batch_id = batch_row["id"]
    batch_name = batch_row["batchName"]

    if gemini_client is None:
        await log("GEMINI_API_KEY not set; skipping batch poll.", "warning")
        return CollectResult(state=batch_row.get("state", ""))

    remote_types, batch_seniorities = _search_preferences(batch_row)
    gate_remote = allowed_remote_types if allowed_remote_types is not None else remote_types
    gate_seniorities = seniorities if seniorities is not None else batch_seniorities

    batch_job = await asyncio.to_thread(gemini_client.batches.get, name=batch_name)
    state = _batch_state_name(batch_job)
    result_file = None
    dest = getattr(batch_job, "dest", None)
    if dest is not None:
        result_file = getattr(dest, "file_name", None) or (
            dest.get("file_name") if isinstance(dest, dict) else None
        )

    update_fields = {
        "state": state,
        "lastPolledAt": _now_iso(),
    }
    if result_file:
        update_fields["resultFileName"] = result_file
    batch_jobs_db.update_batch_job(batch_id, update_fields, db_path=db_path)

    if state == "JOB_STATE_SUCCEEDED":
        if not result_file:
            await log(f"Batch {batch_name} succeeded but has no result file.", "warning")
            return CollectResult(state=state, terminal=True)

        raw_content = await asyncio.to_thread(gemini_client.files.download, file=result_file)
        result_lines = _parse_result_jsonl(raw_content)
        matched = rejected = failed = unclassified = 0
        handled_job_ids: set[int] = set()

        for line in result_lines:
            key = line.get("key")
            if key is None:
                continue
            try:
                job_id = int(key)
            except (TypeError, ValueError):
                continue

            handled_job_ids.add(job_id)
            job = database.get_job(job_id, db_path=db_path)
            company = ""
            if job:
                company = job.company if hasattr(job, "company") else job.get("company", "")

            text = _extract_response_text(line)
            if not text:
                outcome = handle_poison_job_failure(
                    job_id,
                    allowed_remote_types=gate_remote,
                    seniorities=gate_seniorities,
                    db_path=db_path,
                )
                if outcome == "retry":
                    failed += 1
                elif outcome == "matched":
                    unclassified += 1
                    await log(
                        f"Unclassified fallback: job id={job_id} moved to Matched after "
                        f"{POISON_MAX_ATTEMPTS} failed batch attempts.",
                        "warning",
                    )
                elif outcome == "rejected":
                    rejected += 1
                continue

            evaluation = parse_evaluation_text(text, company_name=company)
            if not evaluation:
                outcome = handle_poison_job_failure(
                    job_id,
                    allowed_remote_types=gate_remote,
                    seniorities=gate_seniorities,
                    db_path=db_path,
                )
                if outcome == "retry":
                    failed += 1
                elif outcome == "matched":
                    unclassified += 1
                    await log(
                        f"Unclassified fallback: job id={job_id} moved to Matched after "
                        f"{POISON_MAX_ATTEMPTS} failed batch attempts.",
                        "warning",
                    )
                elif outcome == "rejected":
                    rejected += 1
                continue

            outcome = write_back_job_evaluation(
                job_id,
                evaluation,
                allowed_remote_types=gate_remote,
                seniorities=gate_seniorities,
                db_path=db_path,
            )
            if outcome == "matched":
                matched += 1
            elif outcome == "rejected":
                rejected += 1
                if job:
                    title = job.title if hasattr(job, "title") else job.get("title", "")
                    merged = merge_job_attributes(
                        job.model_dump() if hasattr(job, "model_dump") else dict(job),
                        evaluation,
                    )
                    await log(
                        format_attribute_mismatch(
                            title,
                            company,
                            remote_type=merged["remoteType"],
                            seniority=merged["seniority"],
                            allowed_remote_types=gate_remote,
                            seniorities=gate_seniorities,
                        ),
                        "info",
                    )
            else:
                failed += 1

        for job_id in batch_row.get("jobIds") or []:
            if job_id in handled_job_ids:
                continue
            job = database.get_job(job_id, db_path=db_path)
            if not job:
                continue
            status = job.status if hasattr(job, "status") else job.get("status")
            if status != "scraped":
                continue
            outcome = handle_poison_job_failure(
                job_id,
                allowed_remote_types=gate_remote,
                seniorities=gate_seniorities,
                db_path=db_path,
            )
            if outcome == "retry":
                failed += 1
            elif outcome == "matched":
                unclassified += 1
                await log(
                    f"Unclassified fallback: job id={job_id} moved to Matched after "
                    f"{POISON_MAX_ATTEMPTS} failed batch attempts.",
                    "warning",
                )
            elif outcome == "rejected":
                rejected += 1

        await log(
            f"Batch chunk completed: {matched} matched, {rejected} rejected, "
            f"{failed} failed, {unclassified} unclassified.",
            "summary",
        )
        return CollectResult(
            state=state,
            matched=matched,
            rejected=rejected,
            failed=failed,
            unclassified=unclassified,
            terminal=True,
        )

    if state in TERMINAL_FAILURE_STATES:
        await log(f"Batch {batch_name} ended with state {state}.", "warning")
        matched = rejected = failed = unclassified = 0
        for job_id in batch_row.get("jobIds") or []:
            job = database.get_job(job_id, db_path=db_path)
            if not job:
                continue
            status = job.status if hasattr(job, "status") else job.get("status")
            if status != "scraped":
                continue
            outcome = handle_poison_job_failure(
                job_id,
                allowed_remote_types=gate_remote,
                seniorities=gate_seniorities,
                db_path=db_path,
            )
            if outcome == "retry":
                failed += 1
            elif outcome == "matched":
                unclassified += 1
                await log(
                    f"Unclassified fallback: job id={job_id} moved to Matched after "
                    f"{POISON_MAX_ATTEMPTS} failed batch attempts.",
                    "warning",
                )
            elif outcome == "rejected":
                rejected += 1
        if failed or unclassified or rejected:
            await log(
                f"Batch failure handled: {failed} retrying, {unclassified} unclassified, "
                f"{rejected} rejected.",
                "summary",
            )
        return CollectResult(
            state=state,
            matched=matched,
            rejected=rejected,
            failed=failed,
            unclassified=unclassified,
            terminal=True,
        )

    return CollectResult(state=state, terminal=False)


async def poll_in_flight_batches(
    *,
    client=None,
    db_path=None,
    log_func=None,
    now: datetime | None = None,
) -> list[CollectResult]:
    """Poll every in-flight batch that is due; never submits new batches."""
    results = []
    now = now or datetime.now(timezone.utc)
    for batch_row in batch_jobs_db.list_in_flight_batch_jobs(db_path=db_path):
        if not is_due_for_poll(batch_row, now=now):
            continue
        result = await collect_batch_results(
            batch_row,
            client=client,
            db_path=db_path,
            log_func=log_func,
        )
        results.append(result)
    return results
