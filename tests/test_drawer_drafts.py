"""PRD #105: explicit Post/Cancel for Job Comment and Outreach Message Template."""

from kanban_js import load_kanban_js, read_drawer_controller


def _drawer():
    return read_drawer_controller()


def test_comment_textarea_does_not_autosave_on_input():
    drawer = _drawer()
    assert 'oninput="onCommentDraftInput(' in drawer, \
        "Comment textarea must track draft locally without autosave on input"
    assert "commentTimeout" not in drawer, \
        "Debounced comment autosave must be removed"


def test_outreach_textarea_does_not_autosave_on_input():
    drawer = _drawer()
    assert 'oninput="onOutreachDraftInput(' in drawer, \
        "Outreach textarea must not autosave on input"
    assert "templateSaveTimeout" not in drawer, \
        "Debounced outreach autosave must be removed"


def test_post_and_cancel_handlers_defined():
    drawer = _drawer()
    for name in (
        "postJobComment",
        "cancelJobComment",
        "postOutreachTemplate",
        "cancelOutreachTemplate",
    ):
        assert f"function {name}(" in drawer, f"{name} must be defined in drawerController"


def test_drawer_renders_post_cancel_buttons():
    drawer = _drawer()
    assert "drawer-comment-post" in drawer
    assert "drawer-comment-cancel" in drawer
    assert "drawer-outreach-post" in drawer
    assert "drawer-outreach-cancel" in drawer


def test_post_comment_calls_comment_endpoint_without_debounce():
    drawer = _drawer()
    start = drawer.find("function postJobComment(")
    assert start != -1
    body = drawer[start : start + 1200]
    assert "/comment" in body
    assert "setTimeout" not in body


def test_post_outreach_normalizes_greeting_before_save():
    drawer = _drawer()
    start = drawer.find("function postOutreachTemplate(")
    assert start != -1
    body = drawer[start : start + 1200]
    assert "normalizeGreeting" in body
    assert "/template" in body


def test_unsaved_draft_guard_before_navigation():
    drawer = _drawer()
    assert "confirmDiscardIfNeeded" in drawer
    assert "hasUnsavedDrafts" in drawer
    close_start = drawer.find("async function closeDrawer(")
    assert close_start != -1
    close_body = drawer[close_start : close_start + 400]
    assert "confirmDiscardIfNeeded" in close_body


def test_discard_guard_uses_injected_confirm_callback():
    drawer = _drawer()
    assert "confirmDiscardUnsavedEdits" in drawer


def test_post_failure_appends_activity_log():
    drawer = _drawer()
    assert "/activity-log" in drawer
    assert "Notes save failed" in drawer
    assert "Outreach template save failed" in drawer


def test_draft_input_does_not_mutate_job_comment():
    drawer = _drawer()
    start = drawer.find("function onCommentDraftInput(")
    assert start != -1
    body = drawer[start : start + 300]
    assert "job.comment" not in body
    assert "onJobMutated" not in body
