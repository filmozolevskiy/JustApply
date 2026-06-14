import os
import sys
import json
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import db as database
import src.db.connection as _db_connection
from src.web.server import app, TaskState, active_tasks

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_job_tracker.db")
    monkeypatch.setattr(_db_connection, "DB_PATH", test_db)
    database.init_db(test_db)
    yield test_db


@pytest.fixture(autouse=True)
def reset_active_tasks():
    active_tasks.clear()
    yield
    active_tasks.clear()


def _make_completed_state(log_messages):
    """Return a completed TaskState with pre-filled logs and a sentinel in the queue."""
    state = TaskState({"job_id": 1})
    for msg in log_messages:
        state.logs.append({"level": "info", "message": msg})
    state.status = "completed"
    state.jobs = []
    state.queue.put_nowait(None)
    return state


def _collect_messages(task_id, skip=0):
    """Stream the SSE endpoint and return all parsed JSON payloads."""
    messages = []
    with client.stream("GET", f"/api/logs/{task_id}?skip={skip}") as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if line.startswith("data: "):
                messages.append(json.loads(line[6:]))
    return messages


# --- 404 on unknown task ---

def test_unknown_task_returns_404():
    resp = client.get("/api/logs/nonexistent-id")
    assert resp.status_code == 404
    assert resp.json() == {"message": "Task ID not found"}


# --- skip parameter skips already-seen log lines ---

def test_skip_zero_returns_all_logs():
    active_tasks["t1"] = _make_completed_state(["Step 1", "Step 2", "Step 3"])
    msgs = _collect_messages("t1", skip=0)
    logs = [m for m in msgs if m.get("type") == "log"]
    assert [m["message"] for m in logs] == ["Step 1", "Step 2", "Step 3"]


def test_skip_two_omits_first_two_logs():
    active_tasks["t2"] = _make_completed_state(["Step 1", "Step 2", "Step 3"])
    msgs = _collect_messages("t2", skip=2)
    logs = [m for m in msgs if m.get("type") == "log"]
    assert len(logs) == 1
    assert logs[0]["message"] == "Step 3"


def test_skip_equal_to_total_yields_no_logs():
    active_tasks["t3"] = _make_completed_state(["Step 1", "Step 2"])
    msgs = _collect_messages("t3", skip=2)
    logs = [m for m in msgs if m.get("type") == "log"]
    assert len(logs) == 0


def test_negative_skip_is_treated_as_zero():
    active_tasks["t4"] = _make_completed_state(["Line A", "Line B"])
    msgs = _collect_messages("t4", skip=-5)
    logs = [m for m in msgs if m.get("type") == "log"]
    assert [m["message"] for m in logs] == ["Line A", "Line B"]


# --- stream termination events ---

def test_completed_task_stream_ends_with_done_event():
    active_tasks["t5"] = _make_completed_state([])
    msgs = _collect_messages("t5")
    done = [m for m in msgs if m.get("type") == "done"]
    assert len(done) == 1


def test_failed_task_stream_ends_with_error_and_done():
    state = TaskState({"job_id": 1})
    state.status = "failed"
    state.queue.put_nowait(None)
    active_tasks["t6"] = state

    msgs = _collect_messages("t6")
    done = [m for m in msgs if m.get("type") == "done"]
    errors = [m for m in msgs if m.get("type") == "log" and m.get("level") == "error"]
    assert len(done) == 1
    assert len(errors) >= 1


# --- skip is independent per reconnect ---

def test_skip_one_then_skip_two_covers_all_logs():
    """Simulates two reconnects: first skipping 0, second skipping 1."""
    active_tasks["t7a"] = _make_completed_state(["A", "B", "C"])
    msgs1 = _collect_messages("t7a", skip=0)
    logs1 = [m for m in msgs1 if m.get("type") == "log"]
    assert len(logs1) == 3

    # Reconnect, skipping lines already seen
    active_tasks["t7b"] = _make_completed_state(["A", "B", "C"])
    msgs2 = _collect_messages("t7b", skip=1)
    logs2 = [m for m in msgs2 if m.get("type") == "log"]
    assert len(logs2) == 2
    assert logs2[0]["message"] == "B"


def _make_live_task_state(log_messages):
    """Mirror log_callback: each line is stored in logs and queued."""
    state = TaskState({"job_id": 1})
    for msg in log_messages:
        event = {"level": "info", "message": msg}
        state.logs.append(event)
        state.queue.put_nowait(event)
    state.status = "completed"
    state.queue.put_nowait(None)
    return state


def test_live_stream_does_not_duplicate_replayed_logs():
    """Logs buffered before SSE connect must not appear twice (replay + queue)."""
    active_tasks["live1"] = _make_live_task_state(
        ["Enriching 'QA' at 'Acme'...", "Fetching up to 100 employees for 'Acme'..."]
    )
    msgs = _collect_messages("live1", skip=0)
    logs = [m for m in msgs if m.get("type") == "log"]
    assert [m["message"] for m in logs] == [
        "Enriching 'QA' at 'Acme'...",
        "Fetching up to 100 employees for 'Acme'...",
    ]


def test_live_stream_reconnect_skips_replayed_and_queued_history():
    """Reconnect with skip=N must not re-deliver lines already seen."""
    active_tasks["live2"] = _make_live_task_state(["A", "B", "C"])
    msgs = _collect_messages("live2", skip=1)
    logs = [m for m in msgs if m.get("type") == "log"]
    assert [m["message"] for m in logs] == ["B", "C"]
