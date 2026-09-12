"""Role Relevance parse/pass: reject only on a clear JSON false."""


def parse_role_relevant(payload: dict) -> tuple[bool | None, str]:
    if not isinstance(payload, dict):
        return None, "not an object"
    if "roleRelevant" not in payload:
        return None, "omitted"
    value = payload["roleRelevant"]
    if value is True or value is False or value is None:
        return value, "ok"
    return None, f"unexpected {value!r} (treated as unsure)"


def passes_role_relevance(role_relevant: bool | None) -> bool:
    return role_relevant is not False


def has_role_relevance_query(search_query: str | None) -> bool:
    return bool((search_query or "").strip())


def role_filtered_reason(search_query: str, listing_title: str) -> str:
    query = (search_query or "").strip() or "(blank)"
    title = (listing_title or "").strip() or "(no title)"
    return f"Searched {query} vs {title}"
