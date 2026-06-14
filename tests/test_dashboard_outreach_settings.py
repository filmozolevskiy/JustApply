import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import db as database
import src.db.connection as _db_connection
from src.web.server import app
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_job_tracker.db"
    test_db_str = str(test_db)

    monkeypatch.setattr(_db_connection, "DB_PATH", test_db_str)

    database.init_db(test_db_str)

    yield test_db_str


def test_get_outreach_settings_returns_defaults_on_first_read():
    response = client.get("/api/settings/outreach")
    assert response.status_code == 200
    data = response.json()
    assert data["target_russian_speakers"] is True
    assert data["target_recruiters"] is True


def test_put_outreach_settings_persists_values():
    put_response = client.put(
        "/api/settings/outreach",
        json={"target_russian_speakers": False, "target_recruiters": True},
    )
    assert put_response.status_code == 200
    data = put_response.json()
    assert data["target_russian_speakers"] is False
    assert data["target_recruiters"] is True


def test_outreach_settings_round_trip():
    client.put(
        "/api/settings/outreach",
        json={"target_russian_speakers": False, "target_recruiters": False},
    )
    get_response = client.get("/api/settings/outreach")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["target_russian_speakers"] is False
    assert data["target_recruiters"] is False


def test_dashboard_html_contains_outreach_settings_panel():
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    assert 'id="toggle-russian-speakers"' in content, "Missing Russian speakers toggle"
    assert 'id="toggle-recruiters"' in content, "Missing recruiters toggle"
    assert "Outreach Settings" in content, "Missing Outreach Settings panel heading"
    assert "saveOutreachSettings" in content, "Missing saveOutreachSettings JS function"
    assert "loadOutreachSettings" in content, "Missing loadOutreachSettings JS function"


def test_dashboard_html_enrichment_uses_sse():
    """enrichJob opens an EventSource using a task_id returned by the enrich endpoint."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    assert "task_id" in content, "enrichJob must use task_id from enrich endpoint"
    enrich_job_start = content.find("function enrichJob(")
    assert enrich_job_start != -1, "enrichJob function not found"
    enrich_job_body = content[enrich_job_start:enrich_job_start + 2000]
    assert "EventSource" in enrich_job_body, "enrichJob must open an EventSource for SSE"


def test_dashboard_html_polling_loop_not_called_from_enrich():
    """enrichJob must not start the polling loop (SSE replaces it)."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    enrich_job_start = content.find("function enrichJob(")
    assert enrich_job_start != -1
    enrich_job_body = content[enrich_job_start:enrich_job_start + 2000]
    assert "startPollingEnrichingJobs" not in enrich_job_body, \
        "enrichJob must not call startPollingEnrichingJobs; SSE handles card updates"


def test_dashboard_html_card_warning_strip_for_enrichment_note():
    """Kanban card rendering references enrichmentNote for the warning strip."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    render_start = content.find("function renderVariantB(")
    assert render_start != -1, "renderVariantB function not found"
    render_body = content[render_start:render_start + 6000]
    assert "enrichmentNote" in render_body, \
        "renderVariantB must render a warning strip for jobs with enrichmentNote"


def test_dashboard_html_drawer_enrichment_status_section():
    """Job drawer shows an Enrichment Status section when enrichmentNote is set."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    drawer_start = content.find("function openJobDetailsDrawer(")
    assert drawer_start != -1, "openJobDetailsDrawer function not found"
    drawer_body = content[drawer_start:drawer_start + 8000]
    assert "Enrichment Status" in drawer_body, \
        "openJobDetailsDrawer must include an Enrichment Status section"
    assert "enrichmentNote" in drawer_body, \
        "openJobDetailsDrawer must use enrichmentNote to conditionally show the section"


def test_dashboard_html_outreach_panel_is_separate_from_board_controls():
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    outreach_pos = content.find("Outreach Settings")
    board_controls_pos = content.find("Board Controls")
    assert outreach_pos != -1, "Outreach Settings panel not found"
    assert board_controls_pos != -1, "Board Controls panel not found"
    assert outreach_pos != board_controls_pos, "Outreach Settings must be separate from Board Controls"


def _get_drawer_body(content):
    drawer_start = content.find("function openJobDetailsDrawer(")
    assert drawer_start != -1, "openJobDetailsDrawer not found"
    return content[drawer_start:drawer_start + 12000]


def test_drawer_active_contact_loads_recruiter_template_for_is_recruiter():
    """Recruiter contact (is_recruiter=true) loads recruiterOutreachTemplate."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    drawer_body = _get_drawer_body(content)
    assert "recruiterOutreachTemplate" in drawer_body, \
        "Drawer must reference recruiterOutreachTemplate for recruiter contacts"


def test_drawer_active_contact_loads_russian_speaker_template_for_non_recruiter():
    """Non-recruiter contact loads russianSpeakerOutreachTemplate."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    drawer_body = _get_drawer_body(content)
    assert "russianSpeakerOutreachTemplate" in drawer_body, \
        "Drawer must reference russianSpeakerOutreachTemplate for non-recruiter contacts"


def test_drawer_active_contact_highlight_uses_is_recruiter_flag():
    """HR badge is driven by is_recruiter flag, not title keywords."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    drawer_body = _get_drawer_body(content)
    assert "is_recruiter" in drawer_body, \
        "Drawer must use is_recruiter flag for HR badge"
    assert "hiring manager" not in drawer_body.lower(), \
        "Drawer must not use title-keyword 'hiring manager' for HR badge"


def test_drawer_active_contact_row_highlighted():
    """Active Contact row has a distinct visual highlight (cyan left border)."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    drawer_body = _get_drawer_body(content)
    assert "activeContactIdx" in drawer_body, \
        "Drawer must track activeContactIdx for Active Contact highlight"


def test_drawer_character_counter_present():
    """Outreach textarea has a live character counter."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    drawer_body = _get_drawer_body(content)
    assert "/200" in drawer_body, \
        "Drawer must show a character counter with /200 limit"


def test_drawer_regenerate_button_removed():
    """The Regenerate button is removed from the drawer."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    drawer_body = _get_drawer_body(content)
    assert "regenerateOutreach" not in drawer_body, \
        "Regenerate button must be removed from the drawer"


def test_drawer_title_keyword_badge_logic_removed():
    """Title-keyword HR heuristic must be removed from the drawer."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    drawer_body = _get_drawer_body(content)
    assert "talent acquisition" not in drawer_body.lower(), \
        "Title-keyword HR heuristic must be removed from the drawer"
    assert "human resource" not in drawer_body.lower(), \
        "Title-keyword HR heuristic must be removed from the drawer"
