"""Kanban Role-filtered pill and drawer Job Info row (PRD #207 / #213)."""

import os
import subprocess

from fastapi.testclient import TestClient
from src.web.server import app

client = TestClient(app)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BOARD_RENDERER_PATH = os.path.join(REPO_ROOT, "src", "web", "static", "js", "boardRenderer.js")
DRAWER_CONTROLLER_PATH = os.path.join(REPO_ROOT, "src", "web", "static", "js", "drawerController.js")
SERVER_PATH = os.path.join(REPO_ROOT, "src", "web", "server.py")
NOTES_PATH = os.path.join(REPO_ROOT, "src", "web", "prototype", "NOTES.md")


def _run_node(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_card_role_filtered_badge_shows_pill_with_reason_hover():
    result = _run_node(
        """
        import { cardRoleFilteredBadge } from './src/web/static/js/boardRenderer.js';

        const html = cardRoleFilteredBadge({
          roleFiltered: true,
          roleFilteredReason: 'Searched QA vs Software Engineer',
        });
        if (!html.includes('Role-filtered')) process.exit(1);
        if (!html.includes('kanban-card-badges') && !html.includes('role-filtered')) process.exit(2);
        if (!html.includes('title="Searched QA vs Software Engineer"')) process.exit(3);

        const empty = cardRoleFilteredBadge({ roleFiltered: false, roleFilteredReason: 'ignored' });
        if (empty !== '') process.exit(4);

        const missing = cardRoleFilteredBadge({});
        if (missing !== '') process.exit(5);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_drawer_role_relevance_row_shows_label_and_reason():
    result = _run_node(
        """
        import { drawerRoleRelevanceRow } from './src/web/static/js/drawerController.js';

        const html = drawerRoleRelevanceRow({
          roleFiltered: true,
          roleFilteredReason: 'Searched QA vs Software Engineer',
        });
        if (!html.includes('Role Relevance: Role-filtered')) process.exit(1);
        if (!html.includes('Searched QA vs Software Engineer')) process.exit(2);

        const empty = drawerRoleRelevanceRow({ roleFiltered: false, roleFilteredReason: 'ignored' });
        if (empty !== '') process.exit(3);

        const missing = drawerRoleRelevanceRow({});
        if (missing !== '') process.exit(4);

        console.log('ok');
        """
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_board_renderer_wires_role_filtered_pill_into_badge_row():
    with open(BOARD_RENDERER_PATH, encoding="utf-8") as f:
        content = f.read()
    assert "cardRoleFilteredBadge(job)" in content
    assert "kanban-card-badges" in content
    card_slice = content[content.find("const badgeParts") : content.find("const badgesHtml")]
    assert "cardRoleFilteredBadge" in card_slice
    assert "Role-filtered" not in content[content.find("kanban-card-title") : content.find("kanban-card-company-block")]


def test_drawer_wires_role_relevance_row_without_banner_or_title_strip():
    with open(DRAWER_CONTROLLER_PATH, encoding="utf-8") as f:
        content = f.read()
    assert "drawerRoleRelevanceRow(job)" in content
    assert "Recruiting / Staffing Agency Warning" in content
    role_block_start = content.find("function drawerRoleRelevanceRow")
    assert role_block_start != -1
    role_block = content[role_block_start : role_block_start + 800]
    assert "fa-triangle-exclamation" not in role_block
    header = content[content.find("drawer-header-title") : content.find("drawer-header-actions")]
    assert "roleFiltered" not in header
    assert "Role-filtered" not in header


def test_role_reject_copy_prototype_is_not_product_surface():
    resp = client.get("/prototype/role-reject-copy")
    assert resp.status_code == 404
    with open(SERVER_PATH, encoding="utf-8") as f:
        server = f.read()
    assert "/prototype/role-reject-copy" not in server
    with open(NOTES_PATH, encoding="utf-8") as f:
        notes = f.read()
    assert "Role-filtered" in notes
    assert "badge row" in notes.lower()
