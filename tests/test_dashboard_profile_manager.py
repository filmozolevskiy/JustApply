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
