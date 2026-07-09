"""Tests for Glassdoor core module — mocked Apify boundary."""

from src.core.company_research.glassdoor_intel import (
    _pick_company_match,
    _summarize_interviews,
    build_job_company_research_snapshot,
    format_activity_log_message,
    format_repick_activity_log_message,
    format_search_candidates,
    normalize_salary_row,
    parse_overview_row,
)

FLIGHTHUB_SEARCH = [{"companyId": "882104", "companyName": "FlightHub", "shortName": "FlightHub"}]
QUALITEST_SEARCH = [
    {"companyId": "111", "companyName": "QualiTest Group", "shortName": "qualitest-group"},
    {"companyId": "222", "companyName": "Qualitest Global", "shortName": "qualitest-global"},
]
FLIGHTHUB_OVERVIEW = [
    {
        "size": "51 to 200 Employees",
        "rating": 2.8,
        "reviewCount": 246,
        "recommendToFriendPercent": 40,
    }
]

def test_pick_company_match_exact():
    match = _pick_company_match("FlightHub", FLIGHTHUB_SEARCH)
    assert match["companyId"] == "882104"

def test_pick_company_match_linkedin_slug_tie_break():
    match = _pick_company_match(
        "Qualitest",
        QUALITEST_SEARCH,
        linkedin_slug="qualitest-group",
    )
    assert match["companyId"] == "111"

def test_parse_overview_row_flighthub():
    overview = parse_overview_row(FLIGHTHUB_OVERVIEW)
    assert overview["companySize"] == "51 to 200 Employees"
    assert overview["rating"] == 2.8
    assert overview["reviewCount"] == 246
    assert overview["recommendPercent"] == 40.0

def test_summarize_interviews_caps_at_three():
    rows = [
        {
            "jobTitle": "QA Engineer",
            "processDescription": f"Step {i}",
            "difficulty": "Average",
            "outcome": "Accepted",
        }
        for i in range(5)
    ]
    summaries = _summarize_interviews(rows, "QA Engineer")
    assert len(summaries) == 3

def test_build_job_snapshot_shape():
    snapshot = build_job_company_research_snapshot(
        glassdoor_company_id="882104",
        matched_name="FlightHub",
        overview=parse_overview_row(FLIGHTHUB_OVERVIEW),
        glassdoor_job_title="QA Engineer",
        salary=None,
        interviews=[],
    )
    assert snapshot["glassdoorCompanyId"] == "882104"
    assert snapshot["matchedName"] == "FlightHub"
    assert snapshot["glassdoorJobTitle"] == "QA Engineer"
    assert snapshot["salary"] is None
    assert snapshot["interviews"] == []
    assert snapshot["fetchedAt"]

def test_normalize_salary_row():
    row = {"medianBaseSalary": 85000, "currency": "USD", "numSalaries": 42}
    salary = normalize_salary_row(row, "QA Engineer")
    assert salary["medianBaseSalary"] == 85000
    assert salary["currency"] == "USD"
    assert salary["sampleSize"] == 42

def test_activity_log_message_sparse_salary():
    snapshot = build_job_company_research_snapshot(
        glassdoor_company_id="882104",
        matched_name="FlightHub",
        overview=parse_overview_row(FLIGHTHUB_OVERVIEW),
        glassdoor_job_title="QA Engineer",
        salary=None,
        interviews=[],
    )
    msg = format_activity_log_message(snapshot)
    assert msg.startswith("Company research ·")
    assert "2.8★" in msg
    assert "40% recommend" in msg
    assert "salary n/a" in msg

def test_format_search_candidates_caps_at_three():
    rows = [
        {"companyId": "1", "companyName": "Alpha", "size": "1 to 50"},
        {"companyId": "2", "companyName": "Beta", "size": "51 to 200"},
        {"companyId": "3", "companyName": "Gamma"},
        {"companyId": "4", "companyName": "Delta"},
    ]
    candidates = format_search_candidates(rows, limit=3)
    assert len(candidates) == 3
    assert candidates[0]["glassdoorCompanyId"] == "1"
    assert candidates[0]["matchedName"] == "Alpha"
    assert candidates[0]["previewSize"] == "1 to 50"
    assert candidates[2]["matchedName"] == "Gamma"

def test_format_repick_activity_log_message():
    assert format_repick_activity_log_message("QualiTest Group") == (
        "Company research · employer changed to QualiTest Group"
    )
