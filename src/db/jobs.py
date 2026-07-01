import json
from datetime import UTC, datetime

from . import connection
from .contacted_elsewhere import enrich_jobs_with_contacted_elsewhere
from .job_model import normalize_add_job_input, parse_job_row

VALID_STATUSES = frozenset({
    "scraped", "matched", "accepted",
    "applied", "interviewing", "rejected",
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
        "ts": datetime.now(UTC).isoformat(),
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


def enrich_job_record(job, db_path=None):
    """Attach Contacted Elsewhere metadata to a single Job for API responses."""
    if job is None:
        return None
    enriched = enrich_jobs_with_contacted_elsewhere([job], db_path=db_path)
    return enriched[0] if enriched else None


def parse_job_row_enriched(row, db_path=None):
    """Parse a SQLite row and attach Contacted Elsewhere metadata."""
    if row is None:
        return None
    return enrich_job_record(parse_job_row(row), db_path=db_path)


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
    jobs = [parse_job_row(r) for r in rows]
    return enrich_jobs_with_contacted_elsewhere(jobs, db_path=db_path)


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
    return parse_job_row_enriched(row, db_path=db_path)


def update_job_comment(job_id, comment, db_path=None):
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM jobs WHERE id = ?", (job_id,))
    if not cursor.fetchone():
        conn.close()
        return None
    cursor.execute("UPDATE jobs SET comment = ? WHERE id = ?", (comment, job_id))
    _append_activity_log(cursor, job_id, "Notes updated")
    conn.commit()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return parse_job_row_enriched(row, db_path=db_path)


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
        contacts[contact_idx]["contacted_at"] = datetime.now(UTC).isoformat()
        contact_name = contacts[contact_idx].get("name") or "Contact"
        _append_activity_log(cursor, job_id, f"Marked {contact_name} contacted")
    else:
        contacts[contact_idx].pop("contacted_at", None)

    cursor.execute(
        "UPDATE jobs SET contacts = ? WHERE id = ?",
        (json.dumps(contacts), job_id),
    )
    conn.commit()

    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    updated = cursor.fetchone()
    conn.close()
    return parse_job_row_enriched(updated, db_path=db_path)


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
    return parse_job_row_enriched(row, db_path=db_path)


def enrich_job(
    job_id,
    contacts,
    outreach_message,
    enrichment_note="",
    enrichment_note_kind="",
    recruiter_template="",
    russian_speaker_template="",
    activity_kind="enrich",
    new_profile_count=None,
    keep_contacts=False,
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
    # Capture explicit caller intent before auto-inference (distinguishes partial-success warning
    # from a real failure note that auto-infers to "warning").
    is_partial_success = (enrichment_note_kind == "warning")
    # Auto-infer kind: warning when note is set (unless explicitly provided), clear otherwise.
    if not enrichment_note_kind:
        enrichment_note_kind = "warning" if enrichment_note else ""
    if keep_contacts:
        cursor.execute(
            "UPDATE jobs SET outreachMessage = ?, status = 'accepted', "
            "enrichmentNote = ?, enrichmentNoteKind = ?, recruiterOutreachTemplate = ?, russianSpeakerOutreachTemplate = ? "
            "WHERE id = ?",
            (outreach_message, enrichment_note, enrichment_note_kind,
             recruiter_template, russian_speaker_template, job_id),
        )
    else:
        cursor.execute(
            "UPDATE jobs SET contacts = ?, outreachMessage = ?, status = 'accepted', "
            "enrichmentNote = ?, enrichmentNoteKind = ?, recruiterOutreachTemplate = ?, russianSpeakerOutreachTemplate = ? "
            "WHERE id = ?",
            (json.dumps(contacts), outreach_message, enrichment_note, enrichment_note_kind,
             recruiter_template, russian_speaker_template, job_id),
        )
    if activity_kind == "reclassify_no_cache":
        note_text = enrichment_note or "templates refreshed"
        _append_activity_log(cursor, job_id, f"Re-classified · {note_text}")
    elif enrichment_note and not is_partial_success:
        _append_activity_log(cursor, job_id, f"Enrichment failed · {enrichment_note}")
    elif activity_kind == "reclassify":
        count = len(contacts)
        label = "contact" if count == 1 else "contacts"
        _append_activity_log(cursor, job_id, f"Re-classified · {count} {label}")
    elif activity_kind == "load_more":
        count = len(contacts)
        label = "contact" if count == 1 else "contacts"
        new_count = new_profile_count if new_profile_count is not None else 0
        new_label = "profile" if new_count == 1 else "profiles"
        _append_activity_log(
            cursor,
            job_id,
            f"Load more contacts · {count} {label} ({new_count} new {new_label})",
        )
    else:
        count = len(contacts)
        label = "contact" if count == 1 else "contacts"
        _append_activity_log(cursor, job_id, f"Enriched · {count} {label}")
    conn.commit()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    return parse_job_row_enriched(row, db_path=db_path)


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
    _append_activity_log(cursor, job_id, "Outreach template updated")
    conn.commit()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    return parse_job_row_enriched(row, db_path=db_path)


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
    return parse_job_row_enriched(updated, db_path=db_path)


def get_unevaluated_jobs(db_path=None):
    """Return all jobs (any status, any archive state) where matchType is empty."""
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM jobs WHERE matchType = '' OR matchType IS NULL ORDER BY id ASC"
    )
    rows = cursor.fetchall()
    conn.close()
    return [parse_job_row(r) for r in rows]


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
            strengths, gaps, contacts, outreachMessage, comment, isRecruiter, companyUrl,
            unclassified
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
        1 if fields["unclassified"] else 0,
    ))
    new_id = cursor.lastrowid
    _append_activity_log(cursor, new_id, "Found")
    conn.commit()
    conn.close()
    return new_id


def update_job_evaluation(job_id: int, fields: dict, db_path=None):
    """Update Resume Matcher fields on an existing job."""
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT matchScore, resumeUsed FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    old_score = row[0] or 0
    old_resume = row[1] or ""

    resume_used = fields.get("resumeUsed", old_resume)
    new_score = fields.get("matchScore", old_score)
    cursor.execute("""
        UPDATE jobs SET
            matchScore = ?,
            matchType = ?,
            shouldProceed = ?,
            resumeUsed = ?,
            strengths = ?,
            gaps = ?,
            description = ?,
            isRecruiter = ?,
            salary = ?,
            remoteType = ?,
            seniority = ?,
            unclassified = ?
        WHERE id = ?
    """, (
        fields.get("matchScore", 0),
        fields.get("matchType", ""),
        1 if fields.get("shouldProceed") else 0,
        resume_used,
        json.dumps(fields.get("strengths") or []),
        json.dumps(fields.get("gaps") or []),
        fields.get("description") or "",
        1 if fields.get("isRecruiter") else 0,
        fields.get("salary") or "",
        fields.get("remoteType") or "",
        fields.get("seniority") or "",
        1 if fields.get("unclassified") else 0,
        job_id,
    ))
    _append_activity_log(
        cursor,
        job_id,
        f"Re-assessed with {resume_used}: score {old_score} → {new_score}",
    )
    conn.commit()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    updated = cursor.fetchone()
    conn.close()
    return parse_job_row_enriched(updated, db_path=db_path)


def increment_batch_attempts(job_id: int, db_path=None) -> int:
    """Increment poison-job counter; returns the new attempt count."""
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE jobs SET batchAttempts = COALESCE(batchAttempts, 0) + 1 WHERE id = ?",
        (job_id,),
    )
    cursor.execute("SELECT batchAttempts FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.commit()
    conn.close()
    return int(row[0]) if row else 0
