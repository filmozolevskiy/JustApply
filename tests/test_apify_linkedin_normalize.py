"""Pure Apify LinkedIn normalizer — Actor fixture rows → Job fields.

No live Actor HTTP. Spec: PRD #200 / issue #203.
"""

from src.core.apify_linkedin_scraper import normalize_apify_linkedin_job


def _full_fixture_row(**overrides):
    row = {
        "title": "Senior QA Engineer",
        "companyName": "Acme Corp",
        "companyLinkedinUrl": "https://www.linkedin.com/company/acme-corp",
        "companyEmployeesCount": 420,
        "link": "https://www.linkedin.com/jobs/view/9876543210",
        "postedAt": "2026-08-01",
        "location": "San Francisco, CA",
        "employmentType": "Full-time",
        "salary": "$140,000 - $170,000",
        "descriptionText": "Lead QA for our data products.",
        "seniorityLevel": "Mid-Senior level",
        "workplaceTypes": ["Remote"],
        "jobPosterName": "Alex Recruiter",
        "jobPosterTitle": "Talent Partner",
        "jobPosterProfileUrl": "https://www.linkedin.com/in/alex-recruiter",
    }
    row.update(overrides)
    return row


def test_normalize_maps_company_linkedin_url_to_company_url():
    result = normalize_apify_linkedin_job(_full_fixture_row())
    assert result["companyUrl"] == "https://www.linkedin.com/company/acme-corp"
    assert result["title"] == "Senior QA Engineer"
    assert result["company"] == "Acme Corp"
    assert result["link"] == "https://www.linkedin.com/jobs/view/9876543210"
    assert result["status"] == "scraped"


def test_normalize_maps_poster_fields_to_preliminary_contacts():
    result = normalize_apify_linkedin_job(_full_fixture_row())
    assert len(result["contacts"]) == 1
    contact = result["contacts"][0]
    assert contact["name"] == "Alex Recruiter"
    assert contact["title"] == "Talent Partner"
    assert contact["url"] == "https://www.linkedin.com/in/alex-recruiter"
    assert contact["is_job_poster"] is True
    assert contact["contacted"] is False


def test_normalize_missing_company_url_still_saves_shape():
    result = normalize_apify_linkedin_job(
        _full_fixture_row(companyLinkedinUrl="", companyEmployeesCount=None)
    )
    assert result["companyUrl"] == ""
    assert result["title"] == "Senior QA Engineer"
    assert result["status"] == "scraped"


def test_normalize_missing_poster_yields_empty_contacts():
    result = normalize_apify_linkedin_job(
        _full_fixture_row(
            jobPosterName=None,
            jobPosterTitle=None,
            jobPosterProfileUrl=None,
        )
    )
    assert result["contacts"] == []


def test_normalize_derives_remote_type_from_workplace_types():
    remote = normalize_apify_linkedin_job(_full_fixture_row(workplaceTypes=["Remote"]))
    assert remote["remoteType"] == "remote"

    hybrid = normalize_apify_linkedin_job(
        _full_fixture_row(workplaceTypes=["Hybrid"], location="Austin, TX")
    )
    assert hybrid["remoteType"] == "hybrid"

    office = normalize_apify_linkedin_job(
        _full_fixture_row(workplaceTypes=["On-site"], location="Austin, TX")
    )
    assert office["remoteType"] == "in_office"


def test_normalize_seniority_from_level_and_title():
    senior = normalize_apify_linkedin_job(_full_fixture_row())
    assert senior["seniority"] == "senior"

    junior = normalize_apify_linkedin_job(
        _full_fixture_row(
            title="Junior QA Assistant",
            seniorityLevel="Entry level",
            workplaceTypes=["On-site"],
        )
    )
    assert junior["seniority"] == "junior"


def test_normalize_size_from_employee_count():
    result = normalize_apify_linkedin_job(_full_fixture_row(companyEmployeesCount=420))
    assert result["size"] == "420"


def test_normalize_falls_back_to_description_html_stripped():
    result = normalize_apify_linkedin_job(
        _full_fixture_row(
            descriptionText="",
            descriptionHtml="<p>Build <b>quality</b> systems.</p>",
        )
    )
    assert "Build" in result["description"]
    assert "quality" in result["description"]
    assert "<" not in result["description"]


def test_normalize_salary_info_fallback():
    result = normalize_apify_linkedin_job(
        _full_fixture_row(salary="", salaryInfo=["$120k", "$150k"])
    )
    assert "$120k" in result["salary"]
