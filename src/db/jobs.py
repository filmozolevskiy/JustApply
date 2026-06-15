import json
from datetime import datetime, timezone

from . import connection

VALID_STATUSES = frozenset({
    "sourced", "enriching", "enriched", "evaluating",
    "contacted", "applied", "interviewing", "rejected",
})

ACTIVITY_LOG_MAX = 50


def _format_lane(status: str) -> str:
    return status.replace("_", " ").title()


def _parse_activity_log(raw) -> list:
    try:
        return json.loads(raw) if raw else []
    except Exception:
        return []


def _append_activity_log(cursor, job_id: int, message: str) -> None:
    cursor.execute("SELECT activityLog FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    if not row:
        return
    log = _parse_activity_log(row[0])
    log.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "message": message,
    })
    if len(log) > ACTIVITY_LOG_MAX:
        log = log[-ACTIVITY_LOG_MAX:]
    cursor.execute(
        "UPDATE jobs SET activityLog = ? WHERE id = ?",
        (json.dumps(log), job_id),
    )


def _parse_job_row(row) -> dict:
    job = dict(row)
    for field in ("strengths", "gaps", "contacts"):
        raw = job.get(field)
        try:
            job[field] = json.loads(raw) if raw else []
        except Exception:
            job[field] = []
    job["activityLog"] = _parse_activity_log(job.get("activityLog"))
    job["shouldProceed"] = bool(job["shouldProceed"])
    job["isRecruiter"] = bool(job.get("isRecruiter", 0))
    job["enrichmentNote"] = job.get("enrichmentNote") or ""
    job["recruiterOutreachTemplate"] = job.get("recruiterOutreachTemplate") or ""
    job["russianSpeakerOutreachTemplate"] = job.get("russianSpeakerOutreachTemplate") or ""
    job["companyUrl"] = job.get("companyUrl") or ""
    # Legacy migration: promote outreachMessage into recruiterOutreachTemplate on read
    if not job["recruiterOutreachTemplate"] and job.get("outreachMessage"):
        job["recruiterOutreachTemplate"] = job["outreachMessage"]
    return job


def get_jobs(db_path=None):
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [_parse_job_row(r) for r in rows]


def update_job_status(job_id, status, db_path=None):
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status {status!r}. Valid values: {sorted(VALID_STATUSES)}")
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM jobs WHERE id = ?", (job_id,))
    old_row = cursor.fetchone()
    if not old_row:
        conn.close()
        return None
    old_status = old_row[0]
    cursor.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
    if old_status != status:
        if status == "enriching":
            _append_activity_log(cursor, job_id, "Enrichment started")
        else:
            _append_activity_log(
                cursor,
                job_id,
                f"Moved {_format_lane(old_status)} → {_format_lane(status)}",
            )
    conn.commit()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return _parse_job_row(row)


def update_job_comment(job_id, comment, db_path=None):
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET comment = ? WHERE id = ?", (comment, job_id))
    conn.commit()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return _parse_job_row(row)


def update_contact_status(job_id, contact_idx, contacted, db_path=None):
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    job = dict(row)
    try:
        contacts = json.loads(job.get("contacts") or "[]")
    except Exception:
        contacts = []

    if contact_idx < 0 or contact_idx >= len(contacts):
        conn.close()
        return None

    contacts[contact_idx]["contacted"] = bool(contacted)

    if contacted:
        contact_name = contacts[contact_idx].get("name") or "Contact"
        _append_activity_log(cursor, job_id, f"Marked {contact_name} contacted")

    cursor.execute(
        "UPDATE jobs SET contacts = ? WHERE id = ?",
        (json.dumps(contacts), job_id),
    )
    conn.commit()

    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    updated = cursor.fetchone()
    conn.close()
    return _parse_job_row(updated)


def get_job(job_id, db_path=None):
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return _parse_job_row(row)


def start_enrichment(job_id, db_path=None):
    return update_job_status(job_id, "enriching", db_path)


def enrich_job(
    job_id,
    contacts,
    outreach_message,
    enrichment_note="",
    recruiter_template="",
    russian_speaker_template="",
    db_path=None,
):
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM jobs WHERE id = ?", (job_id,))
    if not cursor.fetchone():
        conn.close()
        return None
    cursor.execute(
        "UPDATE jobs SET contacts = ?, outreachMessage = ?, status = 'enriched', "
        "enrichmentNote = ?, recruiterOutreachTemplate = ?, russianSpeakerOutreachTemplate = ? "
        "WHERE id = ?",
        (json.dumps(contacts), outreach_message, enrichment_note,
         recruiter_template, russian_speaker_template, job_id),
    )
    if enrichment_note:
        _append_activity_log(cursor, job_id, f"Enrichment failed · {enrichment_note}")
    else:
        count = len(contacts)
        label = "contact" if count == 1 else "contacts"
        _append_activity_log(cursor, job_id, f"Enriched · {count} {label}")
    conn.commit()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    return _parse_job_row(row) if row else None


def log_activity(job_id: int, message: str, db_path=None) -> None:
    """Append a message to the job's Job Activity Log."""
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    _append_activity_log(cursor, job_id, message)
    conn.commit()
    conn.close()


def update_outreach_template(job_id, audience, template, db_path=None):
    if audience == "recruiter":
        column = "recruiterOutreachTemplate"
    elif audience == "russian_speaker":
        column = "russianSpeakerOutreachTemplate"
    else:
        raise ValueError(f"Invalid audience {audience!r}")
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM jobs WHERE id = ?", (job_id,))
    if not cursor.fetchone():
        conn.close()
        return None
    cursor.execute(f"UPDATE jobs SET {column} = ? WHERE id = ?", (template, job_id))
    conn.commit()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    return _parse_job_row(row) if row else None


def job_exists(title, company, link=None, db_path=None):
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    if link:
        cursor.execute("SELECT id FROM jobs WHERE link = ?", (link,))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            return True
    cursor.execute("SELECT id FROM jobs WHERE title = ? AND company = ?", (title, company))
    existing = cursor.fetchone()
    conn.close()
    return existing is not None


def add_job(job, db_path=None):
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()

    title = job.get("title") or job.get("Job title") or ""
    company = job.get("company") or job.get("Company + Company size") or ""
    link = job.get("link") or job.get("Posting link") or ""

    if not title.strip() and not company.strip():
        conn.close()
        return None

    if link:
        cursor.execute("SELECT id FROM jobs WHERE link = ?", (link,))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            return existing[0]

    cursor.execute("SELECT id FROM jobs WHERE title = ? AND company = ?", (title, company))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return existing[0]

    cursor.execute("""
        INSERT INTO jobs (
            title, company, size, link, date, location, remoteType, seniority, salary,
            description, matchScore, matchType, shouldProceed, status, resumeUsed,
            strengths, gaps, contacts, outreachMessage, comment, isRecruiter, companyUrl
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """, (
        title,
        company,
        job.get("size") or "",
        link,
        job.get("date") or job.get("Posting date") or "",
        job.get("location") or job.get("Location + Remote type (in office, hybrid, remote)") or "",
        job.get("remoteType") or "",
        job.get("seniority") or job.get("Seniority type (junior, mid, senior)") or "",
        job.get("salary") or job.get("Salary type") or "",
        job.get("description") or job.get("Short description") or "",
        job.get("matchScore") or 0,
        job.get("matchType") or "",
        1 if job.get("shouldProceed") or job.get("Should proceed?") else 0,
        job.get("status") or "sourced",
        job.get("resumeUsed") or "",
        json.dumps(job.get("strengths") or []),
        json.dumps(job.get("gaps") or []),
        json.dumps(job.get("contacts") or []),
        job.get("outreachMessage") or "",
        job.get("comment") or job.get("Comment") or "",
        1 if job.get("isRecruiter") else 0,
        job.get("companyUrl") or "",
    ))
    new_id = cursor.lastrowid
    _append_activity_log(cursor, new_id, "Sourced")
    conn.commit()
    conn.close()
    return new_id
