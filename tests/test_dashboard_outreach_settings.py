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
    test_db = tmp_path / "test_job_tracker.db"
    test_db_str = str(test_db)

    monkeypatch.setattr(_db_connection, "DB_PATH", test_db_str)

    database.init_db(test_db_str)

    yield test_db_str


def test_get_outreach_settings_returns_defaults_on_first_read():
    response = client.get("/api/settings/outreach")
    assert response.status_code == 200
    data = response.json()
    assert data["target_russian_speakers"] is True
    assert data["target_recruiters"] is True


def test_put_outreach_settings_persists_values():
    put_response = client.put(
        "/api/settings/outreach",
        json={"target_russian_speakers": False, "target_recruiters": True},
    )
    assert put_response.status_code == 200
    data = put_response.json()
    assert data["target_russian_speakers"] is False
    assert data["target_recruiters"] is True


def test_outreach_settings_round_trip():
    client.put(
        "/api/settings/outreach",
        json={"target_russian_speakers": False, "target_recruiters": False},
    )
    get_response = client.get("/api/settings/outreach")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["target_russian_speakers"] is False
    assert data["target_recruiters"] is False


def test_dashboard_html_contains_outreach_settings_panel():
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    assert 'id="toggle-russian-speakers"' in content, "Missing Russian speakers toggle"
    assert 'id="toggle-recruiters"' in content, "Missing recruiters toggle"
    assert "Outreach Settings" in content, "Missing Outreach Settings panel heading"
    assert "saveOutreachSettings" in content, "Missing saveOutreachSettings JS function"
    assert "loadOutreachSettings" in content, "Missing loadOutreachSettings JS function"


def test_dashboard_html_outreach_panel_is_separate_from_board_controls():
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        content = f.read()
    outreach_pos = content.find("Outreach Settings")
    board_controls_pos = content.find("Board Controls")
    assert outreach_pos != -1, "Outreach Settings panel not found"
    assert board_controls_pos != -1, "Board Controls panel not found"
    assert outreach_pos != board_controls_pos, "Outreach Settings must be separate from Board Controls"
