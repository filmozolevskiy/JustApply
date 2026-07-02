"""FastAPI server bootstrap: DB init on startup, not import; health smoke test."""

import importlib
import os
import sqlite3
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.db.connection as _db_connection
from src.web import server

client = TestClient(server.app)


def test_health_smoke():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "FastAPI backend online"}


def test_init_db_runs_on_application_startup(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    test_db = str(tmp_path / "startup.db")
    monkeypatch.setattr(_db_connection, "DB_PATH", test_db)
    monkeypatch.setattr(
        server.asyncio,
        "create_task",
        lambda coro: None,
    )

    assert not os.path.exists(test_db)

    with TestClient(server.app) as startup_client:
        response = startup_client.get("/api/health")

    assert response.status_code == 200
    assert os.path.exists(test_db)
    conn = sqlite3.connect(test_db)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()
    assert "jobs" in tables


def test_import_server_module_does_not_call_init_db():
    sys.modules.pop("src.web.server", None)

    with patch("src.db.init_db") as mock_init:
        importlib.import_module("src.web.server")
        mock_init.assert_not_called()


def test_web_modules_do_not_mutate_sys_path():
    path_before = list(sys.path)
    for module_name in ("src.web.server", "src.web.run_dashboard"):
        sys.modules.pop(module_name, None)
    importlib.import_module("src.web.server")
    importlib.import_module("src.web.run_dashboard")
    assert sys.path == path_before
