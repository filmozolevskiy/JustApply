import os

HTML_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")


def _read_html():
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        return f.read()


def test_lane_collapse_btn_present():
    content = _read_html()
    assert "lane-collapse-btn" in content, \
        "Each lane header must have a lane-collapse-btn element"


def test_toggle_lane_collapse_on_click():
    content = _read_html()
    assert "toggleLaneCollapse(" in content, \
        "Collapse button must call toggleLaneCollapse with lane name"


def test_data_lane_attribute_on_columns():
    content = _read_html()
    assert 'data-lane="sourced"' in content, \
        "Kanban columns must carry a data-lane attribute"


def test_lane_name_text_class_present():
    content = _read_html()
    assert "lane-name-text" in content, \
        "Lane name span must have class lane-name-text for vertical-text CSS targeting"


def test_lane_collapsed_css_defined():
    content = _read_html()
    assert ".lane-collapsed" in content, \
        ".lane-collapsed CSS class must be defined"


def test_lane_collapse_btn_css_defined():
    content = _read_html()
    assert ".lane-collapse-btn" in content, \
        ".lane-collapse-btn CSS class must be defined"


def test_kanban_board_uses_flex():
    content = _read_html()
    # Board container must use flex so collapsed columns shrink and expanded ones grow
    idx = content.find(".kanban-board-container")
    snippet = content[idx:idx + 200]
    assert "display: flex" in snippet, \
        ".kanban-board-container must use display:flex (not grid) so lanes resize dynamically"


def test_kanban_column_has_flex_grow():
    content = _read_html()
    idx = content.find(".kanban-column {")
    snippet = content[idx:idx + 200]
    assert "flex:" in snippet or "flex-grow" in snippet or "flex: 1" in snippet, \
        ".kanban-column must have a flex growth property so expanded lanes fill space"


def test_collapsed_lane_has_narrow_width():
    content = _read_html()
    assert "lane-collapsed" in content
    # Collapsed column must have a narrow fixed size so it renders as a rail
    idx = content.find(".kanban-column.lane-collapsed")
    snippet = content[idx:idx + 300]
    assert "48px" in snippet or "40px" in snippet or "52px" in snippet, \
        ".kanban-column.lane-collapsed must have a narrow fixed width (rail)"


def test_collapsed_lane_hides_cards():
    content = _read_html()
    idx = content.find(".kanban-column.lane-collapsed")
    after = content[idx:]
    # The cards-wrapper rule appears within ~1200 chars of the first lane-collapsed block
    assert "lane-collapsed" in after and ".kanban-cards-wrapper" in after[:1200], \
        "Collapsed lane must hide the cards wrapper via a .lane-collapsed nested CSS rule"


def test_toggle_lane_collapse_function_defined():
    content = _read_html()
    assert "function toggleLaneCollapse" in content, \
        "toggleLaneCollapse function must be defined in JavaScript"


def test_init_lane_collapse_function_defined():
    content = _read_html()
    assert "function initLaneCollapse" in content, \
        "initLaneCollapse function must be defined for restoring state on page load"


def test_init_lane_collapse_called_at_init():
    content = _read_html()
    assert "initLaneCollapse()" in content, \
        "initLaneCollapse() must be called during page initialisation"


def test_storage_key_uses_kanban_lane_prefix():
    content = _read_html()
    assert "kanban-lane-" in content, \
        "Local storage key for collapsed lane must use 'kanban-lane-' prefix"


def test_collapsed_column_is_valid_drop_target():
    content = _read_html()
    # DnD drop handler is registered on .kanban-column — collapsed columns
    # are still .kanban-column, so no extra wiring is needed; assert the
    # drop wiring targets the column (not only the wrapper).
    assert "wrapper.closest('.kanban-column')" in content, \
        "DnD must be wired to .kanban-column so collapsed rails stay valid drop targets"
