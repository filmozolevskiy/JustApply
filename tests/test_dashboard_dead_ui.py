import os

HTML_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")


def _read_html():
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        return f.read()


def test_add_job_button_absent():
    content = _read_html()
    assert "addNewJobPrompt" not in content, "addNewJobPrompt should be fully removed"


def test_add_new_job_prompt_function_absent():
    content = _read_html()
    assert "Add Job" not in content, "Add Job button should be removed"


def test_kb_scrape_btn_top_absent():
    content = _read_html()
    assert "kb-scrape-btn-top" not in content, "kb-scrape-btn-top should be removed"


def test_scrape_and_sync_button_absent():
    content = _read_html()
    assert "Scrape &amp; Sync" not in content and "Scrape & Sync" not in content, \
        "Scrape & Sync button should be removed"


def test_run_scraper_with_filters_remains():
    content = _read_html()
    assert "Run Scraper with Filters" in content, \
        "Run Scraper with Filters must remain as the sole scrape trigger"


def test_connection_mode_update_logic_absent():
    content = _read_html()
    assert "connection-mode" not in content, \
        "All connection-mode references including update logic should be removed"


def test_job_search_settings_header_present():
    content = _read_html()
    assert "Job Search Settings" in content, "Job Search Settings title must remain"
    assert "toggleJobSearchSettings" in content, "Job Search Settings toggle must remain"
    assert "job-search-settings-toggle" in content, "Job Search Settings toggle button must remain"
    assert "Manage applications by status lanes" not in content, "Old subtitle must be removed"
