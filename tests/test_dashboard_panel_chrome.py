import os

HTML_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")


def _read_html():
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        return f.read()


def test_panel_order():
    """Job Search Settings → Task Logs → Board Controls → kanban."""
    content = _read_html()
    js_idx = content.index("Job Search Settings")
    tl_idx = content.index("Task Logs")
    bc_idx = content.index('id="board-controls-panel"')
    kb_idx = content.index("kanban-lanes-container")
    assert js_idx < tl_idx < bc_idx < kb_idx, (
        f"Panel order wrong: JS={js_idx} TL={tl_idx} BC={bc_idx} KB={kb_idx}"
    )


def test_contact_search_settings_nested_in_job_search_panel():
    """Contact Search Settings must live inside the Job Search Settings collapsible body."""
    content = _read_html()
    body_start = content.index('id="job-search-settings-body"')
    body_end = content.index('id="kb-logs-panel"')
    body_block = content[body_start:body_end]
    assert "Contact Search Settings" in body_block, (
        "Contact Search Settings must be nested inside job-search-settings-body"
    )
    assert 'id="contact-search-settings-section"' in body_block, (
        "Contact Search Settings section id must be inside job-search-settings-body"
    )


def test_board_controls_immediately_precedes_kanban():
    """Board Controls must come directly before the kanban lane container."""
    content = _read_html()
    bc_idx = content.index('id="board-controls-panel"')
    kb_idx = content.index("kanban-lanes-container")
    assert bc_idx < kb_idx
    between = content[bc_idx:kb_idx]
    # nothing significant should start a new glass-panel section between them
    assert between.count('class="glass-panel"') <= 1, (
        "Another glass-panel appears between Board Controls and kanban lanes"
    )


def test_shared_panel_header_class():
    """Utility panels use the panel-header class (Job Search, Contact Search, Task Logs, Board Controls)."""
    content = _read_html()
    assert content.count("panel-header") >= 4, (
        "Expected at least 4 panel-header class uses (Job Search, Contact Search, Task Logs, Board Controls)"
    )


def test_task_logs_collapse_key():
    """Task Logs body has data-collapse-key attribute for local storage persistence."""
    content = _read_html()
    assert 'data-collapse-key="panel-task-logs-collapsed"' in content


def test_job_search_settings_collapse_key():
    """Job Search Settings body has data-collapse-key for local storage persistence."""
    content = _read_html()
    assert 'data-collapse-key="panel-scraper-settings-collapsed"' in content


def test_task_logs_collapsed_by_default():
    """Task Logs console has .shrunk class in static HTML (collapsed on first visit)."""
    content = _read_html()
    # Find the kb-logs-console element and verify it has 'shrunk' in its class list
    console_idx = content.index('id="kb-logs-console"')
    # Look at the opening tag (before the '>') - find the class attribute
    tag_start = content.rindex("<", 0, console_idx)
    tag_end = content.index(">", console_idx)
    tag = content[tag_start:tag_end]
    assert "shrunk" in tag, f"kb-logs-console should have 'shrunk' class by default, got: {tag}"


def test_job_search_settings_collapsed_by_default():
    """Job Search Settings body starts without .expanded class (collapsed by default)."""
    content = _read_html()
    panel_idx = content.index('id="job-search-settings-body"')
    tag_start = content.rindex("<", 0, panel_idx)
    tag_end = content.index(">", panel_idx)
    tag = content[tag_start:tag_end]
    assert "expanded" not in tag, "job-search-settings-body should not have 'expanded' in its static class"


def test_job_search_settings_show_hide_toggle():
    """Job Search Settings uses a Show/Hide toggle instead of a Scraper Settings label."""
    content = _read_html()
    assert "toggleJobSearchSettings" in content
    assert 'id="job-search-settings-toggle"' in content
    assert "Scraper Settings" not in content
    assert "> Show" in content or "> Show<" in content


def test_job_search_settings_init_restores_state():
    """Job Search Settings collapse state is restored on page load."""
    content = _read_html()
    assert "initJobSearchSettingsState" in content
    assert "initJobSearchSettingsState()" in content


def test_contact_search_settings_no_cyan_tint():
    """Contact Search Settings must not use the ad-hoc cyan background tint inline."""
    content = _read_html()
    assert "rgba(6, 182, 212, 0.04)" not in content, (
        "Contact Search Settings cyan background tint should be removed"
    )


def test_board_controls_has_id():
    """Board Controls panel has id=board-controls-panel."""
    content = _read_html()
    assert 'id="board-controls-panel"' in content


def test_contact_search_settings_no_cyan_border():
    """Contact Search Settings section must not use the inline border-color cyan tint."""
    content = _read_html()
    cs_idx = content.index('id="contact-search-settings-section"')
    tag_start = content.rindex("<", 0, cs_idx)
    tag_end = content.index(">", cs_idx)
    tag = content[tag_start:tag_end]
    assert "rgba(6, 182, 212, 0.2)" not in tag, (
        "Contact Search Settings section should not have inline cyan border-color"
    )


def test_contact_search_settings_has_section_divider():
    """Contact Search Settings must be separated from scraper filters by a horizontal divider."""
    content = _read_html()
    body_start = content.index('id="job-search-settings-body"')
    body_end = content.index('id="kb-logs-panel"')
    body_block = content[body_start:body_end]
    cs_idx = body_block.index("Contact Search Settings")
    divider_idx = body_block.rindex("panel-section-divider", 0, cs_idx)
    assert divider_idx != -1, (
        "A panel-section-divider must appear before Contact Search Settings inside job-search-settings-body"
    )


def test_job_search_subtitle_removed():
    """The old Pipeline Tracker subtitle must be removed."""
    content = _read_html()
    assert "Manage applications by status lanes" not in content
