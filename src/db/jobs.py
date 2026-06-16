import json
from datetime import datetime, timezone

from . import connection
from .job_model import normalize_add_job_input, parse_job_row

VALID_STATUSES = frozenset({
    "found", "accepted",
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


def _auto_archive_stale_jobs(cursor) -> int:
    """Archive rejected jobs whose rejectedAt is 14+ days ago and are not exempt."""
    cursor.execute(
        "SELECT id FROM jobs WHERE status = 'rejected' AND archived = 0 "
        "AND autoArchiveExempt = 0 AND rejectedAt != '' "
        "AND rejectedAt <= datetime('now', '-14 days')"
    )
    stale_ids = [row[0] for row in cursor.fetchall()]
    for job_id in stale_ids:
        cursor.execute("UPDATE jobs SET archived = 1 WHERE id = ?", (job_id,))
        _append_activity_log(cursor, job_id, "Auto-archived (rejected 14+ days)")
    return len(stale_ids)


def archive_stale_rejected_jobs(db_path=None) -> int:
    """Explicit maintenance sweep for stale rejected jobs. Returns archived count."""
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    archived_count = _auto_archive_stale_jobs(cursor)
    conn.commit()
    conn.close()
    return archived_count


def get_jobs(db_path=None, archived_filter="active"):
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    if archived_filter == "archived":
        cursor.execute("SELECT * FROM jobs WHERE archived = 1 ORDER BY id DESC")
    elif archived_filter == "all":
        cursor.execute("SELECT * FROM jobs ORDER BY id DESC")
    else:
        cursor.execute("SELECT * FROM jobs WHERE archived = 0 ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [parse_job_row(r) for r in rows]


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
    if status == "rejected":
        cursor.execute(
            "UPDATE jobs SET status = ?, rejectedAt = CASE WHEN (rejectedAt IS NULL OR rejectedAt = '') THEN datetime('now') ELSE rejectedAt END WHERE id = ?",
            (status, job_id),
        )
    else:
        cursor.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
    if old_status != status:
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
    return parse_job_row(row)


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
    return parse_job_row(row)


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
    return parse_job_row(updated)


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
    return parse_job_row(row)


def start_enrichment(job_id, db_path=None):
    return update_job_status(job_id, "accepted", db_path)


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
        "UPDATE jobs SET contacts = ?, outreachMessage = ?, status = 'accepted', "
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
    return parse_job_row(row) if row else None


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
    return parse_job_row(row) if row else None


def archive_job(job_id: int, db_path=None):
    """Toggle archive state on a job.
    - Archived → un-archive: sets archived=0, autoArchiveExempt=1
    - Rejected non-archived → archive: sets archived=1
    - Non-rejected non-archived → returns None (invalid)
    """
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT status, archived FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    _status, current_archived = row
    if current_archived:
        cursor.execute(
            "UPDATE jobs SET archived = 0, autoArchiveExempt = 1 WHERE id = ?",
            (job_id,),
        )
        _append_activity_log(cursor, job_id, "Un-archived (auto-archive exempted)")
    else:
        if _status != "rejected":
            conn.close()
            return None
        cursor.execute("UPDATE jobs SET archived = 1 WHERE id = ?", (job_id,))
        _append_activity_log(cursor, job_id, "Archived")
    conn.commit()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    updated = cursor.fetchone()
    conn.close()
    return parse_job_row(updated) if updated else None


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

    fields = normalize_add_job_input(job)
    title = fields["title"]
    company = fields["company"]
    link = fields["link"]

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
        fields["size"],
        link,
        fields["date"],
        fields["location"],
        fields["remoteType"],
        fields["seniority"],
        fields["salary"],
        fields["description"],
        fields["matchScore"],
        fields["matchType"],
        1 if fields["shouldProceed"] else 0,
        fields["status"],
        fields["resumeUsed"],
        json.dumps(fields["strengths"]),
        json.dumps(fields["gaps"]),
        json.dumps(fields["contacts"]),
        fields["outreachMessage"],
        fields["comment"],
        1 if fields["isRecruiter"] else 0,
        fields["companyUrl"],
    ))
    new_id = cursor.lastrowid
    _append_activity_log(cursor, new_id, "Found")
    conn.commit()
    conn.close()
    return new_id
