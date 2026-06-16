"""Contact Sample Cache — per-company store of raw Apify profiles."""
import json
from datetime import datetime, timezone

from . import connection


def get_contact_sample(company_slug: str, db_path=None) -> dict | None:
    """Return cached Contact Sample dict with profiles, fetched_at, display_name, or None on miss."""
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT profiles, fetched_at, display_name FROM contact_sample_cache WHERE company_slug = ?",
        (company_slug,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    try:
        profiles = json.loads(row[0])
    except Exception:
        profiles = []
    return {"profiles": profiles, "fetched_at": row[1], "display_name": row[2] or ""}


def set_contact_sample(company_slug: str, profiles: list, display_name: str = "", db_path=None) -> None:
    """Write raw Contact Sample profiles to cache, including empty lists from successful Apify runs."""
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO contact_sample_cache "
        "(company_slug, profiles, fetched_at, display_name) VALUES (?, ?, ?, ?)",
        (company_slug, json.dumps(profiles), datetime.now(timezone.utc).isoformat(), display_name),
    )
    conn.commit()
    conn.close()


def delete_contact_sample(company_slug: str, db_path=None) -> None:
    """Delete the Contact Sample Cache entry for a company (used by Refresh Contacts)."""
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM contact_sample_cache WHERE company_slug = ?", (company_slug,))
    conn.commit()
    conn.close()
