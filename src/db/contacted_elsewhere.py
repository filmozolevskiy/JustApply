"""Contacted Elsewhere — cross-job outreach warning for duplicate LinkedIn profiles."""

from __future__ import annotations

from ..core.enrichment.contact_sample import normalize_linkedin_url
from ..schemas import Contact, Job
from .connection import DB_PATH, get_db_connection
from .job_model import parse_job_row


def _load_all_jobs(db_path=None) -> list[Job]:
    if db_path is None:
        db_path = DB_PATH
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [parse_job_row(r) for r in rows]


def _contact_profile_url(contact: Contact | dict) -> str:
    if isinstance(contact, Contact):
        return contact.url or contact.linkedin or ""
    return contact.get("url") or contact.get("linkedin") or ""


def _activity_log_entries(job: Job) -> list[dict]:
    entries = []
    for entry in job.activityLog or []:
        if hasattr(entry, "model_dump"):
            entries.append(entry.model_dump())
        elif isinstance(entry, dict):
            entries.append(entry)
    return entries


def contacted_timestamp(contact: Contact | dict, activity_log: list[dict]) -> str:
    """Return ISO timestamp for when this contact was marked contacted on a job."""
    if isinstance(contact, Contact):
        raw = contact.model_dump()
    else:
        raw = contact
    contacted_at = raw.get("contacted_at") or ""
    if contacted_at:
        return contacted_at

    name = raw.get("name") or "Contact"
    marker = f"Marked {name} contacted"
    for entry in reversed(activity_log):
        if entry.get("message") == marker:
            return entry.get("ts") or ""
    return ""


def build_contacted_index(jobs: list[Job]) -> dict[str, list[dict]]:
    """Map normalized LinkedIn slug -> contacted occurrences on jobs."""
    index: dict[str, list[dict]] = {}
    for job in jobs:
        activity_log = _activity_log_entries(job)
        for contact in job.contacts or []:
            if isinstance(contact, Contact):
                raw = contact.model_dump()
            else:
                raw = contact
            if not raw.get("contacted"):
                continue
            slug = normalize_linkedin_url(_contact_profile_url(raw))
            if not slug:
                continue
            index.setdefault(slug, []).append(
                {
                    "jobId": job.id,
                    "company": job.company,
                    "title": job.title,
                    "contactedAt": contacted_timestamp(raw, activity_log),
                }
            )
    return index


def _pick_most_recent(matches: list[dict]) -> dict | None:
    if not matches:
        return None
    return max(matches, key=lambda item: (item.get("contactedAt") or "", item.get("jobId") or 0))


def contacted_elsewhere_for_contact(
    job_id: int,
    contact: Contact | dict,
    index: dict[str, list[dict]],
) -> dict | None:
    """Return {jobId, company, title} when this contact was contacted on another job."""
    if isinstance(contact, Contact):
        raw = contact.model_dump()
    else:
        raw = contact
    if raw.get("contacted"):
        return None

    slug = normalize_linkedin_url(_contact_profile_url(raw))
    if not slug:
        return None

    matches = [entry for entry in index.get(slug, []) if entry.get("jobId") != job_id]
    best = _pick_most_recent(matches)
    if not best:
        return None
    return {
        "jobId": best["jobId"],
        "company": best["company"],
        "title": best["title"],
    }


def enrich_jobs_with_contacted_elsewhere(jobs: list[Job], db_path=None) -> list[Job]:
    """Attach contactedElsewhere metadata to each contact on the given jobs."""
    if not jobs:
        return jobs

    all_jobs = _load_all_jobs(db_path=db_path)
    index = build_contacted_index(all_jobs)

    enriched: list[Job] = []
    for job in jobs:
        if job.id is None:
            enriched.append(job)
            continue
        updated_contacts = []
        for contact in job.contacts or []:
            payload = contact.model_dump() if isinstance(contact, Contact) else dict(contact)
            elsewhere = contacted_elsewhere_for_contact(job.id, payload, index)
            if elsewhere:
                payload["contactedElsewhere"] = elsewhere
            else:
                payload.pop("contactedElsewhere", None)
            updated_contacts.append(Contact(**payload))
        enriched.append(job.model_copy(update={"contacts": updated_contacts}))
    return enriched
