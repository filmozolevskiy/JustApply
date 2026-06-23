"""Tests verifying that the refresh-contacts endpoint and refreshContacts JS are removed."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import db as database
import src.db.connection as _db_connection
from src.web.server import app
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_just_apply.db"
    test_db_str = str(test_db)
    monkeypatch.setattr(_db_connection, "DB_PATH", test_db_str)
    database.init_db(test_db_str)
    yield test_db_str


# --- POST /api/jobs/{id}/refresh-contacts is removed ---

def test_post_refresh_contacts_endpoint_removed():
    """The refresh-contacts endpoint no longer exists."""
    response = client.post("/api/jobs/1/refresh-contacts")
    assert response.status_code == 404


# --- Dashboard HTML: refreshContacts function is removed ---

def _load_script():
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    for marker in ('<script type="module">', '<script>'):
        start = content.find(marker)
        if start != -1:
            return content[start:]
    raise AssertionError("<script> block not found")


def test_dashboard_html_refresh_contacts_function_removed():
    script = _load_script()
    assert "function refreshContacts(" not in script, \
        "refreshContacts JS function must be removed from dashboard"


def test_dashboard_html_refresh_contacts_not_exported():
    script = _load_script()
    assert "refreshContacts," not in script, \
        "refreshContacts must not appear in the window export block"


# --- Drawer: Refresh Contacts button is removed ---

def test_drawer_refresh_contacts_button_removed():
    from kanban_js import read_drawer_controller
    content = read_drawer_controller()
    assert "Refresh Contacts" not in content, \
        "Refresh Contacts button must be removed from drawerController.js"
    assert "refreshContacts" not in content, \
        "refreshContacts call must be removed from drawerController.js"
