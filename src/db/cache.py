"""Contact Sample Cache — per-company, per-stream store of raw Apify profiles."""
import json
import re
from datetime import UTC, datetime

from . import connection


def get_contact_sample(company_slug: str, stream: str = "", db_path=None) -> dict | None:
    """Return cached Contact Sample dict with profiles, fetched_at, display_name, pages_fetched, or None on miss."""
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT profiles, fetched_at, display_name, pages_fetched, last_fetch_empty "
        "FROM contact_sample_cache WHERE company_slug = ? AND stream = ?",
        (company_slug, stream),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    try:
        profiles = json.loads(row[0])
    except Exception:
        profiles = []
    pages_fetched = row[3] if row[3] is not None else 1
    last_fetch_empty = bool(row[4]) if len(row) > 4 and row[4] is not None else len(profiles) == 0
    return {
        "profiles": profiles,
        "fetched_at": row[1],
        "display_name": row[2] or "",
        "pages_fetched": pages_fetched,
        "last_fetch_empty": last_fetch_empty,
    }


def set_contact_sample(
    company_slug: str,
    profiles: list,
    display_name: str = "",
    pages_fetched: int = 1,
    stream: str = "",
    last_fetch_empty: bool | None = None,
    db_path=None,
) -> None:
    """Write raw Contact Sample profiles to cache, including empty lists from successful Apify runs."""
    if last_fetch_empty is None:
        last_fetch_empty = len(profiles) == 0
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO contact_sample_cache "
        "(company_slug, stream, profiles, fetched_at, display_name, pages_fetched, last_fetch_empty) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            company_slug, stream, json.dumps(profiles),
            datetime.now(UTC).isoformat(), display_name, pages_fetched,
            1 if last_fetch_empty else 0,
        ),
    )
    conn.commit()
    conn.close()


def _normalize_profile_url(profile: dict) -> str:
    """Return canonical /in/{slug} from any LinkedIn profile URL in an Apify profile dict."""
    url = (
        profile.get("linkedinUrl") or
        profile.get("linkedInUrl") or
        profile.get("profileUrl") or
        profile.get("url") or
        ""
    )
    if not url:
        return ""
    match = re.search(r'/in/([^/?#]+)', url)
    return f"/in/{match.group(1)}" if match else ""


def append_contact_sample(company_slug: str, new_profiles: list, stream: str = "", db_path=None) -> None:
    """Append new profiles to cache (deduped by LinkedIn URL) and increment pages_fetched."""
    existing = get_contact_sample(company_slug, stream=stream, db_path=db_path)
    if not existing:
        set_contact_sample(company_slug, new_profiles, pages_fetched=1, stream=stream, db_path=db_path)
        return

    existing_profiles = existing["profiles"]
    pages_fetched = existing.get("pages_fetched", 1)
    display_name = existing.get("display_name", "")

    existing_urls = set()
    for p in existing_profiles:
        normalized = _normalize_profile_url(p)
        if normalized:
            existing_urls.add(normalized)

    combined = list(existing_profiles)
    for p in new_profiles:
        normalized = _normalize_profile_url(p)
        if not normalized or normalized not in existing_urls:
            combined.append(p)
            if normalized:
                existing_urls.add(normalized)

    set_contact_sample(
        company_slug,
        combined,
        display_name=display_name,
        pages_fetched=pages_fetched + 1,
        stream=stream,
        last_fetch_empty=len(new_profiles) == 0,
        db_path=db_path,
    )


def delete_contact_sample(company_slug: str, stream: str = "", db_path=None) -> None:
    """Delete the Contact Sample Cache entry for a company and stream."""
    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM contact_sample_cache WHERE company_slug = ? AND stream = ?",
        (company_slug, stream),
    )
    conn.commit()
    conn.close()
