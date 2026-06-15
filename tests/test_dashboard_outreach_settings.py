import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kanban_js import (
    get_drawer_body,
    load_kanban_js,
    read_dashboard_html,
    read_drawer_controller,
)

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
    assert "Contact Search Settings" in content, "Missing Contact Search Settings section heading"
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


def test_dashboard_html_enrich_job_uses_server_status_not_optimistic():
    """enrichJob applies server-returned job status instead of optimistic lane mutation."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    enrich_job_start = content.find("function enrichJob(")
    assert enrich_job_start != -1
    enrich_job_body = content[enrich_job_start:enrich_job_start + 2500]
    assert "job.status = 'enriching'" not in enrich_job_body
    assert "data.job" in enrich_job_body


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
    board_renderer_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "static", "js", "boardRenderer.js")
    with open(board_renderer_path) as f:
        content = f.read()
    assert "enrichmentNote" in content, \
        "boardRenderer must render a warning strip for jobs with enrichmentNote"


def test_dashboard_html_drawer_enrichment_status_section():
    """Job drawer shows an Enrichment Status section when enrichmentNote is set."""
    content = read_drawer_controller()
    assert "function openJobDetailsDrawer(" in content, "openJobDetailsDrawer function not found"
    assert "Enrichment Status" in content, \
        "openJobDetailsDrawer must include an Enrichment Status section"
    assert "enrichmentNote" in content, \
        "openJobDetailsDrawer must use enrichmentNote to conditionally show the section"


def test_dashboard_html_contact_search_settings_nested_in_job_search_panel():
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    contact_pos = content.find("Contact Search Settings")
    board_controls_pos = content.find("Board Controls")
    assert contact_pos != -1, "Contact Search Settings section not found"
    assert board_controls_pos != -1, "Board Controls panel not found"
    body_start = content.index('id="job-search-settings-body"')
    body_end = content.index('id="kb-logs-panel"')
    assert body_start < contact_pos < body_end, (
        "Contact Search Settings must be nested in job-search-settings-body"
    )


def _get_drawer_body(_content=None):
    return get_drawer_body()


def _contact_group_body(script):
    marker = "function contactGroup("
    fn_start = script.find(marker)
    if fn_start == -1:
        fn_start = script.find("export function contactGroup(")
    assert fn_start != -1, "contactGroup function must be defined"
    return script[fn_start : fn_start + 400]


def test_drawer_active_contact_loads_recruiter_template_for_is_recruiter():
    """Recruiter contact (is_recruiter=true) loads recruiterOutreachTemplate."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    drawer_body = _get_drawer_body()
    assert "recruiterOutreachTemplate" in drawer_body, \
        "Drawer must reference recruiterOutreachTemplate for recruiter contacts"


def test_drawer_active_contact_loads_russian_speaker_template_for_non_recruiter():
    """Non-recruiter contact loads russianSpeakerOutreachTemplate."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    drawer_body = _get_drawer_body()
    assert "russianSpeakerOutreachTemplate" in drawer_body, \
        "Drawer must reference russianSpeakerOutreachTemplate for non-recruiter contacts"


def test_drawer_active_contact_highlight_uses_is_recruiter_flag():
    """HR badge is driven by is_recruiter flag, not title keywords."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    drawer_body = _get_drawer_body()
    assert "is_recruiter" in drawer_body, \
        "Drawer must use is_recruiter flag for HR badge"
    assert "hiring manager" not in drawer_body.lower(), \
        "Drawer must not use title-keyword 'hiring manager' for HR badge"


def test_drawer_active_contact_row_highlighted():
    """Active Contact row has a distinct visual highlight (cyan left border)."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    drawer_body = _get_drawer_body()
    assert "activeContactIdx" in drawer_body, \
        "Drawer must track activeContactIdx for Active Contact highlight"


def test_drawer_character_counter_present():
    """Outreach textarea has a live character counter."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    drawer_body = _get_drawer_body()
    assert "/200" in drawer_body, \
        "Drawer must show a character counter with /200 limit"


def test_drawer_regenerate_button_removed():
    """The Regenerate button is removed from the drawer."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    drawer_body = _get_drawer_body()
    assert "regenerateOutreach" not in drawer_body, \
        "Regenerate button must be removed from the drawer"


def test_drawer_title_keyword_badge_logic_removed():
    """Title-keyword HR heuristic must be removed from the drawer."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    drawer_body = _get_drawer_body()
    assert "talent acquisition" not in drawer_body.lower(), \
        "Title-keyword HR heuristic must be removed from the drawer"
    assert "human resource" not in drawer_body.lower(), \
        "Title-keyword HR heuristic must be removed from the drawer"


# --- Issue #32: Contact Grouping ---

def _load_script():
    return load_kanban_js()


def test_contact_group_function_routes_recruiter_to_recruiters():
    """contactGroup(contact) returns 'recruiters' when is_recruiter is true."""
    script = load_kanban_js()
    assert "contactGroup" in script, "contactGroup function must be defined"
    fn_body = _contact_group_body(script)
    assert "is_recruiter" in fn_body, "contactGroup must check is_recruiter"
    assert "'recruiters'" in fn_body, "contactGroup must return 'recruiters'"


def test_contact_group_function_routes_russian_speaker_to_russian_speakers():
    """contactGroup(contact) returns 'russian_speakers' for non-recruiter russian speakers."""
    fn_body = _contact_group_body(load_kanban_js())
    assert "russian_speaker" in fn_body, "contactGroup must check russian_speaker"
    assert "'russian_speakers'" in fn_body, "contactGroup must return 'russian_speakers'"


def test_contact_group_function_dual_classified_routes_to_recruiters():
    """Dual-classified contacts (is_recruiter + russian_speaker) go to 'recruiters'."""
    fn_body = _contact_group_body(load_kanban_js())
    # is_recruiter must be checked before russian_speaker (dual → recruiters)
    recruiter_pos = fn_body.find("is_recruiter")
    russian_pos = fn_body.find("russian_speaker")
    assert recruiter_pos != -1 and russian_pos != -1
    assert recruiter_pos < russian_pos, \
        "contactGroup must check is_recruiter before russian_speaker so dual-classified → recruiters"


def test_contact_group_function_neither_routes_to_other():
    """contactGroup(contact) returns 'other' when neither flag is set."""
    fn_body = _contact_group_body(load_kanban_js())
    assert "'other'" in fn_body, "contactGroup must return 'other' as the fallback"


def test_drawer_contacts_show_all_three_group_headings():
    """openJobDetailsDrawer renders Recruiters, Russian Speakers, and Other group headings."""
    script = read_drawer_controller()
    assert "Recruiters" in script, "Script must include 'Recruiters' group label"
    assert "Russian Speakers" in script, "Script must include 'Russian Speakers' group label"
    assert "Other" in script, "Script must include 'Other' group label"
    # Verify they appear together (a helper function renders all three)
    recruiters_pos = script.find("'Recruiters'")
    if recruiters_pos == -1:
        recruiters_pos = script.find('"Recruiters"')
    assert recruiters_pos != -1, "Recruiters label must appear in script"


def test_drawer_contacts_grouped_preserve_flat_array_index():
    """Contact callbacks (toggleContacted, selectActiveContact) use the original flat-array index."""
    script = read_drawer_controller()
    # A helper that builds grouped contact HTML must use origIdx (original flat index)
    assert "origIdx" in script, \
        "Grouped contact rendering must use origIdx to preserve flat-array index for API calls"


def test_contact_name_title_do_not_toggle_contacted_checkbox():
    """Only the checkbox may toggle contacted; name/title must not be label-linked."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    drawer_body = _get_drawer_body()
    assert 'label for="contact-${jobId}-${origIdx}"' not in drawer_body, \
        "Contact name/title must not be wrapped in a label tied to the contacted checkbox"
    assert "onchange=\"toggleContacted(" in drawer_body, \
        "toggleContacted must remain wired to the checkbox onchange handler"


# --- Issue #35: Persist outreach template edits ---

def test_save_outreach_template_function_defined():
    """saveOutreachTemplate function must be present in the script."""
    script = _load_script()
    assert "function saveOutreachTemplate(" in script, \
        "saveOutreachTemplate function must be defined in the dashboard script"


def test_outreach_textarea_wired_to_save_template():
    """Outreach textarea oninput must call saveOutreachTemplate."""
    script = _load_script()
    assert "saveOutreachTemplate" in script, \
        "saveOutreachTemplate must be referenced in the drawer outreach textarea oninput"


def test_save_outreach_template_uses_debounce():
    """saveOutreachTemplate must debounce saves (uses templateSaveTimeout)."""
    script = read_drawer_controller()
    assert "templateSaveTimeout" in script, \
        "saveOutreachTemplate must use templateSaveTimeout for debouncing"


def test_save_outreach_template_calls_template_endpoint():
    """saveOutreachTemplate must PUT to /api/jobs/.../template."""
    script = read_drawer_controller()
    assert "/template" in script, \
        "saveOutreachTemplate must call the /template API endpoint"


def test_save_outreach_template_uses_active_contact_audience():
    """saveOutreachTemplate selects audience from active contact's is_recruiter flag."""
    script = read_drawer_controller()
    fn_start = script.find("function saveOutreachTemplate(")
    assert fn_start != -1
    fn_body = script[fn_start:fn_start + 800]
    assert "is_recruiter" in fn_body, \
        "saveOutreachTemplate must inspect is_recruiter to determine audience"
    assert "recruiter" in fn_body, \
        "saveOutreachTemplate must send audience='recruiter' for recruiter contacts"
    assert "russian_speaker" in fn_body, \
        "saveOutreachTemplate must send audience='russian_speaker' for non-recruiter contacts"


def test_save_outreach_template_updates_in_memory_job():
    """saveOutreachTemplate updates the in-memory job entry immediately."""
    script = read_drawer_controller()
    fn_start = script.find("function saveOutreachTemplate(")
    assert fn_start != -1
    fn_body = script[fn_start:fn_start + 800]
    # Must update at least one of the in-memory template fields
    assert "recruiterOutreachTemplate" in fn_body or "russianSpeakerOutreachTemplate" in fn_body, \
        "saveOutreachTemplate must update the in-memory job template field"


# --- Issue #39: Active Contact greeting name substitution ---

def test_name_placeholder_constant_defined():
    """NAME_PLACEHOLDER constant must be defined in the script."""
    script = _load_script()
    assert "NAME_PLACEHOLDER" in script, \
        "NAME_PLACEHOLDER constant must be defined in the dashboard script"


def test_apply_greeting_name_function_defined():
    """applyGreetingName function must be defined in the script."""
    script = read_drawer_controller()
    assert "applyGreetingName" in script, \
        "applyGreetingName function must be defined in the dashboard script"


def test_normalize_greeting_function_defined():
    """normalizeGreeting function must be defined in the script."""
    script = read_drawer_controller()
    assert "normalizeGreeting" in script, \
        "normalizeGreeting function must be defined in the dashboard script"


def test_select_active_contact_applies_greeting_substitution():
    """selectActiveContact must call applyGreetingName to substitute the contact's first name."""
    script = read_drawer_controller()
    fn_start = script.find("function selectActiveContact(")
    assert fn_start != -1, "selectActiveContact function must exist"
    fn_body = script[fn_start:fn_start + 1200]
    assert "applyGreetingName" in fn_body, \
        "selectActiveContact must call applyGreetingName to substitute the greeting name"


def test_save_outreach_template_normalizes_greeting():
    """saveOutreachTemplate must call normalizeGreeting before persisting the template."""
    script = read_drawer_controller()
    fn_start = script.find("function saveOutreachTemplate(")
    assert fn_start != -1, "saveOutreachTemplate function must exist"
    fn_body = script[fn_start:fn_start + 1000]
    assert "normalizeGreeting" in fn_body, \
        "saveOutreachTemplate must call normalizeGreeting to restore the Name Placeholder before saving"


def test_open_job_drawer_applies_greeting_for_default_contact():
    """openJobDetailsDrawer must apply greeting substitution for the default active contact."""
    script = read_drawer_controller()
    fn_start = script.find("function openJobDetailsDrawer(")
    assert fn_start != -1, "openJobDetailsDrawer function must exist"
    fn_body = script[fn_start:fn_start + 2000]
    assert "applyGreetingName" in fn_body, \
        "openJobDetailsDrawer must call applyGreetingName for the default active contact"


def test_apply_greeting_name_replaces_placeholder_in_hi_greeting():
    """applyGreetingName JS function body must replace NAME_PLACEHOLDER with first name."""
    script = _load_script()
    fn_start = script.find("function applyGreetingName(")
    assert fn_start != -1
    fn_body = script[fn_start:fn_start + 500]
    assert "replace" in fn_body, \
        "applyGreetingName must use string replace to substitute the name"


def test_normalize_greeting_restores_placeholder():
    """normalizeGreeting JS function body must replace back to NAME_PLACEHOLDER."""
    script = _load_script()
    fn_start = script.find("function normalizeGreeting(")
    assert fn_start != -1
    fn_body = script[fn_start:fn_start + 500]
    assert "NAME_PLACEHOLDER" in fn_body, \
        "normalizeGreeting must restore NAME_PLACEHOLDER in the greeting line"


def test_switch_audience_loads_template_and_applies_greeting():
    """selectActiveContact must load the audience template then apply greeting for the new contact."""
    script = _load_script()
    fn_start = script.find("function selectActiveContact(")
    assert fn_start != -1
    fn_body = script[fn_start:fn_start + 1200]
    # must call getActiveTemplate (loads correct audience template)
    assert "getActiveTemplate" in fn_body, \
        "selectActiveContact must call getActiveTemplate to load the correct audience template"
    # then apply greeting substitution
    assert "applyGreetingName" in fn_body, \
        "selectActiveContact must apply greeting substitution after loading the template"


def test_greeting_functions_support_hello_prefix():
    """applyGreetingName and normalizeGreeting must handle Hello greetings used by Connection Notes."""
    script = _load_script()
    for fn_name in ("applyGreetingName", "normalizeGreeting"):
        fn_start = script.find(f"function {fn_name}(")
        assert fn_start != -1, f"{fn_name} function must exist"
        fn_body = script[fn_start:fn_start + 500]
        assert "Hello" in fn_body, \
            f"{fn_name} must match Hello greetings from outreach templates"
