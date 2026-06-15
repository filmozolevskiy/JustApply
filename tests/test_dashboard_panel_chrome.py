import os

HTML_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")


def _read_html():
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        return f.read()


def test_panel_order():
    """Pipeline Tracker → Task Logs → Outreach Settings → Board Controls → kanban."""
    content = _read_html()
    pt_idx = content.index("Pipeline Tracker")
    tl_idx = content.index("Task Logs")
    os_idx = content.index("Outreach Settings")
    bc_idx = content.index('id="board-controls-panel"')
    kb_idx = content.index("kanban-lanes-container")
    assert pt_idx < tl_idx < os_idx < bc_idx < kb_idx, (
        f"Panel order wrong: PT={pt_idx} TL={tl_idx} OS={os_idx} BC={bc_idx} KB={kb_idx}"
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
    """All four utility panels use the panel-header class."""
    content = _read_html()
    assert content.count("panel-header") >= 4, (
        "Expected at least 4 panel-header class uses (one per utility panel)"
    )


def test_task_logs_collapse_key():
    """Task Logs body has data-collapse-key attribute for local storage persistence."""
    content = _read_html()
    assert 'data-collapse-key="panel-task-logs-collapsed"' in content


def test_scraper_settings_collapse_key():
    """Scraper Settings panel has data-collapse-key for local storage persistence."""
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


def test_scraper_settings_collapsed_by_default():
    """Scraper Settings panel starts without .expanded class (collapsed by default)."""
    content = _read_html()
    panel_idx = content.index('id="scraper-settings-panel"')
    tag_start = content.rindex("<", 0, panel_idx)
    tag_end = content.index(">", panel_idx)
    tag = content[tag_start:tag_end]
    assert "expanded" not in tag, "scraper-settings-panel should not have 'expanded' in its static class"


def test_outreach_settings_no_cyan_tint():
    """Outreach Settings panel must not use the ad-hoc cyan background tint inline."""
    content = _read_html()
    # rgba(6, 182, 212, 0.04) only ever appeared in the outreach-settings-panel inline style
    assert "rgba(6, 182, 212, 0.04)" not in content, (
        "Outreach Settings cyan background tint should be removed"
    )


def test_board_controls_has_id():
    """Board Controls panel has id=board-controls-panel."""
    content = _read_html()
    assert 'id="board-controls-panel"' in content


def test_outreach_settings_no_cyan_border():
    """Outreach Settings panel must not use the inline border-color cyan tint."""
    content = _read_html()
    # Check the outreach-settings-panel element's inline style is clean
    os_idx = content.index('id="outreach-settings-panel"')
    tag_start = content.rindex("<", 0, os_idx)
    tag_end = content.index(">", os_idx)
    tag = content[tag_start:tag_end]
    assert "rgba(6, 182, 212, 0.2)" not in tag, (
        "Outreach Settings panel should not have inline cyan border-color"
    )
