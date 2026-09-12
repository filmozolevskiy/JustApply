"""Canonical Job normalization — single owner for read-time migration and validation."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from ..schemas import ActivityLogEntry, Contact, Job, JobComment

COMMENT_BODY_MAX = 2000


def _nullable_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_activity_log(raw) -> list[ActivityLogEntry]:
    try:
        entries = json.loads(raw) if raw else []
    except Exception:
        return []
    return [ActivityLogEntry(**e) if isinstance(e, dict) else e for e in entries]


def activity_log_as_dicts(raw) -> list[dict]:
    """Parse activity log JSON into plain dicts for index/sync callers."""
    return [e.model_dump() for e in _parse_activity_log(raw)]


def _parse_job_comments(raw) -> list[JobComment]:
    try:
        entries = json.loads(raw) if raw else []
    except Exception:
        return []
    if not isinstance(entries, list):
        return []
    out: list[JobComment] = []
    for entry in entries:
        if isinstance(entry, JobComment):
            out.append(entry)
        elif isinstance(entry, dict) and entry.get("id") and entry.get("body") is not None:
            try:
                out.append(JobComment(**entry))
            except Exception:
                continue
    return out


def _legacy_blob_as_root_comment(blob: str, created_at: str) -> JobComment:
    """Wrap a pre-Comment-Thread notes blob as one root Job Comment."""
    return JobComment(
        id=f"c{uuid.uuid4().hex[:12]}",
        parentId=None,
        body=blob,
        createdAt=created_at,
        editedAt=None,
    )


def parse_job_row(row) -> Job:
    """Normalize a SQLite jobs row into the canonical Job model."""
    job = dict(row)
    for field in ("strengths", "gaps"):
        raw = job.get(field)
        try:
            job[field] = json.loads(raw) if raw else []
        except Exception:
            job[field] = []

    raw_contacts = job.get("contacts")
    try:
        contact_dicts = json.loads(raw_contacts) if raw_contacts else []
    except Exception:
        contact_dicts = []
    job["contacts"] = [Contact(**c) if isinstance(c, dict) else c for c in contact_dicts]

    job["activityLog"] = _parse_activity_log(job.get("activityLog"))
    job["shouldProceed"] = bool(job["shouldProceed"])
    job["isRecruiter"] = bool(job.get("isRecruiter", 0))
    job["unclassified"] = bool(job.get("unclassified", 0))
    job["roleFiltered"] = bool(job.get("roleFiltered", 0))
    job["roleFilteredReason"] = job.get("roleFilteredReason") or ""
    job["batchAttempts"] = int(job.get("batchAttempts") or 0)
    job["enrichmentNote"] = job.get("enrichmentNote") or ""
    job["enrichmentNoteKind"] = job.get("enrichmentNoteKind") or ""
    job["recruiterOutreachTemplate"] = job.get("recruiterOutreachTemplate") or ""
    job["russianSpeakerOutreachTemplate"] = job.get("russianSpeakerOutreachTemplate") or ""
    job["companyUrl"] = job.get("companyUrl") or ""
    job["archived"] = bool(job.get("archived", 0))
    job["rejectedAt"] = job.get("rejectedAt") or ""
    job["autoArchiveExempt"] = bool(job.get("autoArchiveExempt", 0))
    job["favorited"] = bool(job.get("favorited", 0))
    job["employmentType"] = job.get("employmentType") or ""
    job["annualMin"] = _nullable_int(job.get("annualMin"))
    job["annualMax"] = _nullable_int(job.get("annualMax"))
    raw_currency = job.get("annualCurrency")
    if raw_currency is None or raw_currency == "":
        job["annualCurrency"] = None
    else:
        job["annualCurrency"] = str(raw_currency).strip() or None

    raw_company_research = job.get("companyResearch")
    if raw_company_research in (None, ""):
        job["companyResearch"] = None
    elif isinstance(raw_company_research, dict):
        job["companyResearch"] = raw_company_research
    else:
        try:
            job["companyResearch"] = json.loads(str(raw_company_research))
        except Exception:
            job["companyResearch"] = None

    # Legacy migration: promote outreachMessage into recruiterOutreachTemplate on read.
    if not job["recruiterOutreachTemplate"] and job.get("outreachMessage"):
        job["recruiterOutreachTemplate"] = job["outreachMessage"]

    comments = _parse_job_comments(job.get("comments"))
    legacy_blob = (job.get("comment") or "").strip() if "comment" in job else ""
    if not comments and legacy_blob:
        comments = [_legacy_blob_as_root_comment(legacy_blob, datetime.now(UTC).isoformat())]
    job["comments"] = comments
    job.pop("comment", None)

    return Job(**job)


def coerce_job(job: Job | dict) -> Job:
    """Normalize dict or Job inputs to the canonical Job model."""
    if isinstance(job, Job):
        return job
    return Job.model_validate(job)


def normalize_add_job_input(job: dict) -> dict:
    """Map legacy spreadsheet aliases to canonical Job field names for writes."""
    return {
        "title": job.get("title") or job.get("Job title") or "",
        "company": job.get("company") or job.get("Company + Company size") or "",
        "link": job.get("link") or job.get("Posting link") or "",
        "date": job.get("date") or job.get("Posting date") or "",
        "location": job.get("location") or job.get("Location + Remote type (in office, hybrid, remote)") or "",
        "seniority": job.get("seniority") or job.get("Seniority type (junior, mid, senior)") or "",
        "employmentType": job.get("employmentType") or "",
        "salary": job.get("salary") or job.get("Salary type") or "",
        "description": job.get("description") or job.get("Short description") or "",
        "comments": job.get("comments") or [],
        "shouldProceed": bool(job.get("shouldProceed") or job.get("Should proceed?")),
        "size": job.get("size") or "",
        "remoteType": job.get("remoteType") or "",
        "matchScore": job.get("matchScore") or 0,
        "matchType": job.get("matchType") or "",
        "status": job.get("status") or "scraped",
        "resumeUsed": job.get("resumeUsed") or "",
        "strengths": job.get("strengths") or [],
        "gaps": job.get("gaps") or [],
        "contacts": job.get("contacts") or [],
        "outreachMessage": job.get("outreachMessage") or "",
        "isRecruiter": bool(job.get("isRecruiter")),
        "unclassified": bool(job.get("unclassified")),
        "roleFiltered": bool(job.get("roleFiltered")),
        "roleFilteredReason": job.get("roleFilteredReason") or "",
        "companyUrl": job.get("companyUrl") or "",
    }
