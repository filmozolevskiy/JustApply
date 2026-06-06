import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os
import datetime

# Add root directory to path to import job_hunter
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import from job_hunter (to be implemented)
from job_hunter import run_search_pipeline, filter_jobs, normalize_job

@pytest.mark.asyncio
async def test_run_search_pipeline_calls_mcp_for_each_site():
    mock_session = AsyncMock()
    
    mock_tools_list = MagicMock()
    mock_tools_list.tools = [MagicMock(name="search_jobs")]
    mock_session.list_tools.return_value = mock_tools_list
    
    mock_call_result = MagicMock()
    mock_call_result.content = [
        MagicMock(
            text='{"count": 1, "jobs": [{"id": "1", "title": "QA Engineer", "company": "Google", "location": "New York, NY", "jobUrl": "http://google.com/job1", "datePosted": "2026-06-01"}]}'
        )
    ]
    mock_session.call_tool.return_value = mock_call_result
    
    mock_read = MagicMock()
    mock_write = MagicMock()
    
    with patch('job_hunter.stdio_client') as mock_stdio_client, \
         patch('job_hunter.ClientSession') as mock_client_session:
         
        mock_stdio_client.return_value.__aenter__.return_value = (mock_read, mock_write)
        mock_client_session.return_value.__aenter__.return_value = mock_session
        
        results = await run_search_pipeline("QA", sites=["linkedin", "indeed"])
        
        assert mock_session.initialize.called
        assert mock_session.call_tool.call_count == 2
        
        # Check that it called search_jobs with the correct parameters
        mock_session.call_tool.assert_any_call(
            "search_jobs",
            {
                "siteNames": "linkedin",
                "searchTerm": "QA",
                "location": "remote",
                "resultsWanted": 20,
                "hoursOld": 72
            }
        )
        mock_session.call_tool.assert_any_call(
            "search_jobs",
            {
                "siteNames": "indeed",
                "searchTerm": "QA",
                "location": "remote",
                "resultsWanted": 20,
                "hoursOld": 72
            }
        )

def test_filter_jobs_keywords():
    jobs = [
        {"title": "QA Automation Engineer", "description": "Looking for testing skills", "location": "New York, NY", "isRemote": False},
        {"title": "Java Developer", "description": "No testing mentioned", "location": "New York, NY", "isRemote": False},
        {"title": "Project Manager", "description": "Managing projects", "location": "Remote", "isRemote": True}
    ]
    # Filter by QA
    qa_jobs = filter_jobs(jobs, "QA")
    assert len(qa_jobs) == 1
    assert qa_jobs[0]["title"] == "QA Automation Engineer"
    
    # Filter by Project/delivery manager
    pm_jobs = filter_jobs(jobs, "Project/delivery manager")
    assert len(pm_jobs) == 1
    assert pm_jobs[0]["title"] == "Project Manager"

def test_filter_jobs_timezone():
    jobs = [
        # In Eastern states
        {"title": "QA", "description": "", "location": "New York, NY", "isRemote": False},
        {"title": "QA", "description": "", "location": "Atlanta, GA", "isRemote": False},
        # In Western states
        {"title": "QA", "description": "", "location": "Seattle, WA", "isRemote": False},
        # Remote with Eastern preferred
        {"title": "QA", "description": "Remote. Eastern Time Zone preferred", "location": "Remote", "isRemote": True},
        # Remote with Pacific preferred
        {"title": "QA", "description": "Must work in Pacific Time Zone (PST)", "location": "Remote", "isRemote": True},
        # Remote with no restrictions
        {"title": "QA", "description": "Work from anywhere", "location": "Remote", "isRemote": True}
    ]
    
    filtered = filter_jobs(jobs, "QA")
    # Expected: NY, GA (Eastern states) should pass. WA (Western state) should fail.
    # Remote Eastern should pass. Remote Pacific should fail. Remote anywhere should pass.
    # So NY, GA, Remote Eastern, Remote anywhere should pass -> 4 jobs.
    passed_locations = [j["location"] for j in filtered]
    assert "New York, NY" in passed_locations
    assert "Atlanta, GA" in passed_locations
    assert "Seattle, WA" not in passed_locations
    assert "Remote" in passed_locations
    assert len(filtered) == 4

def test_normalize_job():
    raw_job = {
        "title": "Senior QA Engineer",
        "company": "Google",
        "companyNumEmployees": "10,000+",
        "jobUrl": "https://linkedin.com/jobs/view/123",
        "datePosted": "2026-06-01T12:00:00Z",
        "location": "New York, NY",
        "isRemote": True,
        "description": "This is a long description " * 50,
        "minAmount": 120000,
        "maxAmount": 150000,
        "currency": "USD",
        "interval": "yearly"
    }
    
    normalized = normalize_job(raw_job)
    
    assert normalized["Job title"] == "Senior QA Engineer"
    assert normalized["Company + Company size"] == "Google (10,000+)"
    assert normalized["Posting link"] == "https://linkedin.com/jobs/view/123"
    assert normalized["Posting date"] == "2026-06-01T12:00:00Z"
    assert normalized["Location + Remote type (in office, hybrid, remote)"] == "Remote (New York, NY)"
    assert normalized["Seniority type (junior, mid, senior)"] == "senior"
    assert "$120k" in normalized["Salary type"] and "$150k" in normalized["Salary type"]
    assert len(normalized["Short description"]) <= 503  # 500 chars + "..."
    assert normalized["match"] == ""
    assert normalized["no-match"] == ""
    assert normalized["Should proceed?"] == ""


@pytest.mark.asyncio
async def test_evaluate_job_compatibility_success():
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"match": "Skills match", "no_match": "No gaps", "should_proceed": true}'
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)
    
    with patch('google.generativeai.GenerativeModel', return_value=mock_model) as mock_model_init:
        from job_hunter import evaluate_job_compatibility
        
        job = {
            "Job title": "QA Engineer",
            "Company + Company size": "Google",
            "Location + Remote type (in office, hybrid, remote)": "Remote",
            "Seniority type (junior, mid, senior)": "senior",
            "Salary type": "$150k",
            "Short description": "Looking for a QA engineer with Python skills."
        }
        
        result = await evaluate_job_compatibility("Resume content", job, api_key="test_key")
        
        assert result["match"] == "Skills match"
        assert result["no-match"] == "No gaps"
        assert result["Should proceed?"] == "Yes"
        
        mock_model_init.assert_called_once_with('gemini-2.5-flash')
        mock_model.generate_content_async.assert_called_once()


@pytest.mark.asyncio
async def test_run_orchestrator_pipeline_success():
    # Mock jobs search
    mock_jobs = [
        {"title": "QA Lead", "description": "Looking for python lead", "location": "New York, NY", "isRemote": False},
        {"title": "QA Intern", "description": "Looking for entry level", "location": "Remote", "isRemote": True}
    ]
    
    # Mock sheets MCP session
    mock_sheets_session = AsyncMock()
    mock_resume_result = MagicMock()
    mock_resume_result.content = [MagicMock(text="# QA Resume Text")]
    mock_sheets_session.call_tool.side_effect = [
        mock_resume_result,  # first call: get_resume
        MagicMock(content=[MagicMock(text="Job added successfully")]), # second call: add_job (QA Lead)
        MagicMock(content=[MagicMock(text="Job added successfully")])  # third call: add_job (QA Intern)
    ]
    
    mock_read = MagicMock()
    mock_write = MagicMock()
    
    # Mock evaluate_job_compatibility
    mock_evaluated_lead = {
        "Job title": "QA Lead",
        "Company + Company size": "TechCorp",
        "Posting link": "http://example.com/1",
        "Posting date": "",
        "Location + Remote type (in office, hybrid, remote)": "In Office",
        "Seniority type (junior, mid, senior)": "senior",
        "Salary type": "",
        "Short description": "Looking for python lead",
        "match": "Strong match",
        "no-match": "None",
        "Should proceed?": "Yes"
    }
    mock_evaluated_intern = {
        "Job title": "QA Intern",
        "Company + Company size": "TechCorp",
        "Posting link": "http://example.com/2",
        "Posting date": "",
        "Location + Remote type (in office, hybrid, remote)": "Remote",
        "Seniority type (junior, mid, senior)": "junior",
        "Salary type": "",
        "Short description": "Looking for entry level",
        "match": "Weak match",
        "no-match": "Too junior",
        "Should proceed?": "No"
    }
    
    with patch('job_hunter.run_search_pipeline', return_value=mock_jobs) as mock_search, \
         patch('job_hunter.stdio_client') as mock_stdio_client, \
         patch('job_hunter.ClientSession') as mock_client_session, \
         patch('job_hunter.evaluate_job_compatibility') as mock_eval:
         
        mock_stdio_client.return_value.__aenter__.return_value = (mock_read, mock_write)
        mock_client_session.return_value.__aenter__.return_value = mock_sheets_session
        
        mock_eval.side_effect = [mock_evaluated_lead, mock_evaluated_intern]
        
        from job_hunter import run_orchestrator_pipeline
        
        # Test default: write all jobs (flag unmatched)
        results = await run_orchestrator_pipeline("QA", skip_unmatched=False, sites=["linkedin"])
        
        assert mock_search.called
        assert mock_eval.call_count == 2
        assert mock_sheets_session.call_tool.call_count == 3 # 1 get_resume + 2 add_job
        assert len(results) == 2
        
        # Test skip_unmatched=True
        mock_sheets_session.call_tool.reset_mock()
        mock_sheets_session.call_tool.side_effect = [
            mock_resume_result,
            MagicMock(content=[MagicMock(text="Job added successfully")])
        ]
        mock_eval.reset_mock()
        mock_eval.side_effect = [mock_evaluated_lead, mock_evaluated_intern]
        
        results_skipped = await run_orchestrator_pipeline("QA", skip_unmatched=True, sites=["linkedin"])
        
        assert mock_eval.call_count == 2
        assert mock_sheets_session.call_tool.call_count == 2 # 1 get_resume + 1 add_job (intern skipped)
        assert len(results_skipped) == 1

def test_extract_company_slug():
    from job_hunter import extract_company_slug
    
    data = {
        "references": {
            "search_results": [
                {"kind": "company", "url": "/company/docker/", "text": "Docker, Inc"},
                {"kind": "company", "url": "/company/google/", "text": "Google"}
            ]
        }
    }
    
    assert extract_company_slug("Docker", data) == "docker"
    assert extract_company_slug("Random Company", {}) == "random-company"
    assert extract_company_slug("Google (10,000+)", {}) == "google"

@pytest.mark.asyncio
async def test_extract_contacts_via_llm():
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '[{"name": "John Doe", "title": "Recruiter", "url": "https://www.linkedin.com/in/johndoe"}]'
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)
    
    with patch('google.generativeai.GenerativeModel', return_value=mock_model) as mock_model_init:
        from job_hunter import extract_contacts_via_llm
        res = await extract_contacts_via_llm("raw text", api_key="key")
        assert len(res) == 1
        assert res[0]["name"] == "John Doe"
        mock_model_init.assert_called_once_with('gemini-2.5-flash')

@pytest.mark.asyncio
async def test_generate_outreach_messages():
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "[Cover Letter]\nDear Google\n\n[Referral Message]\nHi John"
    mock_model.generate_content_async = AsyncMock(return_value=mock_response)
    
    with patch('google.generativeai.GenerativeModel', return_value=mock_model) as mock_model_init:
        from job_hunter import generate_outreach_messages
        res = await generate_outreach_messages("Resume content", {"Job title": "QA"}, [], api_key="key")
        assert "[Cover Letter]" in res
        assert "[Referral Message]" in res
        mock_model_init.assert_called_once_with('gemini-2.5-flash')

@pytest.mark.asyncio
async def test_run_promotion_pipeline_success():
    # Mock sheets MCP session
    mock_sheets_session = AsyncMock()
    
    # 1. Mock get_resume call tool output
    mock_resume_result = MagicMock()
    mock_resume_result.content = [MagicMock(text="# QA Resume Text")]
    
    # 2. Mock list_jobs call tool output
    mock_list_jobs_result = MagicMock()
    mock_list_jobs_result.content = [MagicMock(text='[{"Job title": "QA Engineer", "Company + Company size": "Docker (501-1k employees)", "Posting link": "https://docker.com/job1", "Should proceed?": "Yes", "Posting date": "2026-06-01", "Location + Remote type (in office, hybrid, remote)": "Remote", "Salary type": "$100k", "Short description": "QA details", "match": "Good match", "no-match": "None"}]')]
    
    # 3. Mock list_applications call tool output
    mock_list_apps_result = MagicMock()
    mock_list_apps_result.content = [MagicMock(text='[]')]
    
    # 4. Mock track_application call tool output
    mock_track_app_result = MagicMock()
    mock_track_app_result.content = [MagicMock(text='Success')]
    
    mock_sheets_session.call_tool.side_effect = [
        mock_resume_result,      # get_resume
        mock_list_jobs_result,    # list_jobs
        mock_list_apps_result,    # list_applications
        mock_track_app_result     # track_application
    ]
    
    # Mock linkedin MCP session
    mock_li_session = AsyncMock()
    
    # search_companies
    mock_search_comp_res = MagicMock()
    mock_search_comp_res.content = [MagicMock(text='{"references": {"search_results": [{"kind": "company", "url": "/company/docker/", "text": "Docker"}]}}')]
    
    # get_company_employees recruiter
    mock_rec_res = MagicMock()
    mock_rec_res.content = [MagicMock(text='{"references": {"employees": [{"kind": "person", "url": "/in/kmarscel", "text": "Kyle"}]}}')]
    
    # get_company_employees hiring manager
    mock_hm_res = MagicMock()
    mock_hm_res.content = [MagicMock(text='{"references": {"employees": []}}')]
    
    mock_li_session.call_tool.side_effect = [
        mock_search_comp_res, # search_companies
        mock_rec_res,         # recruiter employees
        mock_hm_res           # hiring manager employees
    ]
    
    mock_read = MagicMock()
    mock_write = MagicMock()
    
    # Mock helpers
    mock_contacts = [{"name": "Kyle", "title": "Recruiter", "url": "https://www.linkedin.com/in/kmarscel"}]
    mock_outreach_msg = "[Cover Letter]\nDear Docker\n\n[Referral Message]\nHi Kyle"
    
    mock_cache_inst = MagicMock()
    mock_cache_inst.get_slug.return_value = None
    mock_cache_inst.get_contacts.return_value = None
    mock_cache_inst.get_lookups_count_last_24h.return_value = 0
    
    with patch('job_hunter.stdio_client') as mock_stdio_client, \
         patch('job_hunter.ClientSession') as mock_client_session, \
         patch('job_hunter.extract_contacts_via_llm', return_value=mock_contacts) as mock_extract, \
         patch('job_hunter.generate_outreach_messages', return_value=mock_outreach_msg) as mock_gen_outreach, \
         patch('job_hunter.LinkedInCache', return_value=mock_cache_inst), \
         patch('job_hunter.asyncio.sleep') as mock_sleep:
         
        # We need two stdio_client mocks, one for sheets and one for linkedin
        mock_stdio_client.return_value.__aenter__.side_effect = [
            (mock_read, mock_write), # sheets client
            (mock_read, mock_write)  # linkedin client
        ]
        
        mock_client_session.return_value.__aenter__.side_effect = [
            mock_sheets_session, # sheets session
            mock_li_session      # linkedin session
        ]
        
        from job_hunter import run_promotion_pipeline
        
        results = await run_promotion_pipeline("QA")
        
        assert len(results) == 1
        assert results[0]["Job title"] == "QA Engineer"
        
        # Verify Sheets track_application call
        mock_sheets_session.call_tool.assert_any_call(
            "track_application",
            {
                "job_title": "QA Engineer",
                "company": "Docker (501-1k employees)",
                "posting_link": "https://docker.com/job1",
                "posting_date": "2026-06-01",
                "application_date": datetime.date.today().isoformat(),
                "location": "Remote",
                "salary": "$100k",
                "short_description": "QA details",
                "match_details": "Good match",
                "no_match_details": "None",
                "people_contacted": "Kyle (Recruiter) - https://www.linkedin.com/in/kmarscel",
                "contact_message": mock_outreach_msg,
                "comment": "Promoted from Jobs"
            }
        )

def test_linkedin_cache(tmp_path):
    from job_hunter import LinkedInCache
    cache_file = tmp_path / "test_cache.json"
    cache = LinkedInCache(filepath=str(cache_file))
    
    # Verify defaults
    assert cache.get_slug("Nonexistent") is None
    assert cache.get_contacts("nonexistent-slug") is None
    assert cache.get_lookups_count_last_24h() == 0
    
    # Set and get slug
    cache.set_slug("Google", "google")
    assert cache.get_slug("Google") == "google"
    
    # Set and get contacts
    contacts = [{"name": "Jane", "title": "Recruiter", "url": "url"}]
    cache.set_contacts("google", contacts)
    assert cache.get_contacts("google") == contacts
    
    # Record lookups and check count
    cache.record_lookup()
    assert cache.get_lookups_count_last_24h() == 1
    
    # Test persistence by reloading
    reloaded = LinkedInCache(filepath=str(cache_file))
    assert reloaded.get_slug("Google") == "google"
    assert reloaded.get_contacts("google") == contacts
    assert reloaded.get_lookups_count_last_24h() == 1





