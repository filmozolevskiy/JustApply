import json
from datetime import UTC, datetime

from . import connection

TERMINAL_STATES = frozenset({
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
    "JOB_STATE_PARTIALLY_SUCCEEDED",
})


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_job_ids(raw) -> list[int]:
    try:
        parsed = json.loads(raw) if raw else []
    except Exception:
        return []
    return [int(jid) for jid in parsed]


def _row_to_dict(row) -> dict:
    data = dict(row)
    data["jobIds"] = _parse_job_ids(data.get("jobIds"))
    return data


def create_batch_job(
    *,
    batch_name: str,
    display_name: str,
    state: str,
    kind: str,
    job_ids: list[int],
    submitted_at: str | None = None,
    search_remote_types: list[str] | None = None,
    search_seniorities: str = "any",
    db_path=None,
) -> dict:
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    submitted_at = submitted_at or _now_iso()
    remote_types_json = json.dumps(search_remote_types) if search_remote_types is not None else None
    cursor.execute(
        """
        INSERT INTO batch_jobs (
            batchName, displayName, state, kind, submittedAt, lastPolledAt, resultFileName, jobIds,
            searchRemoteTypes, searchSeniorities
        ) VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)
        """,
        (
            batch_name,
            display_name,
            state,
            kind,
            submitted_at,
            json.dumps(job_ids),
            remote_types_json,
            search_seniorities,
        ),
    )
    batch_id = cursor.lastrowid
    conn.commit()
    cursor.execute("SELECT * FROM batch_jobs WHERE id = ?", (batch_id,))
    row = cursor.fetchone()
    conn.close()
    return _row_to_dict(row)


def get_batch_job(batch_id: int, db_path=None) -> dict | None:
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM batch_jobs WHERE id = ?", (batch_id,))
    row = cursor.fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def get_batch_job_by_name(batch_name: str, db_path=None) -> dict | None:
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM batch_jobs WHERE batchName = ?", (batch_name,))
    row = cursor.fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def update_batch_job(batch_id: int, fields: dict, db_path=None) -> dict | None:
    if db_path is None:
        db_path = connection.DB_PATH
    allowed = {
        "displayName", "state", "lastPolledAt", "resultFileName", "jobIds",
        "searchRemoteTypes", "searchSeniorities",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_batch_job(batch_id, db_path=db_path)

    if "jobIds" in updates:
        updates["jobIds"] = json.dumps(updates["jobIds"])
    if "searchRemoteTypes" in updates and isinstance(updates["searchRemoteTypes"], list):
        updates["searchRemoteTypes"] = json.dumps(updates["searchRemoteTypes"])

    set_clause = ", ".join(f"{column} = ?" for column in updates)
    values = list(updates.values()) + [batch_id]

    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE batch_jobs SET {set_clause} WHERE id = ?", values)
    conn.commit()
    cursor.execute("SELECT * FROM batch_jobs WHERE id = ?", (batch_id,))
    row = cursor.fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def list_batch_jobs(db_path=None) -> list[dict]:
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM batch_jobs ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [_row_to_dict(row) for row in rows]


def list_in_flight_batch_jobs(db_path=None) -> list[dict]:
    placeholders = ", ".join("?" for _ in TERMINAL_STATES)
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT * FROM batch_jobs WHERE state NOT IN ({placeholders}) ORDER BY id ASC",
        tuple(TERMINAL_STATES),
    )
    rows = cursor.fetchall()
    conn.close()
    return [_row_to_dict(row) for row in rows]


def get_in_flight_job_ids(db_path=None) -> set[int]:
    job_ids: set[int] = set()
    for batch in list_in_flight_batch_jobs(db_path=db_path):
        job_ids.update(batch.get("jobIds") or [])
    return job_ids
