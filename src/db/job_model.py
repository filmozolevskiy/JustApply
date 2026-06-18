"""Canonical Job normalization — single owner for read-time migration and validation."""

from __future__ import annotations

import json

from ..schemas import ActivityLogEntry, Contact, Job


def _parse_activity_log(raw) -> list[ActivityLogEntry]:
    try:
        entries = json.loads(raw) if raw else []
    except Exception:
        return []
    return [ActivityLogEntry(**e) if isinstance(e, dict) else e for e in entries]


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
    job["enrichmentNote"] = job.get("enrichmentNote") or ""
    job["enrichmentNoteKind"] = job.get("enrichmentNoteKind") or ""
    job["recruiterOutreachTemplate"] = job.get("recruiterOutreachTemplate") or ""
    job["russianSpeakerOutreachTemplate"] = job.get("russianSpeakerOutreachTemplate") or ""
    job["companyUrl"] = job.get("companyUrl") or ""
    job["archived"] = bool(job.get("archived", 0))
    job["rejectedAt"] = job.get("rejectedAt") or ""
    job["autoArchiveExempt"] = bool(job.get("autoArchiveExempt", 0))

    # Legacy migration: promote outreachMessage into recruiterOutreachTemplate on read.
    if not job["recruiterOutreachTemplate"] and job.get("outreachMessage"):
        job["recruiterOutreachTemplate"] = job["outreachMessage"]

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
        "salary": job.get("salary") or job.get("Salary type") or "",
        "description": job.get("description") or job.get("Short description") or "",
        "comment": job.get("comment") or job.get("Comment") or "",
        "shouldProceed": bool(job.get("shouldProceed") or job.get("Should proceed?")),
        "size": job.get("size") or "",
        "remoteType": job.get("remoteType") or "",
        "matchScore": job.get("matchScore") or 0,
        "matchType": job.get("matchType") or "",
        "status": job.get("status") or "found",
        "resumeUsed": job.get("resumeUsed") or "",
        "strengths": job.get("strengths") or [],
        "gaps": job.get("gaps") or [],
        "contacts": job.get("contacts") or [],
        "outreachMessage": job.get("outreachMessage") or "",
        "isRecruiter": bool(job.get("isRecruiter")),
        "companyUrl": job.get("companyUrl") or "",
    }
