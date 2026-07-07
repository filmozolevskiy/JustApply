"""Tests for Glassdoor core module — mocked Apify boundary."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.company_research.glassdoor_intel import (
    _pick_company_match,
    _summarize_interviews,
    build_job_company_research_snapshot,
    format_activity_log_message,
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
