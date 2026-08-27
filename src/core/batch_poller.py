"""Batch Evaluation Job poller: poll Gemini batches and write back job scores."""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from .. import db as database
from ..db import batch_jobs as batch_jobs_db
from .annual_posted_salary import annualize_posted_salary
from .attribute_gating import (
    is_unclassified,
    merge_job_attributes,
    passes_attribute_gate,
)
from .batch_evaluation import submit_batch_evaluation
from .gemini_client import get_client
from .matcher import check_recruiter_by_name, load_resume

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
    return datetime.now(UTC).isoformat()


def _batch_state_name(batch_job) -> str:
    state = getattr(batch_job, "state", batch_job)
    if hasattr(state, "name"):
        return state.name
    return str(state)


def is_due_for_poll(batch_row: dict, *, now: datetime | None = None) -> bool:
    """True when enough time has passed since the last poll for this batch."""
    now = now or datetime.now(UTC)
    submitted = _parse_iso(batch_row.get("submittedAt"))
    if submitted is None:
        return True
    if submitted.tzinfo is None:
        submitted = submitted.replace(tzinfo=UTC)

    last_polled = _parse_iso(batch_row.get("lastPolledAt"))
    if last_polled and last_polled.tzinfo is None:
        last_polled = last_polled.replace(tzinfo=UTC)

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


def _search_preferences(batch_row: dict) -> tuple[list[str] | None, str, str, int | None]:
    remote_types = _parse_search_remote_types(batch_row.get("searchRemoteTypes"))
    seniorities = batch_row.get("searchSeniorities") or "any"
    employment_types = batch_row.get("searchEmploymentTypes") or "any"
    raw_salary_min = batch_row.get("searchSalaryMin")
    salary_min: int | None
    if raw_salary_min is None or raw_salary_min == "":
        salary_min = None
    else:
        try:
            salary_min = int(raw_salary_min)
        except (TypeError, ValueError):
            salary_min = None
    return remote_types, seniorities, employment_types, salary_min


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
    attribute_filtered: int = 0
    fallback_rejected: int = 0
    failed: int = 0
    unclassified: int = 0
    terminal: bool = False


def _chunk_summary_line(
    matched: int,
    attribute_filtered: int,
    fallback_rejected: int,
    failed: int,
    unclassified: int,
) -> str:
    return (
        f"Batch chunk completed: {matched} matched, "
        f"{attribute_filtered} attribute-filtered, "
        f"{fallback_rejected} fallback-rejected, "
        f"{failed} failed, {unclassified} unclassified"
    )


def _round_summary_line(
    kind: str,
    matched: int,
    attribute_filtered: int,
    fallback_rejected: int,
    failed: int,
    unclassified: int,
) -> str:
    return (
        f"Evaluation round complete ({kind}): {matched} matched, "
        f"{attribute_filtered} attribute-filtered, "
        f"{fallback_rejected} fallback-rejected, "
        f"{failed} failed, {unclassified} unclassified"
    )


@dataclass
class _RoundAccumulator:
    matched: int = 0
    attribute_filtered: int = 0
    fallback_rejected: int = 0
    failed: int = 0
    unclassified: int = 0
    kind: str = "search"
    chunk_count: int = 0
    gate_remote_types: list[str] | None = None
    gate_seniorities: str = "any"
    gate_employment_types: str = "any"
    gate_salary_min: int | None = None

    def add(
        self,
        result: CollectResult,
        kind: str,
        *,
        gate_remote_types: list[str] | None = None,
        gate_seniorities: str = "any",
        gate_employment_types: str = "any",
        gate_salary_min: int | None = None,
    ) -> None:
        if not result.terminal:
            return
        self.matched += result.matched
        self.attribute_filtered += result.attribute_filtered
        self.fallback_rejected += result.fallback_rejected
        self.failed += result.failed
        self.unclassified += result.unclassified
        if kind:
            self.kind = kind
        self.chunk_count += 1
        self.gate_remote_types = gate_remote_types
        self.gate_seniorities = gate_seniorities or "any"
        self.gate_employment_types = gate_employment_types or "any"
        self.gate_salary_min = gate_salary_min

    def clear(self) -> None:
        self.matched = 0
        self.attribute_filtered = 0
        self.fallback_rejected = 0
        self.failed = 0
        self.unclassified = 0
        self.kind = "search"
        self.chunk_count = 0
        self.gate_remote_types = None
        self.gate_seniorities = "any"
        self.gate_employment_types = "any"
        self.gate_salary_min = None

    def gate_prefs(self) -> dict:
        return {
            "allowed_remote_types": self.gate_remote_types,
            "seniorities": self.gate_seniorities,
            "employment_types": self.gate_employment_types,
            "salary_min": self.gate_salary_min,
        }


_round_accumulator = _RoundAccumulator()


def reset_round_accumulator() -> None:
    """Clear in-progress round totals (tests and orphaned cancel paths)."""
    _round_accumulator.clear()


def _accumulate_terminal_result(result: CollectResult, batch_row: dict) -> None:
    remote_types, seniorities, employment_types, salary_min = _search_preferences(
        batch_row
    )
    _round_accumulator.add(
        result,
        batch_row.get("kind") or "search",
        gate_remote_types=remote_types,
        gate_seniorities=seniorities,
        gate_employment_types=employment_types,
        gate_salary_min=salary_min,
    )


async def _emit_round_summary_if_ready(*, log_func=None) -> dict | None:
    """Emit Evaluation Round Summary when the lock is clear and chunks were tallied.

    Returns gate prefs from the round when a summary was emitted, else None.
    """
    if _round_accumulator.chunk_count == 0:
        return None

    async def log(msg: str, level: str = "info"):
        if log_func is None:
            return
        if inspect.iscoroutinefunction(log_func):
            await log_func(msg, level)
        else:
            log_func(msg, level)

    await log(
        _round_summary_line(
            _round_accumulator.kind,
            _round_accumulator.matched,
            _round_accumulator.attribute_filtered,
            _round_accumulator.fallback_rejected,
            _round_accumulator.failed,
            _round_accumulator.unclassified,
        ),
        "summary",
    )
    prefs = _round_accumulator.gate_prefs()
    _round_accumulator.clear()
    return prefs


async def _auto_retry_failed_scraped_jobs(
    *,
    gate_prefs: dict,
    client=None,
    db_path=None,
    log_func=None,
) -> list[dict]:
    """Submit a retry Batch Evaluation Job for poison-failed Scraped jobs."""

    async def log(msg: str, level: str = "info"):
        if log_func is None:
            return
        if inspect.iscoroutinefunction(log_func):
            await log_func(msg, level)
        else:
            log_func(msg, level)

    jobs = database.get_retryable_scraped_jobs(
        db_path=db_path,
        max_attempts=POISON_MAX_ATTEMPTS,
    )
    if not jobs:
        return []

    await log(f"Auto-retrying {len(jobs)} failed Scraped job(s)…", "summary")

    try:
        resume_content = load_resume("general_cv.md")
    except FileNotFoundError:
        await log("No resume found — cannot auto-retry failed Scraped jobs.", "error")
        return []

    job_dicts = [job.model_dump() if hasattr(job, "model_dump") else dict(job) for job in jobs]
    remote_types = gate_prefs.get("allowed_remote_types")
    if remote_types is None:
        remote_types = ["any"]
    return await submit_batch_evaluation(
        job_dicts,
        resume_content,
        kind="retry",
        client=client,
        log_func=log_func,
        db_path=db_path,
        allowed_remote_types=remote_types,
        seniorities=gate_prefs.get("seniorities") or "any",
        employment_types=gate_prefs.get("employment_types") or "any",
        salary_min=gate_prefs.get("salary_min"),
    )


def apply_unclassified_fallback(
    job_id: int,
    *,
    allowed_remote_types: list[str] | None,
    seniorities: str,
    employment_types: str = "any",
    salary_min: int | None = None,
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
    employment_type = job_dict.get("employmentType") or ""
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
        "employmentType": employment_type,
        "unclassified": True,
    }
    database.update_job_evaluation(job_id, fields, db_path=db_path)

    if passes_attribute_gate(
        remote_type,
        seniority,
        allowed_remote_types,
        seniorities,
        employment_type=employment_type,
        employment_types=employment_types,
        annual_max=job_dict.get("annualMax"),
        annual_min=job_dict.get("annualMin"),
        salary_min=salary_min,
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
    employment_types: str = "any",
    salary_min: int | None = None,
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
        employment_types=employment_types,
        salary_min=salary_min,
        db_path=db_path,
    )


def write_back_job_evaluation(
    job_id: int,
    evaluation: dict,
    *,
    allowed_remote_types: list[str] | None,
    seniorities: str,
    employment_types: str = "any",
    salary_min: int | None = None,
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
    annual_band = annualize_posted_salary(
        evaluation.get("postedSalary"),
        job_location=job_dict.get("location") or "",
    )
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
        "annualMin": annual_band["annualMin"] if annual_band else None,
        "annualMax": annual_band["annualMax"] if annual_band else None,
        "annualCurrency": annual_band["annualCurrency"] if annual_band else None,
        "remoteType": merged["remoteType"],
        "seniority": merged["seniority"],
        "employmentType": merged["employmentType"],
        "unclassified": is_unclassified(evaluation),
    }
    database.update_job_evaluation(job_id, fields, db_path=db_path)

    if passes_attribute_gate(
        merged["remoteType"],
        merged["seniority"],
        allowed_remote_types,
        seniorities,
        employment_type=merged["employmentType"],
        employment_types=employment_types,
        annual_max=fields["annualMax"],
        annual_min=fields["annualMin"],
        salary_min=salary_min,
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
    employment_types: str | None = None,
    salary_min: int | None = None,
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

    remote_types, batch_seniorities, batch_employment_types, batch_salary_min = (
        _search_preferences(batch_row)
    )
    gate_remote = allowed_remote_types if allowed_remote_types is not None else remote_types
    gate_seniorities = seniorities if seniorities is not None else batch_seniorities
    gate_employment_types = (
        employment_types if employment_types is not None else batch_employment_types
    )
    gate_salary_min = salary_min if salary_min is not None else batch_salary_min

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
        matched = attribute_filtered = fallback_rejected = failed = unclassified = 0
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
                    employment_types=gate_employment_types,
                    salary_min=gate_salary_min,
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
                    fallback_rejected += 1
                continue

            evaluation = parse_evaluation_text(text, company_name=company)
            if not evaluation:
                outcome = handle_poison_job_failure(
                    job_id,
                    allowed_remote_types=gate_remote,
                    seniorities=gate_seniorities,
                    employment_types=gate_employment_types,
                    salary_min=gate_salary_min,
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
                    fallback_rejected += 1
                continue

            outcome = write_back_job_evaluation(
                job_id,
                evaluation,
                allowed_remote_types=gate_remote,
                seniorities=gate_seniorities,
                employment_types=gate_employment_types,
                salary_min=gate_salary_min,
                db_path=db_path,
            )
            if outcome == "matched":
                matched += 1
            elif outcome == "rejected":
                attribute_filtered += 1
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
                employment_types=gate_employment_types,
                salary_min=gate_salary_min,
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
                fallback_rejected += 1

        await log(
            _chunk_summary_line(
                matched,
                attribute_filtered,
                fallback_rejected,
                failed,
                unclassified,
            ),
            "summary",
        )
        return CollectResult(
            state=state,
            matched=matched,
            attribute_filtered=attribute_filtered,
            fallback_rejected=fallback_rejected,
            failed=failed,
            unclassified=unclassified,
            terminal=True,
        )

    if state in TERMINAL_FAILURE_STATES:
        await log(f"Batch {batch_name} ended with state {state}.", "warning")
        matched = attribute_filtered = fallback_rejected = failed = unclassified = 0
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
                employment_types=gate_employment_types,
                salary_min=gate_salary_min,
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
                fallback_rejected += 1
        if failed or unclassified or fallback_rejected:
            await log(
                f"Batch failure handled: {failed} retrying, {unclassified} unclassified, "
                f"{fallback_rejected} fallback-rejected.",
                "summary",
            )
        return CollectResult(
            state=state,
            matched=matched,
            attribute_filtered=attribute_filtered,
            fallback_rejected=fallback_rejected,
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
    """Poll every in-flight batch that is due; may auto-submit poison retries."""
    now = now or datetime.now(UTC)
    in_flight = batch_jobs_db.list_in_flight_batch_jobs(db_path=db_path)
    if not in_flight:
        # Drop orphaned totals (e.g. remaining batches cancelled mid-round).
        reset_round_accumulator()
        return []

    results: list[CollectResult] = []
    for batch_row in in_flight:
        if not is_due_for_poll(batch_row, now=now):
            continue
        result = await collect_batch_results(
            batch_row,
            client=client,
            db_path=db_path,
            log_func=log_func,
        )
        results.append(result)
        if result.terminal:
            _accumulate_terminal_result(result, batch_row)

    if not batch_jobs_db.list_in_flight_batch_jobs(db_path=db_path):
        gate_prefs = await _emit_round_summary_if_ready(log_func=log_func)
        if gate_prefs is not None:
            await _auto_retry_failed_scraped_jobs(
                gate_prefs=gate_prefs,
                client=client,
                db_path=db_path,
                log_func=log_func,
            )
    return results


def seconds_until_next_poll(
    batch_rows: list[dict],
    *,
    now: datetime | None = None,
) -> int:
    """Seconds until the earliest in-flight batch is due for another poll."""
    now = now or datetime.now(UTC)
    if not batch_rows:
        return 0

    waits: list[int] = []
    for batch_row in batch_rows:
        submitted = _parse_iso(batch_row.get("submittedAt"))
        if submitted is None:
            waits.append(1)
            continue
        if submitted.tzinfo is None:
            submitted = submitted.replace(tzinfo=UTC)

        last_polled = _parse_iso(batch_row.get("lastPolledAt"))
        if last_polled and last_polled.tzinfo is None:
            last_polled = last_polled.replace(tzinfo=UTC)

        reference = last_polled or submitted
        age_seconds = max(0.0, (now - submitted).total_seconds())
        interval = poll_cadence_seconds(age_seconds)
        elapsed = (now - reference).total_seconds()
        waits.append(max(1, int(interval - elapsed)))
    return min(waits)


def _summarize_collect_results(
    results: list[CollectResult],
    *,
    db_path=None,
) -> dict:
    return {
        "batches_polled": len(results),
        "matched": sum(result.matched for result in results),
        "attribute_filtered": sum(result.attribute_filtered for result in results),
        "fallback_rejected": sum(result.fallback_rejected for result in results),
        "failed": sum(result.failed for result in results),
        "unclassified": sum(result.unclassified for result in results),
        "in_flight_remaining": len(
            batch_jobs_db.list_in_flight_batch_jobs(db_path=db_path)
        ),
    }


async def collect_in_flight_batches_once(
    *,
    client=None,
    db_path=None,
    log_func=None,
) -> dict:
    """One-shot poll of all in-flight batches; ignores poll cadence."""
    in_flight = batch_jobs_db.list_in_flight_batch_jobs(db_path=db_path)
    if not in_flight:
        reset_round_accumulator()
        return _summarize_collect_results([], db_path=db_path)

    results: list[CollectResult] = []
    for batch_row in in_flight:
        result = await collect_batch_results(
            batch_row,
            client=client,
            db_path=db_path,
            log_func=log_func,
        )
        results.append(result)
        if result.terminal:
            _accumulate_terminal_result(result, batch_row)

    if not batch_jobs_db.list_in_flight_batch_jobs(db_path=db_path):
        gate_prefs = await _emit_round_summary_if_ready(log_func=log_func)
        if gate_prefs is not None:
            await _auto_retry_failed_scraped_jobs(
                gate_prefs=gate_prefs,
                client=client,
                db_path=db_path,
                log_func=log_func,
            )
    return _summarize_collect_results(results, db_path=db_path)


async def wait_for_in_flight_collection(
    *,
    client=None,
    db_path=None,
    log_func=None,
) -> dict:
    """Poll on cadence until every in-flight batch reaches a terminal state."""
    results: list[CollectResult] = []
    while batch_jobs_db.list_in_flight_batch_jobs(db_path=db_path):
        results.extend(
            await poll_in_flight_batches(
                client=client,
                db_path=db_path,
                log_func=log_func,
            )
        )
        in_flight = batch_jobs_db.list_in_flight_batch_jobs(db_path=db_path)
        if not in_flight:
            break
        await asyncio.sleep(seconds_until_next_poll(in_flight))
    return _summarize_collect_results(results, db_path=db_path)


async def run_batch_collection(
    *,
    wait: bool = False,
    client=None,
    db_path=None,
    log_func=None,
) -> dict:
    """Headless batch result collection; may auto-submit poison retries when a round clears."""
    if wait:
        return await wait_for_in_flight_collection(
            client=client,
            db_path=db_path,
            log_func=log_func,
        )
    return await collect_in_flight_batches_once(
        client=client,
        db_path=db_path,
        log_func=log_func,
    )
