import os
import sys
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import db as database
import src.db.connection as _db_connection
import src.web.server as server_module
from src.web.server import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_job_tracker.db"
    test_db_str = str(test_db)
    monkeypatch.setattr(_db_connection, "DB_PATH", test_db_str)
    database.init_db(test_db_str)
    yield test_db_str


# --- POST /api/jobs/{id}/refresh-contacts ---

def test_post_refresh_contacts_returns_task_id():
    with patch("src.web.server.run_refresh_contacts_task_with_logs"):
        response = client.post("/api/jobs/1/refresh-contacts")
    assert response.status_code == 200
    data = response.json()
    assert "task_id" in data
    assert data["job_id"] == 1


def test_post_refresh_contacts_sets_job_to_accepted():
    with patch("src.web.server.run_refresh_contacts_task_with_logs"):
        client.post("/api/jobs/1/refresh-contacts")
    jobs = client.get("/api/jobs").json()
    job1 = next(j for j in jobs if j["id"] == 1)
    assert job1["status"] == "accepted"


def test_post_refresh_contacts_nonexistent_job_returns_404():
    response = client.post("/api/jobs/999/refresh-contacts")
    assert response.status_code == 404
    assert response.json() == {"message": "Job not found"}


# --- run_refresh_contacts_task_with_logs calls pipeline with bust_cache=True ---

@pytest.mark.asyncio
async def test_run_refresh_contacts_task_calls_pipeline_with_bust_cache(setup_test_db):
    from src.web.server import run_refresh_contacts_task_with_logs, TaskState, active_tasks
    from src.core.enrichment.coordinator import begin_enrichment
    from src.db import enrich_job
    import uuid

    enrich_job(1, [], "Hi", db_path=setup_test_db)
    begin_enrichment(1, setup_test_db)

    task_id = str(uuid.uuid4())
    state = TaskState({"job_id": 1})
    active_tasks[task_id] = state

    mock_contacts = [{"name": "Refreshed Contact", "url": "https://linkedin.com/in/r", "contacted": False, "russian_speaker": False}]
    mock_templates = {"recruiter": "Hello ______, refreshed.", "russian_speaker": ""}

    with patch("src.pipelines.source_contacts", new=AsyncMock(return_value=mock_contacts)) as mock_src, \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=mock_templates)):
        await run_refresh_contacts_task_with_logs(task_id, 1)

    mock_src.assert_called_once()
    call_kwargs = mock_src.call_args
    assert call_kwargs.kwargs.get("bust_cache") is True, "refresh-contacts must pass bust_cache=True"


@pytest.mark.asyncio
async def test_run_refresh_contacts_task_updates_job_contacts(setup_test_db):
    from src.web.server import run_refresh_contacts_task_with_logs, TaskState, active_tasks
    from src.core.enrichment.coordinator import begin_enrichment
    from src.db import enrich_job
    import uuid

    enrich_job(1, [], "Hi", db_path=setup_test_db)
    begin_enrichment(1, setup_test_db)

    task_id = str(uuid.uuid4())
    state = TaskState({"job_id": 1})
    active_tasks[task_id] = state

    mock_contacts = [{"name": "Fresh Contact", "url": "https://linkedin.com/in/fresh", "contacted": False, "russian_speaker": False}]
    mock_templates = {"recruiter": "Hello ______, fresh.", "russian_speaker": ""}

    with patch("src.pipelines.source_contacts", new=AsyncMock(return_value=mock_contacts)), \
         patch("src.pipelines.generate_outreach_templates", new=AsyncMock(return_value=mock_templates)):
        await run_refresh_contacts_task_with_logs(task_id, 1)

    job = database.get_job(1)
    assert job.status == "accepted"
    assert any(c.name == "Fresh Contact" for c in job.contacts)


# --- Dashboard HTML: refreshContacts function ---

def _load_script():
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    for marker in ('<script type="module">', '<script>'):
        start = content.find(marker)
        if start != -1:
            return content[start:]
    raise AssertionError("<script> block not found")


def test_dashboard_html_refresh_contacts_function_defined():
    script = _load_script()
    assert "function refreshContacts(" in script, \
        "refreshContacts JS function must be defined in the dashboard script"


def test_dashboard_html_refresh_contacts_calls_api_endpoint():
    script = _load_script()
    fn_start = script.find("function refreshContacts(")
    assert fn_start != -1
    fn_body = script[fn_start:fn_start + 1500]
    assert "/refresh-contacts" in fn_body, \
        "refreshContacts must call /api/jobs/{id}/refresh-contacts endpoint"


def test_dashboard_html_refresh_contacts_uses_sse():
    script = _load_script()
    fn_start = script.find("function refreshContacts(")
    assert fn_start != -1
    fn_body = script[fn_start:fn_start + 1500]
    assert "EventSource" in fn_body, \
        "refreshContacts must open an EventSource for SSE log streaming"


def test_dashboard_html_refresh_contacts_button_shown_for_enriched_job():
    from kanban_js import read_drawer_controller

    content = read_drawer_controller()
    drawer_start = content.find("function openJobDetailsDrawer(")
    assert drawer_start != -1
    drawer_body = content[drawer_start:drawer_start + 14000]
    assert "refreshContacts" in drawer_body, \
        "openJobDetailsDrawer must call refreshContacts for enriched/enriching jobs"
    assert "Refresh Contacts" in drawer_body, \
        "Drawer must contain a Refresh Contacts button label"


def test_dashboard_html_refresh_contacts_not_shown_on_found_job():
    """Found job drawer shows Enrich Job; Refresh Contacts is gated on accepted status."""
    from kanban_js import read_drawer_controller

    content = read_drawer_controller()
    drawer_start = content.find("function openJobDetailsDrawer(")
    assert drawer_start != -1
    drawer_body = content[drawer_start:drawer_start + 14000]
    # Enrich Job button must remain for sourced jobs
    assert "enrichJob" in drawer_body, \
        "Drawer must still reference enrichJob for sourced jobs"
    # Refresh Contacts must be conditionally gated on accepted status
    assert "refreshContacts" in drawer_body, \
        "refreshContacts must be in drawer but conditionally shown for accepted jobs"
    assert ("status === 'accepted'" in drawer_body or "status === \"accepted\"" in drawer_body), \
        "Refresh Contacts button must be gated on accepted status"
