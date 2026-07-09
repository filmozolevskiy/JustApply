"""Tests for Company Research preflight/run API and pipeline."""
from unittest.mock import AsyncMock

import pytest
import src.db.connection as _db_connection
from fastapi.testclient import TestClient
from src import db as database
from src.core.company_research.glassdoor_intel import GlassdoorInfrastructureError
from src.db.company_research_cache import set_company_research_cache
from src.db.jobs import add_job, update_job_evaluation
from src.pipelines import run_company_research_pipeline, run_company_research_repick_pipeline
from src.web.server import app

client = TestClient(app)

FLIGHTHUB_SEARCH = [{"companyId": "882104", "companyName": "FlightHub"}]
FLIGHTHUB_OVERVIEW = [
    {
        "size": "51 to 200 Employees",
        "rating": 2.8,
        "reviewCount": 246,
        "recommendToFriendPercent": 40,
    }
]

@pytest.fixture
def db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test.db")
    monkeypatch.setattr(_db_connection, "DB_PATH", test_db)
    database.init_db(test_db)
    return test_db

def _make_matched_job(db, company="FlightHub", title="Senior QA Engineer (Hybrid)"):
    job_id = add_job(
        {
            "title": title,
            "company": company,
            "companyUrl": "https://www.linkedin.com/company/flighthub/",
            "status": "scraped",
        },
        db_path=db,
    )
    update_job_evaluation(
        job_id,
        {
            "matchScore": 80,
            "matchType": "strong",
            "resumeUsed": "qa.md",
        },
        db_path=db,
    )
    database.update_job_status(job_id, "matched", db_path=db)
    return job_id

def _mock_runner(responses: dict):
    async def runner(operation: str, **kwargs):
        if operation == "companySearch":
            return responses.get("companySearch", [])
        if operation == "companyOverview":
            return responses.get("companyOverview", [])
        if operation == "companySalaries":
            return responses.get("companySalaries", [])
        if operation == "companyInterviews":
            return responses.get("companyInterviews", [])
        return []

    return runner

def test_preflight_full_miss_lists_four_billable_slices(db):
    job_id = _make_matched_job(db)
    resp = client.get(f"/api/jobs/{job_id}/company-research-preflight")
    assert resp.status_code == 200
    data = resp.json()
    assert data["will_call_apify"] is True
    assert data["estimated_runs"] == 4
    assert len(data["billable_slices"]) == 4
    assert data["default_glassdoor_job_title"] == "Senior QA Engineer (Hybrid)"

def test_preflight_custom_glassdoor_job_title(db):
    job_id = _make_matched_job(db)
    resp = client.get(
        f"/api/jobs/{job_id}/company-research-preflight",
        params={"glassdoorJobTitle": "QA Engineer"},
    )
    data = resp.json()
    assert data["default_glassdoor_job_title"] == "QA Engineer"

def test_preflight_full_cache_hit(db):
    job_id = _make_matched_job(db)
    set_company_research_cache(
        "flighthub",
        {
            "glassdoorCompanyId": "882104",
            "matchedName": "FlightHub",
            "companySize": "51 to 200 Employees",
            "rating": 2.8,
            "reviewCount": 246,
            "recommendPercent": 40.0,
            "salariesByTitle": {"qa engineer": None},
            "interviewsByTitle": {"qa engineer": []},
        },
        db_path=db,
    )
    resp = client.get(
        f"/api/jobs/{job_id}/company-research-preflight",
        params={"glassdoorJobTitle": "QA Engineer"},
    )
    data = resp.json()
    assert data["will_call_apify"] is False
    assert data["estimated_runs"] == 0

def test_preflight_partial_cache_bills_title_slices_only(db):
    job_id = _make_matched_job(db)
    set_company_research_cache(
        "flighthub",
        {
            "glassdoorCompanyId": "882104",
            "matchedName": "FlightHub",
            "companySize": "51 to 200 Employees",
            "rating": 2.8,
            "reviewCount": 246,
            "recommendPercent": 40.0,
            "salariesByTitle": {"qa engineer": {"medianBaseSalary": 85000, "currency": "USD"}},
            "interviewsByTitle": {"qa engineer": []},
        },
        db_path=db,
    )
    resp = client.get(
        f"/api/jobs/{job_id}/company-research-preflight",
        params={"glassdoorJobTitle": "Data Analyst"},
    )
    data = resp.json()
    assert data["estimated_runs"] == 2
    assert "Salaries" in data["billable_slices"]
    assert "Interviews" in data["billable_slices"]

def test_preflight_rejects_scraped_lane(db):
    job_id = add_job({"title": "QA", "company": "Acme", "status": "scraped"}, db_path=db)
    resp = client.get(f"/api/jobs/{job_id}/company-research-preflight")
    assert resp.status_code == 422

def test_preflight_rejects_rejected_lane(db):
    job_id = add_job({"title": "QA", "company": "Acme", "status": "rejected"}, db_path=db)
    resp = client.get(f"/api/jobs/{job_id}/company-research-preflight")
    assert resp.status_code == 422

def test_run_endpoint_rejects_scraped_lane(db):
    job_id = add_job({"title": "QA", "company": "Acme", "status": "scraped"}, db_path=db)
    resp = client.post(
        f"/api/jobs/{job_id}/company-research",
        json={"glassdoorJobTitle": "QA Engineer"},
    )
    assert resp.status_code == 422

def test_run_endpoint_returns_task_id(db):
    job_id = _make_matched_job(db)
    resp = client.post(
        f"/api/jobs/{job_id}/company-research",
        json={"glassdoorJobTitle": "QA Engineer"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert data["job_id"] == job_id

@pytest.mark.asyncio
async def test_pipeline_first_fetch_persists_cache_and_snapshot(db):
    job_id = _make_matched_job(db)
    runner = _mock_runner(
        {
            "companySearch": FLIGHTHUB_SEARCH,
            "companyOverview": FLIGHTHUB_OVERVIEW,
            "companySalaries": [],
            "companyInterviews": [],
        }
    )
    updated = await run_company_research_pipeline(
        job_id,
        "QA Engineer",
        apify_runner=runner,
        db_path=db,
    )
    assert updated.companyResearch is not None
    assert updated.companyResearch["matchedName"] == "FlightHub"
    assert updated.companyResearch["glassdoorJobTitle"] == "QA Engineer"
    assert updated.companyResearch["rating"] == 2.8
    cached = database.get_company_research_cache("flighthub", db_path=db)
    assert cached["glassdoorCompanyId"] == "882104"
    messages = [e.message for e in updated.activityLog]
    assert any(m.startswith("Company research ·") for m in messages)

@pytest.mark.asyncio
async def test_pipeline_cache_hit_skips_apify(db):
    job_id = _make_matched_job(db)
    set_company_research_cache(
        "flighthub",
        {
            "glassdoorCompanyId": "882104",
            "matchedName": "FlightHub",
            "companySize": "51 to 200 Employees",
            "rating": 2.8,
            "reviewCount": 246,
            "recommendPercent": 40.0,
            "salariesByTitle": {"qa engineer": None},
            "interviewsByTitle": {"qa engineer": []},
        },
        db_path=db,
    )
    runner = AsyncMock(side_effect=AssertionError("Apify should not be called"))
    updated = await run_company_research_pipeline(
        job_id,
        "QA Engineer",
        apify_runner=runner,
        db_path=db,
    )
    runner.assert_not_called()
    assert updated.companyResearch["matchedName"] == "FlightHub"

@pytest.mark.asyncio
async def test_pipeline_rejects_scraped_lane(db):
    job_id = add_job({"title": "QA", "company": "Acme", "status": "scraped"}, db_path=db)
    with pytest.raises(ValueError, match="Matched"):
        await run_company_research_pipeline(job_id, "QA Engineer", db_path=db)

def test_preflight_defaults_to_existing_research_title(db):
    job_id = _make_matched_job(db, title="Senior QA Engineer (Hybrid)")
    database.update_company_research(
        job_id,
        {
            "glassdoorCompanyId": "882104",
            "matchedName": "FlightHub",
            "glassdoorJobTitle": "QA Engineer",
            "rating": 2.8,
        },
        db_path=db,
    )
    set_company_research_cache(
        "flighthub",
        {
            "glassdoorCompanyId": "882104",
            "matchedName": "FlightHub",
            "companySize": "51 to 200 Employees",
            "rating": 2.8,
            "reviewCount": 246,
            "recommendPercent": 40.0,
            "salariesByTitle": {"qa engineer": None},
            "interviewsByTitle": {"qa engineer": []},
        },
        db_path=db,
    )
    resp = client.get(f"/api/jobs/{job_id}/company-research-preflight")
    data = resp.json()
    assert data["default_glassdoor_job_title"] == "QA Engineer"
    assert data["will_call_apify"] is False

@pytest.mark.asyncio
async def test_pipeline_partial_cache_fetches_title_slices_only(db):
    job_id = _make_matched_job(db)
    set_company_research_cache(
        "flighthub",
        {
            "glassdoorCompanyId": "882104",
            "matchedName": "FlightHub",
            "companySize": "51 to 200 Employees",
            "rating": 2.8,
            "reviewCount": 246,
            "recommendPercent": 40.0,
            "salariesByTitle": {"qa engineer": {"medianBaseSalary": 85000, "currency": "USD"}},
            "interviewsByTitle": {"qa engineer": []},
        },
        db_path=db,
    )
    calls: list[str] = []

    async def runner(operation: str, **kwargs):
        calls.append(operation)
        if operation == "companySalaries":
            return [{"medianBaseSalary": 92000, "currency": "USD", "numSalaries": 12}]
        if operation == "companyInterviews":
            return [
                {
                    "jobTitle": "Data Analyst",
                    "difficulty": "Average",
                    "outcome": "Accepted offer",
                    "processDescription": "Phone screen then onsite.",
                }
            ]
        raise AssertionError(f"Unexpected operation: {operation}")

    updated = await run_company_research_pipeline(
        job_id,
        "Data Analyst",
        apify_runner=runner,
        db_path=db,
    )
    assert calls == ["companySalaries", "companyInterviews"]
    assert updated.companyResearch["glassdoorJobTitle"] == "Data Analyst"
    assert updated.companyResearch["salary"]["medianBaseSalary"] == 92000
    assert len(updated.companyResearch["interviews"]) == 1

@pytest.mark.asyncio
async def test_pipeline_infrastructure_error_does_not_cache(db):
    job_id = _make_matched_job(db)
    set_company_research_cache(
        "flighthub",
        {
            "glassdoorCompanyId": "882104",
            "matchedName": "FlightHub",
            "companySize": "51 to 200 Employees",
            "rating": 2.8,
            "reviewCount": 246,
            "recommendPercent": 40.0,
            "salariesByTitle": {},
            "interviewsByTitle": {},
        },
        db_path=db,
    )

    async def runner(operation: str, **kwargs):
        if operation == "companySalaries":
            raise GlassdoorInfrastructureError("Apify timeout")
        return []

    with pytest.raises(GlassdoorInfrastructureError):
        await run_company_research_pipeline(
            job_id,
            "QA Engineer",
            apify_runner=runner,
            db_path=db,
        )
    cached = database.get_company_research_cache("flighthub", db_path=db)
    assert "qa engineer" not in cached["salariesByTitle"]

@pytest.mark.asyncio
async def test_two_jobs_same_company_different_titles(db):
    job_a = _make_matched_job(db, title="Senior QA Engineer")
    job_b = _make_matched_job(db, title="Data Analyst Lead")
    qa_runner = _mock_runner(
        {
            "companySearch": FLIGHTHUB_SEARCH,
            "companyOverview": FLIGHTHUB_OVERVIEW,
            "companySalaries": [{"medianBaseSalary": 85000, "currency": "USD"}],
            "companyInterviews": [
                {
                    "jobTitle": "QA Engineer",
                    "difficulty": "Easy",
                    "outcome": "Accepted offer",
                    "processDescription": "QA interview loop.",
                }
            ],
        }
    )
    await run_company_research_pipeline(job_a, "QA Engineer", apify_runner=qa_runner, db_path=db)

    da_runner = _mock_runner(
        {
            "companySalaries": [{"medianBaseSalary": 92000, "currency": "USD"}],
            "companyInterviews": [
                {
                    "jobTitle": "Data Analyst",
                    "difficulty": "Hard",
                    "outcome": "No offer",
                    "processDescription": "DA interview loop.",
                }
            ],
        }
    )
    await run_company_research_pipeline(job_b, "Data Analyst", apify_runner=da_runner, db_path=db)

    job_a_updated = database.get_job(job_a, db_path=db)
    job_b_updated = database.get_job(job_b, db_path=db)
    assert job_a_updated.companyResearch["glassdoorJobTitle"] == "QA Engineer"
    assert job_a_updated.companyResearch["salary"]["medianBaseSalary"] == 85000
    assert job_b_updated.companyResearch["glassdoorJobTitle"] == "Data Analyst"
    assert job_b_updated.companyResearch["salary"]["medianBaseSalary"] == 92000
    cached = database.get_company_research_cache("flighthub", db_path=db)
    assert cached["salariesByTitle"]["qa engineer"]["medianBaseSalary"] == 85000
    assert cached["salariesByTitle"]["data analyst"]["medianBaseSalary"] == 92000

QUALITEST_SEARCH = [
    {"companyId": "111", "companyName": "QualiTest Group", "size": "51 to 200 Employees"},
    {"companyId": "222", "companyName": "Qualitest Global", "size": "10000+ Employees"},
    {"companyId": "333", "companyName": "QualiTest India", "size": "201 to 500 Employees"},
    {"companyId": "444", "companyName": "Other Corp"},
]

def _seed_researched_job(db, company="Qualitest", title="QA Engineer"):
    job_id = _make_matched_job(db, company=company, title=title)
    database.update_company_research(
        job_id,
        {
            "glassdoorCompanyId": "222",
            "matchedName": "Qualitest Global",
            "glassdoorJobTitle": "QA Engineer",
            "rating": 3.5,
            "reviewCount": 1000,
            "recommendPercent": 55.0,
            "companySize": "10000+ Employees",
        },
        db_path=db,
    )
    set_company_research_cache(
        "qualitest",
        {
            "glassdoorCompanyId": "222",
            "matchedName": "Qualitest Global",
            "companySize": "10000+ Employees",
            "rating": 3.5,
            "reviewCount": 1000,
            "recommendPercent": 55.0,
            "salariesByTitle": {"qa engineer": None},
            "interviewsByTitle": {"qa engineer": []},
        },
        db_path=db,
    )
    return job_id

def test_candidates_clears_cache_and_returns_top_three(db, monkeypatch):
    job_id = _seed_researched_job(db)

    async def fake_fetch(company_name, apify_runner=None):
        assert company_name == "Qualitest"
        return [
            {"glassdoorCompanyId": "111", "matchedName": "QualiTest Group", "previewSize": "51 to 200 Employees"},
            {"glassdoorCompanyId": "222", "matchedName": "Qualitest Global", "previewSize": "10000+ Employees"},
            {"glassdoorCompanyId": "333", "matchedName": "QualiTest India", "previewSize": "201 to 500 Employees"},
        ]

    import src.core.company_research.glassdoor_intel as glassdoor_module

    monkeypatch.setattr(glassdoor_module, "fetch_glassdoor_company_candidates", fake_fetch)
    resp = client.post(f"/api/jobs/{job_id}/company-research/candidates")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["candidates"]) == 3
    assert data["candidates"][0]["matchedName"] == "QualiTest Group"
    assert database.get_company_research_cache("qualitest", db_path=db) is None

def test_candidates_requires_researched_job(db):
    job_id = _make_matched_job(db)
    resp = client.post(f"/api/jobs/{job_id}/company-research/candidates")
    assert resp.status_code == 422

def test_repick_preflight_bills_overview_and_title_slices(db):
    job_id = _seed_researched_job(db)
    resp = client.get(
        f"/api/jobs/{job_id}/company-research/repick-preflight",
        params={
            "glassdoorCompanyId": "111",
            "matchedName": "QualiTest Group",
            "glassdoorJobTitle": "QA Engineer",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["will_call_apify"] is True
    assert data["estimated_runs"] == 3
    assert "Company search" in data["cached_slices"]
    assert "Company overview" in data["billable_slices"]
    assert "Salaries" in data["billable_slices"]
    assert "Interviews" in data["billable_slices"]

def test_repick_endpoint_returns_task_id(db):
    job_id = _seed_researched_job(db)
    resp = client.post(
        f"/api/jobs/{job_id}/company-research/repick",
        json={
            "glassdoorCompanyId": "111",
            "matchedName": "QualiTest Group",
            "glassdoorJobTitle": "QA Engineer",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert data["job_id"] == job_id

@pytest.mark.asyncio
async def test_repick_pipeline_updates_employer_and_logs(db):
    job_id = _seed_researched_job(db)
    runner = _mock_runner(
        {
            "companyOverview": [
                {
                    "size": "51 to 200 Employees",
                    "rating": 4.1,
                    "reviewCount": 120,
                    "recommendToFriendPercent": 72,
                }
            ],
            "companySalaries": [{"medianBaseSalary": 78000, "currency": "USD"}],
            "companyInterviews": [
                {
                    "jobTitle": "QA Engineer",
                    "difficulty": "Average",
                    "outcome": "Accepted offer",
                    "processDescription": "Phone screen.",
                }
            ],
        }
    )
    updated = await run_company_research_repick_pipeline(
        job_id,
        "QA Engineer",
        "111",
        "QualiTest Group",
        apify_runner=runner,
        db_path=db,
    )
    assert updated.companyResearch["matchedName"] == "QualiTest Group"
    assert updated.companyResearch["glassdoorCompanyId"] == "111"
    assert updated.companyResearch["rating"] == 4.1
    cached = database.get_company_research_cache("qualitest", db_path=db)
    assert cached["glassdoorCompanyId"] == "111"
    assert cached["matchedName"] == "QualiTest Group"
    messages = [e.message for e in updated.activityLog]
    assert any("employer changed to QualiTest Group" in m for m in messages)
