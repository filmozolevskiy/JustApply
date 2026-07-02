"""Shared helpers for Kanban Dashboard JS module tests."""

import os

WEB_DIR = os.path.join(os.path.dirname(__file__), "..", "src", "web")
JS_DIR = os.path.join(WEB_DIR, "static", "js")
HTML_PATH = os.path.join(WEB_DIR, "dashboard.html")
DASHBOARD_CSS_PATH = os.path.join(WEB_DIR, "static", "css", "dashboard.css")
DRAWER_PATH = os.path.join(JS_DIR, "drawerController.js")
TASK_LOG_PATH = os.path.join(JS_DIR, "taskLogClient.js")

DASHBOARD_MODULE_PATHS = (
    "perRegionLimit.js",
    "spendConfirmation.js",
    "evaluationLock.js",
    "jobSearchSettings.js",
    "boardOrchestration.js",
    "profileManager.js",
    "dashboardApp.js",
)


def read_dashboard_html() -> str:
    with open(HTML_PATH, encoding="utf-8") as f:
        return f.read()


def read_dashboard_css() -> str:
    with open(DASHBOARD_CSS_PATH, encoding="utf-8") as f:
        return f.read()


def read_drawer_controller() -> str:
    with open(DRAWER_PATH, encoding="utf-8") as f:
        return f.read()


def read_task_log_client() -> str:
    with open(TASK_LOG_PATH, encoding="utf-8") as f:
        return f.read()


def read_dashboard_module(name: str) -> str:
    path = os.path.join(JS_DIR, name)
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_dashboard_modules() -> str:
    return "\n".join(read_dashboard_module(name) for name in DASHBOARD_MODULE_PATHS)


def get_script_section(content: str) -> str:
    for marker in ('<script type="module">', '<script>'):
        start = content.find(marker)
        if start != -1:
            return content[start:]
    raise AssertionError("<script> block not found")


def load_dashboard_js() -> str:
    """Inline bootstrap plus extracted dashboard modules (orchestration, search, spend, lock)."""
    return get_script_section(read_dashboard_html()) + "\n" + read_dashboard_modules()


def load_kanban_js() -> str:
    return (
        load_dashboard_js()
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
