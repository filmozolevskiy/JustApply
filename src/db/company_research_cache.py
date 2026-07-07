"""Company Research Cache — employer-wide Glassdoor intel keyed by normalized company name."""
import json
from datetime import UTC, datetime


def normalize_company_name(company: str) -> str:
    """Return cache key for an employer display name."""
    return " ".join(company.strip().lower().split())


def normalize_glassdoor_job_title(title: str) -> str:
    """Return title key for salary/interview maps."""
    return " ".join(title.strip().lower().split())


def get_company_research_cache(company_key: str, db_path=None) -> dict | None:
    from . import connection

    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT glassdoor_company_id, matched_name, company_size, rating, review_count, "
        "recommend_percent, salaries_by_title, interviews_by_title, fetched_at "
        "FROM company_research_cache WHERE company_key = ?",
        (company_key,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    try:
        salaries = json.loads(row[6] or "{}")
    except Exception:
        salaries = {}
    try:
        interviews = json.loads(row[7] or "{}")
    except Exception:
        interviews = {}
    return {
        "glassdoorCompanyId": row[0] or "",
        "matchedName": row[1] or "",
        "companySize": row[2] or "",
        "rating": row[3],
        "reviewCount": row[4],
        "recommendPercent": row[5],
        "salariesByTitle": salaries,
        "interviewsByTitle": interviews,
        "fetchedAt": row[8] or "",
    }


def set_company_research_cache(company_key: str, data: dict, db_path=None) -> None:
    from . import connection

    if db_path is None:
        db_path = connection.DB_PATH
    existing = get_company_research_cache(company_key, db_path=db_path) or {
        "glassdoorCompanyId": "",
        "matchedName": "",
        "companySize": "",
        "rating": None,
        "reviewCount": None,
        "recommendPercent": None,
        "salariesByTitle": {},
        "interviewsByTitle": {},
        "fetchedAt": "",
    }
    merged = {**existing, **data}
    salaries = merged.get("salariesByTitle") or {}
    interviews = merged.get("interviewsByTitle") or {}
    fetched_at = merged.get("fetchedAt") or datetime.now(UTC).isoformat()
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO company_research_cache "
        "(company_key, glassdoor_company_id, matched_name, company_size, rating, "
        "review_count, recommend_percent, salaries_by_title, interviews_by_title, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            company_key,
            merged.get("glassdoorCompanyId") or "",
            merged.get("matchedName") or "",
            merged.get("companySize") or "",
            merged.get("rating"),
            merged.get("reviewCount"),
            merged.get("recommendPercent"),
            json.dumps(salaries),
            json.dumps(interviews),
            fetched_at,
        ),
    )
    conn.commit()
    conn.close()


def delete_company_research_cache(company_key: str, db_path=None) -> None:
    from . import connection

    if db_path is None:
        db_path = connection.DB_PATH
    conn = connection.get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM company_research_cache WHERE company_key = ?", (company_key,))
    conn.commit()
    conn.close()
