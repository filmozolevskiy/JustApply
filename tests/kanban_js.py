"""Shared helpers for Kanban Dashboard JS module tests."""

import os

WEB_DIR = os.path.join(os.path.dirname(__file__), "..", "src", "web")
HTML_PATH = os.path.join(WEB_DIR, "dashboard.html")
DRAWER_PATH = os.path.join(WEB_DIR, "static", "js", "drawerController.js")
TASK_LOG_PATH = os.path.join(WEB_DIR, "static", "js", "taskLogClient.js")


def read_dashboard_html() -> str:
    with open(HTML_PATH, encoding="utf-8") as f:
        return f.read()


def read_drawer_controller() -> str:
    with open(DRAWER_PATH, encoding="utf-8") as f:
        return f.read()


def read_task_log_client() -> str:
    with open(TASK_LOG_PATH, encoding="utf-8") as f:
        return f.read()


def get_script_section(content: str) -> str:
    for marker in ('<script type="module">', '<script>'):
        start = content.find(marker)
        if start != -1:
            return content[start:]
    raise AssertionError("<script> block not found")


def load_kanban_js() -> str:
    return (
        get_script_section(read_dashboard_html())
        + "\n"
        + read_drawer_controller()
        + "\n"
        + read_task_log_client()
    )


def get_drawer_body() -> str:
    content = read_drawer_controller()
    start = content.find("function buildContactGroupsHtml(")
    if start == -1:
        start = content.find("function openJobDetailsDrawer(")
    assert start != -1, "Drawer function (or buildContactGroupsHtml) not found"
    return content[start : start + 20000]
