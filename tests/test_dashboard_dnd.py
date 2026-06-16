import os

HTML_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
BOARD_RENDERER_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "web", "static", "js", "boardRenderer.js")


def _read_html():
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _read_board_renderer():
    with open(BOARD_RENDERER_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _read_kanban_sources():
    return _read_html() + "\n" + _read_board_renderer()


def test_chevron_move_left_absent():
    content = _read_html()
    assert 'title="Move Left"' not in content, "Move Left chevron button must be removed"


def test_chevron_move_right_absent():
    content = _read_html()
    assert 'title="Move Right"' not in content, "Move Right chevron button must be removed"


def test_draggable_attribute_on_cards():
    content = _read_board_renderer()
    assert "setAttribute('draggable', 'true')" in content, \
        "Cards must set draggable='true' attribute"


def test_dragstart_wired():
    content = _read_board_renderer()
    assert "dragstart" in content, "dragstart event listener must be wired on cards"


def test_dragover_wired():
    content = _read_html()
    assert "dragover" in content, "dragover event listener must be wired on lane columns"


def test_drop_handler_wired():
    content = _read_html()
    assert "addEventListener('drop'" in content, \
        "drop event listener must be wired on lane columns"


def test_hover_reject_css_defined():
    content = _read_html()
    assert ".hover-reject" in content, "hover-reject CSS class must be defined"


def test_hover_reject_class_on_button():
    content = _read_board_renderer()
    assert "hover-reject" in content and "reject-btn hover-reject" in content, \
        "Reject button must carry hover-reject class"


def test_same_lane_drop_noop():
    content = _read_html()
    assert "job.status === lane" in content, \
        "Same-lane drop must be a no-op (guarded by job.status === lane check)"


def test_init_kanban_dnd_defined_and_called():
    content = _read_html()
    assert "function initKanbanDnd" in content, "initKanbanDnd function must be defined"
    assert "initKanbanDnd()" in content, "initKanbanDnd must be called at init"


def test_drag_does_not_trigger_enrichment():
    content = _read_html()
    assert "newStatus === 'enriching'" not in content, \
        "Lane drag must never call enrichJob — drag is status-only"


def test_dragging_class_applied_on_dragstart():
    content = _read_board_renderer()
    assert "classList.add('dragging')" in content, \
        "Dragging card must get 'dragging' CSS class on dragstart"


def test_dragging_class_removed_on_dragend():
    content = _read_board_renderer()
    assert "classList.remove('dragging')" in content, \
        "Dragging class must be removed on dragend"
