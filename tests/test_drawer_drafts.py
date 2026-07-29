"""PRD #105: explicit Post/Cancel for Job Comment and Outreach Message Template.

PRD #185 / #191: Job Comment drafts (root, reply, inline edit) in Unsaved Draft Warning.
"""

import subprocess
from pathlib import Path

from kanban_js import read_drawer_controller

REPO_ROOT = Path(__file__).resolve().parents[1]


def _drawer():
    return read_drawer_controller()


def _run_node(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_reply_compose_text_is_dirty_comment_draft():
    """Non-empty reply compose counts as a dirty Job Comment draft."""
    result = _run_node(
        """
        import { isCommentDraftDirty } from './src/web/static/js/drawerController.js';

        if (isCommentDraftDirty({ replyComposeValue: 'Follow up' }) !== true) process.exit(1);
        if (isCommentDraftDirty({ replyComposeValue: '   ' }) !== false) process.exit(2);
        if (isCommentDraftDirty({ replyComposeValue: '' }) !== false) process.exit(3);
        if (isCommentDraftDirty({}) !== false) process.exit(4);
        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_inline_edit_differs_from_posted_body_is_dirty():
    """Inline edit is dirty only when textarea differs from last posted body."""
    result = _run_node(
        """
        import { isCommentDraftDirty } from './src/web/static/js/drawerController.js';

        if (isCommentDraftDirty({
          editValue: 'Changed',
          editOriginalBody: 'Original',
        }) !== true) process.exit(1);
        if (isCommentDraftDirty({
          editValue: 'Original',
          editOriginalBody: 'Original',
        }) !== false) process.exit(2);
        if (isCommentDraftDirty({
          rootComposeValue: 'New root',
        }) !== true) process.exit(3);
        if (isCommentDraftDirty({
          rootComposeValue: '   ',
        }) !== false) process.exit(4);
        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_is_comment_dirty_reads_root_reply_and_edit_fields():
    """Drawer isCommentDirty consults root compose, reply compose, and inline edit."""
    drawer = _drawer()
    start = drawer.find("function isCommentDirty(")
    assert start != -1
    body = drawer[start : start + 900]
    assert "isCommentDraftDirty" in body
    assert "drawer-comment-text" in body
    assert "drawer-comment-reply-text" in body
    assert "drawer-comment-edit-text" in body


def test_discard_message_names_comment_drafts_alone_or_with_outreach():
    """Unsaved Draft Warning body names Job Comment drafts and/or outreach."""
    result = _run_node(
        """
        import { buildDiscardDraftMessage } from './src/web/static/js/drawerController.js';

        const both = buildDiscardDraftMessage({ commentDirty: true, outreachDirty: true });
        if (!both.toLowerCase().includes('notes') || !both.toLowerCase().includes('outreach')) {
          process.exit(1);
        }
        const notesOnly = buildDiscardDraftMessage({ commentDirty: true, outreachDirty: false });
        if (!notesOnly.toLowerCase().includes('notes') || notesOnly.toLowerCase().includes('outreach')) {
          process.exit(2);
        }
        const outreachOnly = buildDiscardDraftMessage({ commentDirty: false, outreachDirty: true });
        if (!outreachOnly.toLowerCase().includes('outreach') || outreachOnly.toLowerCase().includes('notes')) {
          process.exit(3);
        }
        if (buildDiscardDraftMessage({ commentDirty: false, outreachDirty: false }) !== '') {
          process.exit(4);
        }
        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_discard_reverts_comment_reply_and_edit_drafts():
    """Discard clears root compose and closes reply/inline-edit draft UI."""
    drawer = _drawer()
    start = drawer.find("function revertDraftFields(")
    assert start != -1
    body = drawer[start : start + 700]
    assert "drawer-comment-text" in body
    assert "editingCommentId = null" in body
    assert "replyingToCommentId = null" in body
    assert "refreshCommentsListInDrawer" in body


def test_discard_guard_keeps_drafts_when_confirm_cancelled():
    """Modal Cancel leaves drafts; only Discard calls revertDraftFields."""
    drawer = _drawer()
    start = drawer.find("async function confirmDiscardIfNeeded(")
    assert start != -1
    body = drawer[start : start + 350]
    assert "confirmDiscardUnsavedEdits" in body
    assert "revertDraftFields()" in body
    assert "if (ok) revertDraftFields()" in body or "ok && revertDraftFields" in body


def test_nav_and_close_guard_dirty_comment_drafts():
    """Leaving drawer or switching jobs runs discard guard (covers dirty comments)."""
    drawer = _drawer()
    for fn_name in ("closeDrawer", "navigateDrawerJob", "openJobDetailsDrawer"):
        start = drawer.find(f"async function {fn_name}(")
        assert start != -1, f"{fn_name} missing"
        body = drawer[start : start + 500]
        assert "confirmDiscardIfNeeded" in body, f"{fn_name} must guard dirty drafts"


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
    assert "/comments" in body
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
    assert "Comment save failed" in drawer
    assert "Outreach template save failed" in drawer


def test_draft_input_does_not_mutate_job_comment():
    drawer = _drawer()
    start = drawer.find("function onCommentDraftInput(")
    assert start != -1
    body = drawer[start : start + 300]
    assert "job.comments" not in body
    assert "onJobMutated" not in body
