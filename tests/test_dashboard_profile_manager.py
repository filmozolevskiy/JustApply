"""Static HTML/JS scan tests for Profile Manager modal (PRD #85, issue #96)."""

import os
import re

from tests.kanban_js import get_script_section, read_dashboard_html

HTML_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")


def _read_html():
    with open(HTML_PATH, encoding="utf-8") as f:
        return f.read()


def test_manage_profiles_button_in_top_nav():
    content = _read_html()
    nav_start = content.index('class="top-navbar"')
    nav_end = content.index("</header>", nav_start)
    nav = content[nav_start:nav_end]
    assert "Manage Profiles" in nav
    assert "openProfileManager" in nav


def test_old_active_profile_dropdown_removed():
    content = _read_html()
    assert "active-resume-select" not in content
    assert "Active Profile:" not in content
    assert "changeActiveResume" not in content


def test_old_view_resume_modal_removed():
    content = _read_html()
    assert "viewResumeProfile" not in content
    assert 'id="resume-modal"' not in content


def test_profile_manager_two_pane_modal_present():
    content = _read_html()
    assert 'id="profile-manager-modal"' in content
    assert 'class="pm-list"' in content
    assert 'class="pm-detail"' in content
    assert "Import PDF" in content
    assert "Set active" in content
    assert 'id="pm-editor"' in content


def test_active_resume_persisted_in_local_storage():
    js = get_script_section(_read_html())
    assert "ACTIVE_RESUME_KEY" in js
    assert "localStorage.setItem(ACTIVE_RESUME_KEY" in js or "localStorage.setItem(ACTIVE_RESUME_KEY," in js


def test_active_resume_not_hardcoded_to_general_cv():
    js = get_script_section(_read_html())
    assert 'let activeResume = "general_cv.md"' not in js


def test_resolve_active_resume_fallback_logic():
    js = get_script_section(_read_html())
    assert "resolveActiveResume" in js
    assert "general_cv.md" not in re.search(
        r"function resolveActiveResume\([^)]*\)\s*\{[^}]+\}",
        js,
        re.DOTALL,
    ).group(0)


def test_trigger_scrape_uses_active_resume_variable():
    js = get_script_section(_read_html())
    assert "active_resume: activeResume" in js


def test_load_resumes_restores_stored_active_profile():
    js = get_script_section(_read_html())
    assert "resolveActiveResume" in js
    assert "localStorage.getItem(ACTIVE_RESUME_KEY" in js


def test_profile_manager_editor_is_editable():
    content = _read_html()
    assert 'id="pm-editor"' in content
    assert 'id="pm-editor" readonly' not in content.replace(" ", "")


def test_profile_manager_save_posts_to_api_resumes():
    js = get_script_section(_read_html())
    assert "saveProfileManagerProfile" in js
    assert "fetch('/api/resumes'" in js or "fetch(\"/api/resumes\"" in js


def test_profile_manager_new_opens_review_state():
    content = _read_html()
    js = get_script_section(content)
    assert "newProfileManagerProfile" in js
    assert "profileManagerReviewing" in js
    assert "pm-review-banner" in content
    assert "Review before save" in content
    assert "pm-name-input" in content


def test_profile_manager_review_disables_set_active_and_delete():
    js = get_script_section(_read_html())
    assert "profileManagerReviewing" in js
    # Set active and delete disabled while reviewing
    assert re.search(
        r"if \(profileManagerReviewing\)[\s\S]{0,400}setActiveBtn\.disabled = true",
        js,
    )
    assert re.search(
        r"if \(profileManagerReviewing\)[\s\S]{0,400}deleteBtn\.disabled = true",
        js,
    )


def test_profile_manager_delete_calls_api_with_confirmation():
    js = get_script_section(_read_html())
    fn_match = re.search(
        r"async function deleteProfileManagerProfile\(\)\s*\{([\s\S]*?)\n    \}",
        js,
    )
    assert fn_match, "deleteProfileManagerProfile function not found"
    fn_body = fn_match.group(1)
    assert "confirm(" in fn_body
    assert "method: 'DELETE'" in fn_body or 'method: "DELETE"' in fn_body
    assert "active_resume" in fn_body


def test_profile_manager_delete_disabled_for_active_or_last_profile():
    js = get_script_section(_read_html())
    assert re.search(
        r"canDelete[\s\S]{0,120}activeResume",
        js,
    )
    assert re.search(
        r"profileManagerProfiles\.length\s*>\s*1",
        js,
    )


def test_profile_manager_import_pdf_posts_to_convert_endpoint():
    js = get_script_section(_read_html())
    assert "triggerProfileManagerImport" in js
    assert "handleProfileManagerImportFile" in js
    assert "/api/resumes/convert" in js
    assert "profileManagerDraftContent" in js


def test_profile_manager_import_shows_spinner_during_conversion():
    js = get_script_section(_read_html())
    fn_match = re.search(
        r"async function handleProfileManagerImportFile\([^)]*\)\s*\{([\s\S]*?)\n    \}",
        js,
    )
    assert fn_match, "handleProfileManagerImportFile function not found"
    fn_body = fn_match.group(1)
    assert "fa-spinner" in fn_body
    assert "Converting" in fn_body


def test_profile_manager_import_opens_review_state_on_success():
    js = get_script_section(_read_html())
    fn_match = re.search(
        r"async function handleProfileManagerImportFile\([^)]*\)\s*\{([\s\S]*?)\n    \}",
        js,
    )
    assert fn_match
    fn_body = fn_match.group(1)
    assert "profileManagerReviewing = true" in fn_body
    assert "profileManagerDraftContent" in fn_body
